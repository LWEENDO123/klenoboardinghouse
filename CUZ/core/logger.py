# CUZ/ADMIN/core/logger
import google.cloud.logging
import logging

client = google.cloud.logging.Client()
client.setup_logging()

def log_to_cloud(category: str, severity: str, message: str, metadata: dict = None):
    logging.log(
        getattr(logging, severity.upper(), logging.INFO),
        f"[{category}] {message}",
        extra={"metadata": metadata or {}}
    )
