# Dapr Service Invocation Demo

This project showcases service-to-service communication using [Dapr](https://dapr.io/) sidecars around two FastAPI applications. An `orders` service invokes the `payments` service through Dapr's HTTP APIs while exporting metrics and traces for observability tooling.

## Project layout

```
.
├── docker-compose.yml           # Orchestrates services, sidecars, and observability stack
├── dapr/                        # Dapr configuration (tracing, access control)
├── services/
│   ├── orders/                  # FastAPI app that calls payments via Dapr invoke
│   └── payments/                # FastAPI app that simulates a payment processor
├── otel/collector.yaml          # OpenTelemetry Collector pipeline feeding Jaeger & Prometheus
└── observability/prometheus.yml # Prometheus scrape configuration for Dapr sidecars
```

## Prerequisites

- Docker and Docker Compose v2+
- Optional: `curl` or a similar HTTP client for testing requests

## Running locally

1. Build and start the stack:
   ```bash
   docker compose up --build
   ```
2. Wait until the FastAPI apps and their Dapr sidecars report as healthy in the logs.
3. Run sample requests (see below) to exercise the service invocation path.

To stop the stack, press `Ctrl+C` and optionally remove containers with `docker compose down`.

## Services and ports

| Component            | Endpoint / Port                | Notes |
| -------------------- | ------------------------------ | ----- |
| Dapr sidecar (orders)| `http://localhost:3500`        | Invoked by clients to reach the `orders` service |
| Dapr sidecar (payments)| `http://localhost:3501`      | Used internally by `orders` to invoke `payments` |
| Orders FastAPI app   | `http://localhost:8001`        | Exposed inside the mesh only (via sidecar) |
| Payments FastAPI app | `http://localhost:8002`        | Exposed inside the mesh only (via sidecar) |
| Prometheus UI        | `http://localhost:9090`        | Metrics explorer |
| Jaeger UI            | `http://localhost:16686`       | Trace viewer |

## Example requests

### Health checks

Use the Dapr sidecars to hit the health endpoints:

```bash
curl http://localhost:3500/v1.0/healthz
curl http://localhost:3501/v1.0/healthz
```

The FastAPI apps themselves expose `/health` behind the sidecars:

```bash
curl http://localhost:3500/v1.0/invoke/orders/method/health
curl http://localhost:3501/v1.0/invoke/payments/method/health
```

### Invoke payments through orders

Call the `orders` service, which forwards to `payments` via Dapr service invocation:

```bash
curl -X POST \
  http://localhost:3500/v1.0/invoke/orders/method/orders/123/charge \
  -H "Content-Type: application/json" \
  -d '{"amount": 45.90}'
```

Expected response (abbreviated):

```json
{
  "invoked": true,
  "payments_response": {
    "status": "charged",
    "data": {
      "order_id": "123",
      "amount": 45.9
    }
  }
}
```

## Observability

- **Tracing:** Dapr publishes spans to the OpenTelemetry Collector, which exports them to Jaeger. Open the UI at `http://localhost:16686` to inspect traces for `orders` and `payments`.
- **Metrics:** The collector aggregates service metrics and exposes them to Prometheus at `http://localhost:9090`. Dapr sidecars also expose `/metrics` endpoints that are scraped by Prometheus.
- **Dashboards:** Import Prometheus metrics into Grafana or another visualization tool if desired (not bundled by default).

## Customization tips

- Adjust Dapr configuration in `dapr/config.yaml` to change tracing or access control behavior.
- Update the FastAPI apps under `services/` to represent your own business logic.
- Extend `docker-compose.yml` with additional services or bind mounts as required.

## Troubleshooting

- Ensure no other process occupies ports `3500-3501`, `50001-50002`, `8889`, `9090`, or `16686`.
- If requests time out, confirm the sidecars are running and that `orders` can resolve the `payments` app ID (`TARGET_APP_ID` environment variable).
- Use `docker compose logs orders` or `docker compose logs payments` to inspect application logs.

