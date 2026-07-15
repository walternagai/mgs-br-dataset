"""Logging, sinais e estado de shutdown compartilhados pelo pipeline."""

import logging
import signal
import sys
import threading
from pathlib import Path

LOG_DIR = Path("logs")
_LOG_FMT = logging.Formatter("%(asctime)s [%(levelname)s] %(message)s")

logger = logging.getLogger("mgsbr")
logger.setLevel(logging.DEBUG)
logger.addHandler(logging.NullHandler())

# Evento global de shutdown gracioso: setado por SIGTERM/SIGINT e consultado
# pelos workers entre requisições.
shutdown_requested = threading.Event()

_console_handler: logging.StreamHandler | None = None


def setup_logging(verbose: bool = False, log_dir: Path = LOG_DIR) -> None:
    """Anexa handlers de console (WARNING, ou DEBUG com --verbose) e arquivo (DEBUG).

    Idempotente: chamadas subsequentes apenas ajustam o nível do console.
    """
    global _console_handler
    if _console_handler is None:
        _console_handler = logging.StreamHandler(sys.stdout)
        _console_handler.setFormatter(_LOG_FMT)
        logger.addHandler(_console_handler)

        log_dir.mkdir(exist_ok=True)
        file_handler = logging.FileHandler(log_dir / "adapt_dataset.log", encoding="utf-8")
        file_handler.setLevel(logging.DEBUG)
        file_handler.setFormatter(_LOG_FMT)
        logger.addHandler(file_handler)

    _console_handler.setLevel(logging.DEBUG if verbose else logging.WARNING)


def _handle_signal(signum: int, frame) -> None:
    sig_name = signal.Signals(signum).name
    logger.warning("Sinal %s recebido — finalizando graciosamente...", sig_name)
    print(f"\n⚠  [{sig_name}] Finalizando — aguarde as requisições em andamento...")
    shutdown_requested.set()


def install_signal_handlers() -> None:
    signal.signal(signal.SIGTERM, _handle_signal)
    signal.signal(signal.SIGINT, _handle_signal)


def interruptible_sleep(seconds: float) -> bool:
    """Dorme até `seconds`; retorna True se o shutdown foi solicitado durante a espera."""
    return shutdown_requested.wait(timeout=seconds)
