# metadata-sync worker

The worker is deliberately built from the **same codebase and image** as the API so it shares
models, the Salesforce connector and the metadata service (no duplicated logic).

- Entrypoint: `services/api/app/workers/main.py` (`python -m app.workers.main`)
- Jobs: `services/api/app/workers/jobs.py`
- Queue: Redis (RQ), queue name `metadata-sync` (`RQ_QUEUE_NAME`)
- Domain logic: `services/api/app/services/metadata_service.py`

Scaling = run more worker containers. If you later move to SQS/Celery/Temporal, only
`metadata_service.queue_sync()` and this entrypoint change; the domain service and API do not.
