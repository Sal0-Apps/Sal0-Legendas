import threading
import logging

logger = logging.getLogger("legendas")

cancel_event = threading.Event()
active_process = None

def set_active_process(proc):
    global active_process
    active_process = proc

def clear_active_process():
    global active_process
    active_process = None

def check_cancelled():
    if cancel_event.is_set():
        if active_process:
            try:
                logger.info("Encerrando processo filho ativo devido ao cancelamento...")
                active_process.kill()
            except Exception as e:
                logger.error(f"Erro ao encerrar processo: {e}")
            clear_active_process()
        raise RuntimeError("Cancelado pelo usuário.")
