import logging
from pathlib import Path


def configure_logging(log_dir: str) -> None:
    root = Path(log_dir).resolve()
    for name in ("frontend", "backend", "jobs"):
        (root / name).mkdir(parents=True, exist_ok=True)
    formatter = logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s")
    for logger_name, path in {"app": root / "backend" / "errors.log", "app.jobs": root / "jobs" / "errors.log", "app.frontend": root / "frontend" / "errors.log"}.items():
        logger = logging.getLogger(logger_name); logger.setLevel(logging.INFO); logger.propagate = False
        if not any(isinstance(handler, logging.FileHandler) and Path(handler.baseFilename) == path for handler in logger.handlers):
            handler = logging.FileHandler(path, encoding="utf-8"); handler.setFormatter(formatter); logger.addHandler(handler)
