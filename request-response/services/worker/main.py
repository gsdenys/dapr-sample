import os
import json
from typing import Dict, Any
import httpx
from fastapi import FastAPI, Body
from fastapi.responses import JSONResponse
from prometheus_fastapi_instrumentator import Instrumentator

DAPR_HTTP = os.getenv("DAPR_HTTP", "http://localhost:3500")
PUBSUB = os.getenv("PUBSUB", "messagebus")
REQUEST_TOPIC = os.getenv("REQUEST_TOPIC", "requests")

app = FastAPI(title="worker")

# Expose Prometheus metrics
Instrumentator().instrument(app).expose(app, endpoint="/metrics", include_in_schema=False)

@app.get("/health")
async def health():
    return {"ok": True, "service": "worker"}

@app.get("/dapr/subscribe")
def dapr_subscribe():
    # Informa ao Dapr que este app quer receber mensagens do tópico de requisições
    return JSONResponse([
        {"pubsubname": PUBSUB, "topic": REQUEST_TOPIC, "route": "/requests"}
    ])

@app.post("/requests")
async def request_handler(envelope: Dict[str, Any] = Body(...)):
    """
    Envelope esperado (no campo 'data'):
    {
      "correlationId": "...",
      "replyTopic": "responses",
      "payload": {...}
    }
    """
    data = envelope.get("data") or envelope
    corr = data["correlationId"]
    reply_topic = data["replyTopic"]
    payload = data.get("payload", {})

    # ------ Sua lógica de negócio aqui ------
    # Exemplo: eco + enrich
    result = {
        "ok": True,
        "echo": payload,
        "processedBy": "worker-1"
    }
    # ----------------------------------------

    # publica resposta no tópico de reply informado
    async with httpx.AsyncClient(timeout=10) as client:
        pub_url = f"{DAPR_HTTP}/v1.0/publish/{PUBSUB}/{reply_topic}"
        await client.post(pub_url, json={"correlationId": corr, "result": result})

    # Dapr espera 200 pra confirmar entrega
    return {"status": "OK"}