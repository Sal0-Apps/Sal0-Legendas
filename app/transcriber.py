import gc
import os
import logging
from faster_whisper import WhisperModel

logger = logging.getLogger("legendas")

def resolve_whisper_repo(model_size: str) -> str:
    """Retorna o repositório oficial do HuggingFace para o modelo Whisper desejado."""
    m = model_size.lower().strip()
    if m == "large-v3-turbo":
        return "deepdml/faster-whisper-large-v3-turbo"
    elif m == "large-v3":
        return "Systran/faster-whisper-large-v3"
    elif m == "medium":
        return "Systran/faster-whisper-medium"
    elif m == "small":
        return "Systran/faster-whisper-small"
    elif m == "tiny":
        return "Systran/faster-whisper-tiny"
    return m

def get_model_local_dir(model_size: str) -> str:
    """Localiza o diretório local exato com os pesos do modelo Whisper."""
    key = model_size.lower().strip()
    min_size_bytes = 300 * 1024 * 1024  # 300 MB
    if "tiny" in key:
        min_size_bytes = 30 * 1024 * 1024
    elif "small" in key:
        min_size_bytes = 150 * 1024 * 1024

    if key == "large-v3-turbo":
        match_fn = lambda name: "turbo" in name or "large-v3-turbo" in name
    elif key == "large-v3":
        match_fn = lambda name: "large-v3" in name and "turbo" not in name
    elif key == "medium":
        match_fn = lambda name: "medium" in name
    elif key == "small":
        match_fn = lambda name: "small" in name
    elif key == "tiny" or key == "base":
        match_fn = lambda name: "tiny" in name or "base" in name
    else:
        match_fn = lambda name: key in name

    search_roots = [
        "/data/output/models/whisper",
        "/root/.cache/huggingface/hub",
        "/root/.cache/whisper",
        os.path.expanduser("~/.cache/huggingface/hub"),
        os.path.expanduser("~/.cache/whisper")
    ]

    for root in search_roots:
        if not os.path.exists(root):
            continue
        try:
            for entry in os.listdir(root):
                entry_path = os.path.join(root, entry)
                if os.path.isdir(entry_path) and match_fn(entry.lower()):
                    for r, dirs, files in os.walk(entry_path):
                        for f in files:
                            if f in ["model.bin", "model.safetensors", "pytorch_model.bin", "model.pt"]:
                                fpath = os.path.join(r, f)
                                try:
                                    if os.path.getsize(fpath) >= min_size_bytes:
                                        return r
                                except Exception:
                                    pass
        except Exception as e:
            logger.warning(f"Erro ao pesquisar diretório {root}: {e}")
    return None

def is_model_downloaded(model_size: str) -> bool:
    """Verifica se o modelo Whisper está verdadeiramente baixado e presente em disco."""
    local_dir = get_model_local_dir(model_size)
    return local_dir is not None

def transcribe_audio(
    audio_path: str,
    model_size: str = "large-v3-turbo",
    initial_prompt: str = None,
    quality_mode: str = "standard",
    cpu_threads: int = None,
    enable_vad: bool = True
) -> tuple[list[dict], str]:
    """
    Transcreve áudios de QUALQUER DURAÇÃO (sem limite de tempo) com Faster-Whisper e Silero VAD.
    Retorna (lista_de_segmentos, idioma_detectado).
    """
    if not cpu_threads or cpu_threads <= 0:
        total_cpus = os.cpu_count() or 4
        cpu_threads = max(1, total_cpus - 1)

    is_max_quality = (quality_mode == "max_quality" or "max" in str(quality_mode).lower())
    compute_type = "float32" if is_max_quality else "int8"
    beam_size = 10 if is_max_quality else 5

    logger.info(
        f"Sal0 Legendas - Iniciando transcrição Faster-Whisper: Modelo={model_size}, "
        f"Threads={cpu_threads}, Compute={compute_type}, BeamSize={beam_size}, SileroVAD={enable_vad}"
    )

    whisper_download_dir = "/data/output/models/whisper"
    os.makedirs(whisper_download_dir, exist_ok=True)

    model = None

    # Etapa 1: Tentar carregar pelo caminho direto da pasta local contendo os pesos
    local_dir = get_model_local_dir(model_size)
    if local_dir:
        try:
            logger.info(f"Carregando modelo Whisper '{model_size}' do diretório local: {local_dir}")
            model = WhisperModel(
                local_dir,
                device="cpu",
                compute_type=compute_type,
                cpu_threads=cpu_threads
            )
        except Exception as e_local:
            logger.warning(f"Falha ao carregar diretamente do diretório {local_dir}: {e_local}")
            model = None

    # Etapa 2: Se não carregou do diretório local direto, tentar pelo repositório estrito local
    if model is None:
        try:
            logger.info(f"Tentando carregar '{repo_id}' via HuggingFace local...")
            model = WhisperModel(
                repo_id,
                device="cpu",
                compute_type=compute_type,
                cpu_threads=cpu_threads,
                download_root=whisper_download_dir,
                local_files_only=True
            )
        except Exception as ex_local_repo:
            logger.warning(f"O modelo '{repo_id}' não está completamente snapshot-cacheado no servidor ({ex_local_repo}). Baixando repositório oficial...")
            # Etapa 3: Baixar arquivos ausentes do repositório oficial do HuggingFace (local_files_only=False)
            try:
                model = WhisperModel(
                    repo_id,
                    device="cpu",
                    compute_type=compute_type,
                    cpu_threads=cpu_threads,
                    download_root=whisper_download_dir,
                    local_files_only=False
                )
                logger.info(f"Download do modelo '{repo_id}' concluído com sucesso e salvo em {whisper_download_dir}!")
            except Exception as ex_online:
                logger.error(f"Erro no download oficial de '{repo_id}': {ex_online}")
                # Etapa 4: Fallback final para medium
                if model_size != "medium":
                    logger.warning("Tentando fallback de emergência para o modelo 'medium'...")
                    med_dir = get_model_local_dir("medium")
                    if med_dir:
                        model = WhisperModel(med_dir, device="cpu", compute_type="int8", cpu_threads=cpu_threads)
                    else:
                        model = WhisperModel("Systran/faster-whisper-medium", device="cpu", compute_type="int8", cpu_threads=cpu_threads, download_root=whisper_download_dir, local_files_only=False)
                else:
                    raise RuntimeError(f"Erro ao carregar o modelo Whisper '{model_size}': {ex_online}")

    # VAD Parameters para vídeos longos sem limite de tempo
    vad_options = None
    if enable_vad:
        vad_options = dict(
            threshold=0.5,
            min_speech_duration_ms=250,
            max_speech_duration_s=15,  # Segmenta estrofes longas automaticamente
            min_silence_duration_ms=400,
            speech_pad_ms=200
        )

    segments_raw, info = model.transcribe(
        audio_path,
        beam_size=beam_size,
        vad_filter=enable_vad,
        vad_parameters=vad_options,
        initial_prompt=initial_prompt,
        word_timestamps=True
    )

    detected_language = info.language or "unknown"
    logger.info(f"Idioma original detectado pelo Whisper: {detected_language} (Probabilidade: {info.language_probability:.2f})")

    segments_list = []
    for idx, seg in enumerate(segments_raw):
        clean_text = seg.text.strip()
        if not clean_text:
            continue
        words_info = []
        if seg.words:
            for w in seg.words:
                words_info.append({
                    "start": round(w.start, 2),
                    "end": round(w.end, 2),
                    "word": w.word
                })

        segments_list.append({
            "id": idx + 1,
            "start": round(seg.start, 2),
            "end": round(seg.end, 2),
            "text": clean_text,
            "original_text": clean_text,
            "translated_text": clean_text,
            "words": words_info
        })

    # Liberar memória do modelo
    del model
    gc.collect()

    logger.info(f"Transcrição concluída com sucesso: {len(segments_list)} segmentos extraídos.")
    return segments_list, detected_language
