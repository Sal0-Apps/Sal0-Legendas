import os
import subprocess
import logging
import process_manager as pm

logger = logging.getLogger("legendas")

def render_subtitled_video(
    original_video_path: str,
    ass_path: str,
    output_mp4_path: str
):
    """
    Renderiza o vídeo final com as legendas gravadas diretamente na imagem (hardsub).
    UTILIZA SEMPRE O VÍDEO ORIGINAL como fonte de imagem/áudio para manter 100%
    da qualidade, resolução nativa (1080p, 4K), bitrate e framerate originais do envio.
    """
    if not os.path.exists(original_video_path):
        raise FileNotFoundError(f"Vídeo original não encontrado: {original_video_path}")
    if not os.path.exists(ass_path):
        raise FileNotFoundError(f"Arquivo de legenda ASS não encontrado: {ass_path}")

    os.makedirs(os.path.dirname(output_mp4_path), exist_ok=True)

    # Escapar o caminho do arquivo ASS para sintaxe do filtro do FFmpeg
    safe_ass_path = ass_path.replace("\\", "/").replace(":", "\\:")

    cmd = [
        "ffmpeg",
        "-y",
        "-i", original_video_path,
        "-vf", f"subtitles='{safe_ass_path}'",
        "-c:v", "libx264",
        "-preset", "medium",
        "-crf", "18",  # Qualidade de vídeo visualmente transparente / próxima da perfeita
        "-c:a", "copy",  # Copia o fluxo de áudio original sem perda
        output_mp4_path
    ]

    logger.info(f"Sal0 Legendas - Executando renderização de vídeo final no arquivo ORIGINAL: {' '.join(cmd)}")
    proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    pm.set_active_process(proc)

    try:
        stdout, stderr = proc.communicate()
        pm.check_cancelled()

        if proc.returncode != 0:
            logger.error(f"Erro no FFmpeg durante renderização do vídeo: {stderr}")
            raise RuntimeError(f"Falha na renderização de vídeo: {stderr}")

        logger.info(f"Vídeo com legenda embutida renderizado com sucesso mantendo a qualidade original: {output_mp4_path}")
    finally:
        pm.clear_active_process()
