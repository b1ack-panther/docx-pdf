import os
from celery import Celery

# Load environment variables (defaults provided for local testing)
BROKER_URL = os.getenv("CELERY_BROKER_URL", "redis://localhost:6379/0")
RESULT_BACKEND = os.getenv("CELERY_RESULT_BACKEND", "redis://localhost:6379/0")

celery_app = Celery(
    "docx_converter",
    broker=BROKER_URL,
    backend=RESULT_BACKEND,
    include=["app.tasks"]  # Crucial: Register the tasks module
)

# Configuration optimization for long-running tasks
celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,
    task_acks_late=True,  # Ensure tasks are not lost if worker crashes
    broker_connection_retry_on_startup=True,
)