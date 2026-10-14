# Terraform (introduce when cloud deployment begins — Step 16)

Suggested AWS layout (swap equivalents for Azure/GCP):

| Concern | Local prototype | Managed production |
|---|---|---|
| PostgreSQL | `postgres` container | Amazon RDS / Aurora PostgreSQL (Multi-AZ, encrypted, PITR backups) |
| Redis | `redis` container | Amazon ElastiCache for Redis |
| Secrets | `.env` + encrypted `credential_secrets` table | AWS Secrets Manager (implement `SecretStore`), KMS |
| Containers | Docker Compose | ECS Fargate services: `api`, `worker`, `mcp`, `web` (same images) |
| Ingress | localhost ports | ALB + ACM TLS, WAF |
| Telemetry | console / local collector | OTLP → CloudWatch / Datadog / Grafana |
| Object storage | not used | S3 (exports, large audit payloads) |

Modules to create: `network`, `database`, `cache`, `secrets`, `ecs-service` (reused 4×), `observability`.
