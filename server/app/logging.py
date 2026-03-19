import logging
import os

from app.config import Settings

LOG_FORMAT = "%(asctime)s %(levelname)s %(name)s: %(message)s"
LOG_FILE = "dev.log"


def configure_logging(settings: Settings, log_dir: str = "logs") -> None:
    root = logging.getLogger()
    root.setLevel(logging.INFO)
    root.handlers.clear()

    formatter = logging.Formatter(LOG_FORMAT)

    console = logging.StreamHandler()
    console.setFormatter(formatter)
    root.addHandler(console)

    if settings.environment == "development":
        os.makedirs(log_dir, exist_ok=True)
        file_handler = logging.FileHandler(os.path.join(log_dir, LOG_FILE), mode="w")
        file_handler.setFormatter(formatter)
        root.addHandler(file_handler)
