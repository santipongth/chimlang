"""Container health check for the Celery worker heartbeat."""

from core.tasks import worker_available

if __name__ == "__main__":
    raise SystemExit(0 if worker_available() else 1)
