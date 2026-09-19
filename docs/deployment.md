# Deployment

**Prerequisites:** [API](api.md) and [Persistence](persistence.md).

---

Deploy FluxRules as a service for production rule evaluation.

## Minimal deployment (development)

```python
from fluxrules.api.app import create_app
import uvicorn

app = create_app()

if __name__ == "__main__":
    # Single worker, no persistence
    uvicorn.run(
        app,
        host="127.0.0.1",
        port=8000,
        workers=1,
    )
```

## Production deployment (Docker)

```dockerfile
FROM python:3.11-slim

WORKDIR /app

# Install FluxRules with all extras
RUN pip install fluxrules[all]

# Copy rules (if stored as files)
COPY rules/ /app/rules/

# Start API server
CMD ["python", "-m", "fluxrules.api.app"]
```

**Run:**
```bash
docker run -p 8000:8000 -e FLUXRULES_ENV=prod fluxrules:latest
```

## Production configuration

Set environment variables for production:

```bash
# Database
export FLUXRULES_ENV=prod
export FLUXRULES_DB_URL=postgresql://user:pass@db.example.com/fluxrules

# API
export API_HOST=0.0.0.0
export API_PORT=8000
export API_WORKERS=4

# Optional: Prometheus metrics
export OTEL_ENABLED=true
export OTEL_EXPORTER_OTLP_ENDPOINT=http://otel-collector:4317
```

## Scaling

For high-throughput production:

```python skip
import uvicorn

app = create_app()

uvicorn.run(
    app,
    host="0.0.0.0",
    port=8000,
    workers=4,  # CPU cores × 2-4
)
```

Place behind a load balancer (nginx, AWS ALB, etc.):

```nginx
upstream fluxrules {
    server 127.0.0.1:8000;
    server 127.0.0.1:8001;
    server 127.0.0.1:8002;
    server 127.0.0.1:8003;
}

server {
    listen 80;
    server_name rules.example.com;

    location /api/ {
        proxy_pass http://fluxrules;
        proxy_set_header Host $host;
    }
}
```

## Health monitoring

Use the health endpoint for readiness checks:

```bash
curl http://localhost:8000/health
# {"status": "healthy", "version": "0.0.1"}
```

Add to Docker/K8s liveness probes:

```yaml
livenessProbe:
  httpGet:
    path: /health
    port: 8000
  initialDelaySeconds: 5
  periodSeconds: 10
```

---

## Next Steps

- **Security** — See [Security](security.md) for authentication & authorization
- **Observability** — See [Observability](observability.md) for monitoring
- **Troubleshooting** — See [Troubleshooting](troubleshooting.md) for common issues
