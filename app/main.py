import socket
socket.setdefaulttimeout(120)  # Timeout de 120s para impedir travamentos de socket
import os
import uuid
import shutil
import logging
import tempfile
import threading
import requests
import json
import hashlib
from fastapi import FastAPI, UploadFile, File, Form, HTTPException, BackgroundTasks, Header, Depends, Query
from fastapi.responses import HTMLResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel

# Módulos locais do Sal0 Legendas
import process_manager as pm
from audio_processor import extract_audio, create_proxy_video, download_youtube
from transcriber import transcribe_audio, is_model_downloaded, get_model_local_dir
from translator import translate_segments, SUPPORTED_LANGUAGES
from subtitle_formatter import generate_srt, generate_vtt, generate_ass, generate_txt
from video_renderer import render_subtitled_video

APP_VERSION = "v1.0.10"

# Configuração de Logger
logger = logging.getLogger("legendas")
logger.setLevel(logging.INFO)
ch = logging.StreamHandler()
ch.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s] legendas: %(message)s"))
logger.addHandler(ch)

# Sistema de Logs de Diagnóstico
DIAGNOSTIC_LOG_FILE = "/data/output/app_diagnostic.log"

def log_diagnostic(message: str, level: str = "INFO"):
    """Escreve uma mensagem estruturada no arquivo de diagnósticos em /data/output/."""
    try:
        os.makedirs(os.path.dirname(DIAGNOSTIC_LOG_FILE), exist_ok=True)
        import datetime
        timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        entry = f"[{timestamp}] [{level}] {message}\n"
        with open(DIAGNOSTIC_LOG_FILE, "a", encoding="utf-8") as f:
            f.write(entry)
    except Exception as e:
        logger.error(f"Erro ao salvar log de diagnóstico: {e}")

app = FastAPI(title="Sal0 Legendas", version=APP_VERSION)

# Templates HTML e Arquivos Estáticos
templates = Jinja2Templates(directory="templates")
app.mount("/templates", StaticFiles(directory="templates"), name="templates")

@app.get("/favicon.ico", include_in_schema=False)
async def favicon():
    if os.path.exists("templates/favicon.png"):
        return FileResponse("templates/favicon.png")
    return HTMLResponse("", status_code=204)

@app.get("/logo.png", include_in_schema=False)
async def logo():
    if os.path.exists("templates/logo.png"):
        return FileResponse("templates/logo.png")
    return HTMLResponse("", status_code=204)

# Lock de concorrência global
processing_lock = threading.Lock()

# Lock e Estado de progresso global
state_lock = threading.Lock()
state = {
    "status": "idle",  # idle, processing, waiting_for_user_correction, done, error
    "step": "Idle",
    "progress": 0,
    "original_filename": None,
    "result_file": None,
    "error_message": None,
    "detected_language": None,
    "target_language": "pt-BR"
}

# Arquivo de Persistência de Estado
STATE_FILE = "/data/output/state.json"

def save_state_to_disk(state_dict: dict):
    try:
        os.makedirs(os.path.dirname(STATE_FILE), exist_ok=True)
        with open(STATE_FILE, "w", encoding="utf-8") as f:
            json.dump(state_dict, f, indent=4, ensure_ascii=False)
    except Exception as e:
        logger.error(f"Erro ao salvar estado em disco: {e}")

def load_state_from_disk() -> dict:
    if os.path.exists(STATE_FILE):
        try:
            with open(STATE_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            logger.error(f"Erro ao ler estado do disco: {e}")
    return {"status": "idle", "step": "Idle", "progress": 0}

def update_state(status: str, step: str, progress: int, original_filename: str = None, 
                 result_file: str = None, error_message: str = None, detected_language: str = None, target_language: str = None):
    with state_lock:
        state["status"] = status
        state["step"] = step
        state["progress"] = progress
        if original_filename is not None:
            state["original_filename"] = original_filename
        if result_file is not None:
            state["result_file"] = result_file
        if error_message is not None:
            state["error_message"] = error_message
        if detected_language is not None:
            state["detected_language"] = detected_language
        if target_language is not None:
            state["target_language"] = target_language
            
        current_copy = dict(state)
    save_state_to_disk(current_copy)

# Variáveis globais para fluxo de correção visual (Pausa 75%)
segments_to_edit = []
correction_event = threading.Event()

# =====================================================================
# AUTENTICAÇÃO E USUÁRIOS COMPATÍVEL COM O PADRÃO /data
# =====================================================================
USERS_FILE = "/data/users.json"
SESSIONS_FILE = "/data/sessions.json"

def load_users() -> dict:
    if os.path.exists(USERS_FILE):
        try:
            with open(USERS_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return {}

def save_users(users: dict):
    os.makedirs(os.path.dirname(USERS_FILE), exist_ok=True)
    with open(USERS_FILE, "w", encoding="utf-8") as f:
        json.dump(users, f, indent=4)

def load_sessions() -> dict:
    if os.path.exists(SESSIONS_FILE):
        try:
            with open(SESSIONS_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return {}

def save_sessions(sessions: dict):
    os.makedirs(os.path.dirname(SESSIONS_FILE), exist_ok=True)
    with open(SESSIONS_FILE, "w", encoding="utf-8") as f:
        json.dump(sessions, f, indent=4)

def get_current_user(
    x_session_token: str = Header(None),
    authorization: str = Header(None),
    token: str = Query(None)
) -> dict:
    auth_token = x_session_token or token
    if not auth_token and authorization:
        if authorization.startswith("Bearer "):
            auth_token = authorization.split(" ")[1]
        else:
            auth_token = authorization

    users = load_users()
    if not users:
        return {"username": "admin", "role": "admin"}

    if not auth_token:
        raise HTTPException(status_code=401, detail="Token de sessão não fornecido.")

    sessions = load_sessions()
    if auth_token not in sessions:
        raise HTTPException(status_code=401, detail="Sessão inválida ou expirada.")

    username = sessions[auth_token].get("username")
    if username not in users:
        raise HTTPException(status_code=401, detail="Usuário não encontrado.")

    return {"username": username, "role": users[username].get("role", "user")}

# =====================================================================
# REGISTRO DE CONFIGURAÇÕES (Telegram, URL Externa, Perfis)
# =====================================================================
TELEGRAM_CONFIG_FILE = "/data/output/telegram.json"
EXTERNAL_URL_FILE = "/data/output/external_url.json"
PROFILES_FILE = "/data/output/profiles.json"
SAVED_LYRICS_FILE = "/data/output/saved_lyrics.txt"

def load_telegram_config() -> dict:
    if os.path.exists(TELEGRAM_CONFIG_FILE):
        try:
            with open(TELEGRAM_CONFIG_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return {"telegram_token": "", "telegram_chat_id": ""}

def load_external_url_config() -> dict:
    if os.path.exists(EXTERNAL_URL_FILE):
        try:
            with open(EXTERNAL_URL_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return {"external_url": ""}

def send_telegram_notification(token: str, chat_id: str, message: str):
    """Envia notificação de texto simples para o Telegram."""
    if not token or not chat_id:
        return
    try:
        url = f"https://api.telegram.org/bot{token}/sendMessage"
        data = {"chat_id": chat_id, "text": message, "parse_mode": "HTML"}
        requests.post(url, data=data, timeout=10)
    except Exception as e:
        logger.error(f"Erro ao enviar notificação para Telegram: {e}")

def send_telegram_video_flow(token: str, chat_id: str, video_path: str, orig_name: str,
                               base_url: str = "", external_url: str = ""):
    """Envio de vídeo/arquivo final para Telegram com suporte a limite de 50MB."""
    if not token or not chat_id:
        return

    LIMIT_50MB = 50 * 1024 * 1024

    def build_download_links(history_filename: str = None) -> str:
        links = []
        if base_url and base_url.strip():
            if history_filename:
                local_link = f"{base_url.rstrip('/')}/api/library/download/history/{requests.utils.quote(history_filename)}"
            else:
                local_link = f"{base_url.rstrip('/')}/api/download"
            links.append(f'🏠 <a href="{local_link}">Download (rede local)</a>')
        if external_url and external_url.strip():
            if history_filename:
                ext_link = f"{external_url.rstrip('/')}/api/library/download/history/{requests.utils.quote(history_filename)}"
            else:
                ext_link = f"{external_url.rstrip('/')}/api/download"
            links.append(f'🌐 <a href="{ext_link}">Download (acesso externo)</a>')
        if not links:
            return ""
        return "\n" + "\n".join(links)

    try:
        if os.path.exists(video_path) and os.path.getsize(video_path) > LIMIT_50MB:
            file_size_mb = os.path.getsize(video_path) / (1024 * 1024)
            dest_filename = f"{orig_name}.mp4"
            download_block = build_download_links(dest_filename)
            
            msg = (
                f"🎬 <b>Sal0 Legendas</b>: O vídeo de <b>{orig_name}</b> foi concluído!\n\n"
                f"⚠️ Arquivo com <b>{file_size_mb:.1f}MB</b> (excede o limite de 50MB do Telegram).\n"
                f"💾 Salvo automaticamente na sua <b>Biblioteca</b>."
                f"{download_block}"
            )
            send_telegram_notification(token=token, chat_id=chat_id, message=msg)
            return

        url = f"https://api.telegram.org/bot{token}/sendVideo"
        with open(video_path, "rb") as video_file:
            files = {"video": video_file}
            data = {
                "chat_id": chat_id,
                "caption": f"🎥 <b>Sal0 Legendas</b>: Vídeo legendado pronto para <b>{orig_name}</b>!",
                "parse_mode": "HTML"
            }
            res = requests.post(url, data=data, files=files, timeout=90)
            if res.status_code == 200:
                logger.info("Vídeo enviado com sucesso para o Telegram.")
            else:
                download_block = build_download_links(f"{orig_name}.mp4")
                msg = (
                    f"🎬 <b>Sal0 Legendas</b>: O vídeo de <b>{orig_name}</b> foi concluído!\n\n"
                    f"⚠️ Não foi possível enviar via Telegram. Disponível na <b>Biblioteca</b>."
                    f"{download_block}"
                )
                send_telegram_notification(token=token, chat_id=chat_id, message=msg)

    except Exception as e:
        logger.error(f"Erro no envio em segundo plano para o Telegram: {e}")

# =====================================================================
# MODELS PYDANTIC
# =====================================================================
class TelegramModel(BaseModel):
    telegram_token: str
    telegram_chat_id: str

class ExternalUrlModel(BaseModel):
    external_url: str

class ProfileModel(BaseModel):
    name: str
    target_language: str = "pt-BR"
    source_language: str = "auto"
    whisper_model: str = "large-v3-turbo"
    font_size: int = 24
    text_color: str = "#FFFFFF"
    text_position: str = "bottom"
    show_box_background: bool = True
    export_subtitles_only: bool = False
    enable_correction: bool = False
    enable_vad: bool = True

class LyricsModel(BaseModel):
    lyrics_text: str = ""

# =====================================================================
# ENDPOINTS REST DE CONFIGURAÇÃO E DADOS
# =====================================================================
@app.get("/", response_class=HTMLResponse)
def read_root():
    with open("templates/index.html", "r", encoding="utf-8") as f:
        return HTMLResponse(content=f.read())

@app.get("/api/status")
def get_status():
    """Status é público para que qualquer navegador possa ver o progresso."""
    with state_lock:
        return dict(state)

@app.get("/api/languages")
def get_languages():
    return SUPPORTED_LANGUAGES

@app.get("/api/models/status")
def get_models_status(current_user: dict = Depends(get_current_user)):
    models_info = []
    models_keys = ["large-v3-turbo", "medium", "small", "tiny", "large-v3"]
    for key in models_keys:
        downloaded = is_model_downloaded(key)
        local_dir = get_model_local_dir(key)
        models_info.append({
            "key": key,
            "name": key.upper(),
            "downloaded": downloaded,
            "path": local_dir or "Não baixado"
        })
    return {"models": models_info}

@app.get("/api/lyrics")
def get_saved_lyrics(current_user: dict = Depends(get_current_user)):
    if os.path.exists(SAVED_LYRICS_FILE):
        try:
            with open(SAVED_LYRICS_FILE, "r", encoding="utf-8") as f:
                return {"lyrics_text": f.read()}
        except Exception as e:
            logger.error(f"Erro ao ler letra do servidor: {e}")
    return {"lyrics_text": ""}

@app.post("/api/lyrics")
def save_lyrics_server(data: LyricsModel, current_user: dict = Depends(get_current_user)):
    try:
        os.makedirs(os.path.dirname(SAVED_LYRICS_FILE), exist_ok=True)
        with open(SAVED_LYRICS_FILE, "w", encoding="utf-8") as f:
            f.write(data.lyrics_text or "")
        return {"status": "success"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Erro ao salvar letra no servidor: {e}")

@app.delete("/api/lyrics")
def delete_lyrics_server(current_user: dict = Depends(get_current_user)):
    if os.path.exists(SAVED_LYRICS_FILE):
        try:
            os.remove(SAVED_LYRICS_FILE)
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Erro ao excluir letra: {e}")
    return {"status": "success"}

@app.get("/api/telegram")
def get_telegram_config(current_user: dict = Depends(get_current_user)):
    return load_telegram_config()

@app.post("/api/telegram")
def save_telegram_config(config: TelegramModel, current_user: dict = Depends(get_current_user)):
    os.makedirs(os.path.dirname(TELEGRAM_CONFIG_FILE), exist_ok=True)
    with open(TELEGRAM_CONFIG_FILE, "w", encoding="utf-8") as f:
        json.dump(config.dict(), f, indent=4)
    return {"status": "success"}

@app.get("/api/external_url")
def get_external_url_config(current_user: dict = Depends(get_current_user)):
    return load_external_url_config()

@app.post("/api/external_url")
def save_external_url_config(config: ExternalUrlModel, current_user: dict = Depends(get_current_user)):
    os.makedirs(os.path.dirname(EXTERNAL_URL_FILE), exist_ok=True)
    with open(EXTERNAL_URL_FILE, "w", encoding="utf-8") as f:
        json.dump(config.dict(), f, indent=4)
    return {"status": "success"}

@app.get("/api/profiles")
def get_profiles(current_user: dict = Depends(get_current_user)):
    if os.path.exists(PROFILES_FILE):
        try:
            with open(PROFILES_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return {
        "Padrão": {
            "target_language": "pt-BR",
            "source_language": "auto",
            "whisper_model": "large-v3-turbo",
            "font_size": 24,
            "text_color": "#FFFFFF",
            "text_position": "bottom",
            "show_box_background": True,
            "export_subtitles_only": False,
            "enable_correction": False,
            "enable_vad": True
        }
    }

@app.post("/api/profiles")
def save_profile(profile: ProfileModel, current_user: dict = Depends(get_current_user)):
    profiles = get_profiles(current_user)
    profiles[profile.name] = profile.dict()
    os.makedirs(os.path.dirname(PROFILES_FILE), exist_ok=True)
    with open(PROFILES_FILE, "w", encoding="utf-8") as f:
        json.dump(profiles, f, indent=4, ensure_ascii=False)
    return {"status": "success", "profiles": profiles}

@app.delete("/api/profiles/{name}")
def delete_profile(name: str, current_user: dict = Depends(get_current_user)):
    if name == "Padrão":
        raise HTTPException(status_code=400, detail="O perfil 'Padrão' não pode ser excluído.")
    profiles = get_profiles(current_user)
    if name in profiles:
        del profiles[name]
        with open(PROFILES_FILE, "w", encoding="utf-8") as f:
            json.dump(profiles, f, indent=4, ensure_ascii=False)
    return {"status": "success", "profiles": profiles}

# =====================================================================
# PIPELINE PRINCIPAL DE PROCESSAMENTO (SEM LIMITE DE TEMPO)
# =====================================================================
def run_pipeline(
    input_video_path: str,
    target_language: str = "pt-BR",
    source_language: str = "auto",
    whisper_model: str = "large-v3-turbo",
    font_size: int = 24,
    text_color: str = "#FFFFFF",
    text_position: str = "bottom",
    show_box_background: bool = True,
    export_subtitles_only: bool = False,
    enable_correction: bool = False,
    enable_vad: bool = True,
    lyrics_text: str = None,
    youtube_url: str = None
):
    """
    Pipeline principal do Sal0 Legendas (Suporta vídeos de QUALQUER DURAÇÃO).
    """
    if not processing_lock.acquire(blocking=False):
        logger.warning("Processamento em andamento. Ignorando nova chamada.")
        return

    tele_config = load_telegram_config()
    telegram_token = tele_config.get("telegram_token", "")
    telegram_chat_id = tele_config.get("telegram_chat_id", "")
    
    ext_url_cfg = load_external_url_config()
    telegram_external_url = ext_url_cfg.get("external_url", "")
    telegram_base_url = "http://localhost:8001"

    with state_lock:
        orig_name = state.get("original_filename", "video_legenda")

    try:
        pm.cancel_event.clear()
        pm.clear_active_process()

        send_telegram_notification(
            telegram_token, telegram_chat_id,
            f"🎬 <b>Sal0 Legendas</b>: Iniciando legendagem de <b>{orig_name}</b>..."
        )

        output_dir = "/data/output"
        os.makedirs(output_dir, exist_ok=True)
        cache_dir = "/data/cache"
        os.makedirs(cache_dir, exist_ok=True)

        final_mp4_path = os.path.join(output_dir, "final_subtitled.mp4")
        final_srt_path = os.path.join("/data/library/subtitles", f"{orig_name}.srt")
        final_vtt_path = os.path.join("/data/library/subtitles", f"{orig_name}.vtt")
        final_ass_path = os.path.join("/data/library/subtitles", f"{orig_name}.ass")
        final_txt_path = os.path.join("/data/library/subtitles", f"{orig_name}.txt")
        
        os.makedirs("/data/library/subtitles", exist_ok=True)
        os.makedirs("/data/library/history", exist_ok=True)

        # Passo 1: Download do YouTube (se aplicável)
        if youtube_url and youtube_url.strip():
            pm.check_cancelled()
            update_state("processing", "Downloading YouTube Video", 10, target_language=target_language)
            send_telegram_notification(telegram_token, telegram_chat_id, "🌐 <b>Sal0 Legendas</b>: Baixando vídeo do YouTube...")
            input_video_path, orig_name = download_youtube(youtube_url, cache_dir)

        # Passo 2: Extrair Áudio WAV 16kHz
        pm.check_cancelled()
        update_state("processing", "Extracting Audio (WAV 16kHz)", 20, original_filename=orig_name, target_language=target_language)
        send_telegram_notification(telegram_token, telegram_chat_id, "🎵 <b>Sal0 Legendas</b>: Extraindo faixa de áudio (20%)")
        
        converted_wav = os.path.join(cache_dir, "input_audio.wav")
        extract_audio(input_video_path, converted_wav)

        # Passo 3: Transcrever Áudio de qualquer duração com Whisper AI + Silero VAD
        pm.check_cancelled()
        update_state("processing", f"Transcribing Speech ({whisper_model})", 45)
        send_telegram_notification(telegram_token, telegram_chat_id, f"✍️ <b>Sal0 Legendas</b>: Transcrevendo voz com IA ({whisper_model}) (45%)")
        
        segments, detected_lang = transcribe_audio(
            converted_wav,
            model_size=whisper_model,
            initial_prompt=lyrics_text,
            enable_vad=enable_vad
        )

        update_state("processing", "Translating Subtitles", 60, detected_language=detected_lang)

        # Passo 4: Tradução Automática (Padrão: pt-BR)
        pm.check_cancelled()
        target_display = SUPPORTED_LANGUAGES.get(target_language, target_language)
        send_telegram_notification(
            telegram_token, telegram_chat_id,
            f"🌐 <b>Sal0 Legendas</b>: Traduzindo de <b>{detected_lang.upper()}</b> para <b>{target_display}</b> (60%)"
        )
        
        segments = translate_segments(segments, target_lang=target_language, source_lang=source_language)

        # Passo 5: Pausa para Revisão & Correção de Legendas na Interface (se ativada)
        if enable_correction:
            global segments_to_edit, correction_event
            segments_to_edit = segments
            correction_event.clear()

            update_state("waiting_for_user_correction", "Waiting for Subtitle Review", 75)
            send_telegram_notification(
                telegram_token, telegram_chat_id,
                f"⚠️ <b>Sal0 Legendas</b>: As legendas de <b>{orig_name}</b> estão prontas para revisão! "
                "Acesse a interface web para ajustar textos e tempos antes da exportação."
            )

            logger.info("Aguardando o usuário revisar e salvar as legendas na interface web...")
            while not correction_event.is_set():
                pm.check_cancelled()
                correction_event.wait(timeout=1.0)

            segments = segments_to_edit
            logger.info("Retomando pipeline com as legendas revisadas pelo usuário.")

        # Passo 6: Exportação dos Arquivos de Legenda (.srt, .vtt, .ass, .txt)
        pm.check_cancelled()
        update_state("processing", "Generating Subtitle Files", 85)
        
        generate_srt(segments, final_srt_path, use_translated=True)
        generate_vtt(segments, final_vtt_path, use_translated=True)
        generate_txt(segments, final_txt_path, use_translated=True)
        generate_ass(
            segments, final_ass_path,
            font_size=font_size,
            text_color_hex=text_color,
            text_position=text_position,
            show_box_background=show_box_background,
            use_translated=True
        )

        # Se o usuário escolheu APENAS exportar legendas separadas (sem queimar vídeo)
        if export_subtitles_only:
            update_state("done", "Done (Subtitles Exported)", 100, result_file=final_srt_path)
            send_telegram_notification(
                telegram_token, telegram_chat_id,
                f"✅ <b>Sal0 Legendas</b>: Legendas para <b>{orig_name}</b> geradas com sucesso!\n"
                f"📄 Arquivos .SRT, .VTT, .ASS e .TXT disponíveis na Biblioteca."
            )
            processing_lock.release()
            return

        # Passo 7: Renderização do Vídeo Final com Legendas Embutidas (Qualidade 100% Original)
        pm.check_cancelled()
        update_state("processing", "Rendering Subtitled Video (Original Quality)", 95)
        send_telegram_notification(telegram_token, telegram_chat_id, "🎬 <b>Sal0 Legendas</b>: Renderizando vídeo com legenda embutida (95%)")
        
        # UTILIZA O VÍDEO ORIGINAL enviada pelo usuário em resolução máxima
        render_subtitled_video(
            original_video_path=input_video_path,
            ass_path=final_ass_path,
            output_mp4_path=final_mp4_path
        )

        # Salvar cópia na biblioteca de histórico
        history_dest = os.path.join("/data/library/history", f"{orig_name}.mp4")
        shutil.copy2(final_mp4_path, history_dest)

        update_state("done", "Done", 100, result_file=final_mp4_path)
        logger.info(f"Pipeline do Sal0 Legendas concluído com sucesso para '{orig_name}'!")
        
        processing_lock.release()

        # Envio em segundo plano para o Telegram
        if telegram_token and telegram_chat_id:
            threading.Thread(
                target=send_telegram_video_flow,
                kwargs={
                    "token": telegram_token,
                    "chat_id": telegram_chat_id,
                    "video_path": final_mp4_path,
                    "orig_name": orig_name,
                    "base_url": telegram_base_url,
                    "external_url": telegram_external_url
                },
                daemon=True
            ).start()

    except Exception as e:
        logger.exception("Erro catastrófico no processamento do Sal0 Legendas.")
        if "Cancelado pelo usuário" in str(e):
            update_state("idle", "Idle", 0, error_message="Cancelado pelo usuário.")
        else:
            update_state("error", "Error", 0, error_message=str(e))
            send_telegram_notification(
                telegram_token, telegram_chat_id,
                f"❌ <b>Sal0 Legendas</b>: Falha ao legendá-lo <b>{orig_name}</b>. Erro: {e}"
            )
    finally:
        if processing_lock.locked():
            try:
                processing_lock.release()
            except RuntimeError:
                pass

# =====================================================================
# ENDPOINTS DE PROCESSAMENTO & EDIÇÃO DE LEGENDAS
# =====================================================================
@app.post("/api/process")
def process_video(
    background_tasks: BackgroundTasks,
    video_file: UploadFile = File(None),
    library_video: str = Form(None),
    youtube_url: str = Form(None),
    target_language: str = Form("pt-BR"),
    source_language: str = Form("auto"),
    whisper_model: str = Form("large-v3-turbo"),
    font_size: int = Form(24),
    text_color: str = Form("#FFFFFF"),
    text_position: str = Form("bottom"),
    show_box_background: bool = Form(True),
    export_subtitles_only: bool = Form(False),
    enable_correction: bool = Form(False),
    enable_vad: bool = Form(True),
    lyrics_text: str = Form(None),
    current_user: dict = Depends(get_current_user)
):
    if processing_lock.locked():
        raise HTTPException(status_code=400, detail="Já existe uma tarefa sendo processada no momento.")

    cache_dir = "/data/cache"
    os.makedirs(cache_dir, exist_ok=True)
    input_video_path = None
    orig_filename = "video_legenda"

    if youtube_url and youtube_url.strip():
        orig_filename = "YouTube Video"
    elif video_file and video_file.filename:
        orig_filename = os.path.splitext(video_file.filename)[0]
        ext = os.path.splitext(video_file.filename)[1] or ".mp4"
        input_video_path = os.path.join(cache_dir, f"original_input{ext}")
        with open(input_video_path, "wb") as buffer:
            shutil.copyfileobj(video_file.file, buffer)
        # Salvar cópia na biblioteca de vídeos enviados
        lib_video_dest = os.path.join("/data/library/videos", video_file.filename)
        os.makedirs("/data/library/videos", exist_ok=True)
        shutil.copy2(input_video_path, lib_video_dest)
    elif library_video and library_video.strip():
        lib_path = os.path.join("/data/library/videos", library_video.strip())
        if not os.path.exists(lib_path):
            raise HTTPException(status_code=404, detail=f"Vídeo da biblioteca não encontrado: {library_video}")
        orig_filename = os.path.splitext(library_video)[0]
        ext = os.path.splitext(library_video)[1]
        input_video_path = os.path.join(cache_dir, f"original_input{ext}")
        shutil.copy2(lib_path, input_video_path)
    else:
        raise HTTPException(status_code=400, detail="Por favor, envie um arquivo de vídeo/áudio ou selecione um item da biblioteca.")

    update_state("processing", "Starting Pipeline", 5, original_filename=orig_filename, target_language=target_language)

    background_tasks.add_task(
        run_pipeline,
        input_video_path=input_video_path,
        target_language=target_language,
        source_language=source_language,
        whisper_model=whisper_model,
        font_size=font_size,
        text_color=text_color,
        text_position=text_position,
        show_box_background=show_box_background,
        export_subtitles_only=export_subtitles_only,
        enable_correction=enable_correction,
        enable_vad=enable_vad,
        lyrics_text=lyrics_text,
        youtube_url=youtube_url
    )

    return {"status": "started", "original_filename": orig_filename}

@app.post("/api/cancel")
def cancel_process(current_user: dict = Depends(get_current_user)):
    pm.cancel_event.set()
    update_state("idle", "Idle", 0, error_message="Cancelamento solicitado.")
    return {"status": "cancelling"}

@app.get("/api/segments_to_edit")
def get_segments_to_edit(current_user: dict = Depends(get_current_user)):
    return segments_to_edit

@app.post("/api/continue_process")
def continue_process(edited_segments: list[dict], current_user: dict = Depends(get_current_user)):
    global segments_to_edit
    segments_to_edit = edited_segments
    correction_event.set()
    return {"status": "continuing"}

@app.get("/api/download")
def download_file(current_user: dict = Depends(get_current_user)):
    file_path = "/data/output/final_subtitled.mp4"
    if not os.path.exists(file_path):
        raise HTTPException(status_code=404, detail="Vídeo final legendado não encontrado.")
    with state_lock:
        orig_name = state.get("original_filename", "video_legenda")
    return FileResponse(file_path, media_type="video/mp4", filename=f"{orig_name}_legendado.mp4")

@app.get("/api/subtitles/download/{fmt}/{filename}")
def download_subtitle_file(fmt: str, filename: str, current_user: dict = Depends(get_current_user)):
    sub_dir = "/data/library/subtitles"
    file_path = os.path.join(sub_dir, filename)
    if not os.path.exists(file_path):
        raise HTTPException(status_code=404, detail="Arquivo de legenda não encontrado.")
    media_types = {
        "srt": "application/x-subrip",
        "vtt": "text/vtt",
        "ass": "text/plain",
        "txt": "text/plain"
    }
    return FileResponse(file_path, media_type=media_types.get(fmt, "text/plain"), filename=filename)

# =====================================================================
# ENDPOINTS DA BIBLIOTECA (VIDEOS, SUBTITLES, HISTORY)
# =====================================================================
@app.get("/api/library")
def get_library(current_user: dict = Depends(get_current_user)):
    def list_dir_files(dir_path):
        if not os.path.exists(dir_path):
            return []
        items = []
        for f in sorted(os.listdir(dir_path), reverse=True):
            fpath = os.path.join(dir_path, f)
            if os.path.isfile(fpath):
                items.append({
                    "filename": f,
                    "size_mb": round(os.path.getsize(fpath) / (1024 * 1024), 2)
                })
        return items

    return {
        "videos": list_dir_files("/data/library/videos"),
        "subtitles": list_dir_files("/data/library/subtitles"),
        "history": list_dir_files("/data/library/history")
    }

@app.put("/api/library/{section}/rename")
def rename_library_file(section: str, data: dict, current_user: dict = Depends(get_current_user)):
    if section not in ["videos", "subtitles", "history"]:
        raise HTTPException(status_code=400, detail="Seção da biblioteca inválida.")
    
    old_name = data.get("old_filename")
    new_name = data.get("new_filename")
    if not old_name or not new_name:
        raise HTTPException(status_code=400, detail="Nomes inválidos.")

    dir_path = f"/data/library/{section}"
    old_path = os.path.join(dir_path, old_name)
    new_path = os.path.join(dir_path, new_name)

    if not os.path.exists(old_path):
        raise HTTPException(status_code=404, detail="Arquivo original não encontrado.")
    if os.path.exists(new_path):
        raise HTTPException(status_code=400, detail="Já existe um arquivo com esse novo nome.")

    os.rename(old_path, new_path)
    return {"status": "success", "new_filename": new_name}

@app.delete("/api/library/{section}/{filename}")
def delete_library_file(section: str, filename: str, current_user: dict = Depends(get_current_user)):
    if section not in ["videos", "subtitles", "history"]:
        raise HTTPException(status_code=400, detail="Seção inválida.")
    file_path = os.path.join(f"/data/library/{section}", filename)
    if os.path.exists(file_path):
        os.remove(file_path)
        return {"status": "success"}
    raise HTTPException(status_code=404, detail="Arquivo não encontrado.")

@app.get("/api/cache_info")
def get_cache_info(current_user: dict = Depends(get_current_user)):
    proxy_path = "/data/cache/proxy_video.mp4"
    orig_path = "/data/cache/original_input.mp4"
    has_proxy = os.path.exists(proxy_path)
    has_orig = os.path.exists(orig_path)
    return {"has_cache": has_proxy or has_orig, "has_proxy": has_proxy}

@app.get("/api/cache/video")
def get_cache_video(token: str = Query(None), current_user: dict = Depends(get_current_user)):
    proxy_path = "/data/cache/proxy_video.mp4"
    if os.path.exists(proxy_path):
        return FileResponse(proxy_path, media_type="video/mp4")
    
    # Procurar original input no cache
    cache_dir = "/data/cache"
    for f in os.listdir(cache_dir):
        if f.startswith("original_input"):
            return FileResponse(os.path.join(cache_dir, f))
            
    raise HTTPException(status_code=404, detail="Vídeo de cache não encontrado.")
