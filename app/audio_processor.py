import os
import subprocess
import logging
import process_manager as pm

logger = logging.getLogger("legendas")

def extract_audio(input_file_path: str, output_wav_path: str):
    """
    Extrai o áudio de qualquer vídeo/áudio e o converte para WAV PCM 16kHz mono.
    """
    if not os.path.exists(input_file_path):
        raise FileNotFoundError(f"Arquivo de entrada não encontrado: {input_file_path}")

    cmd = [
        "ffmpeg",
        "-y",
        "-i", input_file_path,
        "-vn",
        "-acodec", "pcm_s16le",
        "-ar", "16000",
        "-ac", "1",
        output_wav_path
    ]

    logger.info(f"Executando extração de áudio: {' '.join(cmd)}")
    proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    pm.set_active_process(proc)

    try:
        stdout, stderr = proc.communicate()
        pm.check_cancelled()

        if proc.returncode != 0:
            logger.error(f"Erro no FFmpeg ao extrair áudio: {stderr}")
            raise RuntimeError(f"Falha na extração de áudio: {stderr}")

        logger.info("Extração de áudio concluída com sucesso.")
    finally:
        pm.clear_active_process()

def create_proxy_video(input_file_path: str, output_proxy_path: str):
    """
    Gera uma versão leve de preview em 480p H.264 do vídeo original.
    Usada APENAS para visualização fluida e rápida no navegador durante a edição.
    O vídeo final embutido utilizará sempre o arquivo original em 100% de sua resolução.
    """
    if not os.path.exists(input_file_path):
        return None

    # Se a entrada for apenas áudio (mp3, wav, flac, etc), não precisa criar proxy
    ext = os.path.splitext(input_file_path)[1].lower()
    if ext in ['.mp3', '.wav', '.flac', '.m4a', '.aac', '.ogg', '.opus']:
        return None

    cmd = [
        "ffmpeg",
        "-y",
        "-i", input_file_path,
        "-vf", "scale=-2:480",
        "-c:v", "libx264",
        "-preset", "veryfast",
        "-crf", "28",
        "-c:a", "aac",
        "-b:a", "96k",
        output_proxy_path
    ]

    logger.info(f"Criando vídeo proxy leve para preview: {' '.join(cmd)}")
    proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    pm.set_active_process(proc)

    try:
        stdout, stderr = proc.communicate()
        pm.check_cancelled()

        if proc.returncode != 0:
            logger.warning(f"Erro ao gerar proxy de vídeo (continuando com original): {stderr}")
            return input_file_path

        logger.info("Vídeo proxy de preview criado com sucesso.")
        return output_proxy_path
    finally:
        pm.clear_active_process()

def download_youtube(url: str, output_dir: str) -> tuple[str, str]:
    """
    Baixa vídeo do YouTube utilizando yt-dlp.
    Retorna (caminho_arquivo, titulo_original).
    """
    import yt_dlp
    os.makedirs(output_dir, exist_ok=True)
    
    ydl_opts = {
        'format': 'bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best',
        'outtmpl': os.path.join(output_dir, 'original_input.%(ext)s'),
        'overwrites': True,
        'noplaylist': True,
        'quiet': True
    }
    
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        logger.info(f"Iniciando download do YouTube: {url}")
        info = ydl.extract_info(url, download=True)
        title = info.get('title', 'Vídeo do YouTube')
        filename = ydl.prepare_filename(info)
        
        # Procurar o arquivo baixado caso a extensão mude
        base = os.path.join(output_dir, 'original_input')
        for ext in ['.mp4', '.mkv', '.webm', '.mov']:
            candidate = base + ext
            if os.path.exists(candidate):
                return candidate, title
                
        if os.path.exists(filename):
            return filename, title
            
    raise RuntimeError("Não foi possível localizar o vídeo baixado do YouTube.")
