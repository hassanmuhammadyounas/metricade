"""
Entry point — starts subscriber thread, then serves health endpoint.
"""
import threading
import logging
import uvicorn

from .subscriber import run_subscriber
from .health.http_health import create_app

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
)
logger = logging.getLogger(__name__)


def main():
    logger.info("Starting feature worker")

    # Start Redis stream subscriber in background thread
    subscriber_thread = threading.Thread(target=run_subscriber, daemon=True, name="subscriber")
    subscriber_thread.start()
    logger.info("Subscriber thread started")

    # Serve health endpoint on port 8080 (Fly.io internal only)
    app = create_app()
    uvicorn.run(app, host="0.0.0.0", port=8080, log_level="warning")


if __name__ == "__main__":
    main()
