import os
import logging
from faster_whisper import WhisperModel

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("download_models")

def download_default_models():
    """Baixa o modelo padrão Whisper Large v3 Turbo pré-instalado dentro da imagem Docker."""
    target_dirs = [
        "/root/.cache/huggingface/hub",
        "/data/output/models/whisper"
    ]
    model_id = "deepdml/faster-whisper-large-v3-turbo"

    for target_dir in target_dirs:
        os.makedirs(target_dir, exist_ok=True)
        logger.info(f"Pré-instalando modelo Whisper Large v3 Turbo em: {target_dir}")
        try:
            WhisperModel(model_id, device="cpu", compute_type="int8", download_root=target_dir)
            logger.info(f"Modelo {model_id} instalado com sucesso em {target_dir}.")
        except Exception as e:
            logger.error(f"Aviso ao baixar modelo {model_id} em {target_dir}: {e}")

if __name__ == "__main__":
    download_default_models()
