"""Background worker entrypoint: `python -m app.workers.main`.
Scale by running more worker processes/containers; domain APIs do not change."""
from rq import Queue, Worker

from app.core.config import get_settings
from app.core.logging import configure_logging, get_logger
from app.workers.queue import get_queue_connection


def main() -> None:
    s = get_settings()
    configure_logging(s.log_level, s.log_json)
    get_logger("worker").info("worker_starting", queue=s.rq_queue_name)
    conn = get_queue_connection()
    Worker([Queue(s.rq_queue_name, connection=conn)], connection=conn).work(with_scheduler=False)


if __name__ == "__main__":
    main()
