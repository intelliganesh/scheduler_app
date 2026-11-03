import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path


LOG_FORMAT = "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s"


class ReadableFormatter(logging.Formatter):
    """Keep multiline exception details visually attached to their entry."""

    def formatException(self, exc_info):
        trace = super().formatException(exc_info)
        return "\n".join(f"    | {line}" for line in trace.splitlines())

    def formatStack(self, stack_info):
        stack = super().formatStack(stack_info)
        return "\n".join(f"    | {line}" for line in stack.splitlines())

    def format(self, record):
        # The handler adds its normal newline after this string; the extra one
        # creates a clear separator between consecutive events.
        return super().format(record) + "\n"


def configure_logging(log_dir: str, file_name: str = "application.log") -> None:
    """Configure one readable, rotating log for all application components."""
    root = Path(log_dir).resolve()
    root.mkdir(parents=True, exist_ok=True)
    path = (root / file_name).resolve()
    if path.parent != root:
        raise ValueError("LOG_FILE_NAME must be a file name inside LOG_DIR.")

    formatter = ReadableFormatter(LOG_FORMAT, datefmt="%Y-%m-%d %H:%M:%S")
    app_logger = logging.getLogger("app")
    app_logger.setLevel(logging.INFO)
    app_logger.propagate = False
    for handler in list(app_logger.handlers):
        app_logger.removeHandler(handler)
        handler.close()
    handler = RotatingFileHandler(path, maxBytes=10 * 1024 * 1024, backupCount=5, encoding="utf-8")
    handler.setFormatter(formatter)
    app_logger.addHandler(handler)

    # Component loggers inherit the same handler, keeping one chronological file.
    for logger_name in ("app.jobs", "app.frontend"):
        logger = logging.getLogger(logger_name)
        logger.setLevel(logging.INFO)
        logger.propagate = True
        for component_handler in list(logger.handlers):
            logger.removeHandler(component_handler)
            component_handler.close()
