import os
import logging
from faster_whisper import WhisperModel

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("download_models")

def download_default_models():
    """Baixa o modelo padrão Whisper (large-v3-turbo) no diretório persistente."""
    target_dir = "/data/output/models/whisper"
    os.makedirs(target_dir, exist_ok=True)
    
    models = ["deepdml/faster-whisper-large-v3-turbo"]
    for m in models:
        logger.info(f"Pré-baixando modelo de IA: {m} para {target_dir}")
        try:
            WhisperModel(m, device="cpu", compute_type="int8", download_root=target_dir)
            logger.info(f"Modelo {m} baixado com sucesso.")
        except Exception as e:
            logger.error(f"Erro ao pré-baixar modelo {m}: {e}")

if __name__ == "__main__":
    download_default_models()
