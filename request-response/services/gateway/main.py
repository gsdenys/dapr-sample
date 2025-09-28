import os
import json
import uuid
import asyncio
import logging
from typing import Dict, Any
import httpx
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Body
from fastapi.responses import JSONResponse
from prometheus_fastapi_instrumentator import Instrumentator


DAPR_HTTP = os.getenv("DAPR_HTTP", "http://localhost:3500")
PUBSUB = os.getenv("PUBSUB", "messagebus")
REQUEST_TOPIC = os.getenv("REQUEST_TOPIC", "requests")
REPLY_TOPIC = os.getenv("REPLY_TOPIC", "responses")
REQUEST_TIMEOUT_SEC = float(os.getenv("REQUEST_TIMEOUT_SEC", "15"))

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("gateway")

app = FastAPI(title="gateway")

# Expose Prometheus metrics at /metrics
Instrumentator().instrument(app).expose(app, endpoint="/metrics", include_in_schema=False)

@app.get("/health")
async def health():
    return {"ok": True, "service": "orders"}

# Mapa de correlationId -> Future para sincronizar request-reply
pending: Dict[str, asyncio.Future] = {}
pending_lock = asyncio.Lock()

@app.get("/dapr/subscribe")
def dapr_subscribe():
    # Informa ao Dapr que este app quer receber mensagens do tópico de respostas
    return JSONResponse([
        {"pubsubname": PUBSUB, "topic": REPLY_TOPIC, "route": "/responses"}
    ])

@app.post("/responses")
async def responses_handler(envelope: Dict[str, Any] = Body(...)):
    """
    Handler chamado pelo Dapr com a entrega do tópico 'responses'.
    Envelope esperado (no campo 'data'):
    {
      "correlationId": "...",
      "result": {...}
    }
    """
    data = envelope.get("data") or envelope  # Dapr manda como CloudEvent: data=...
    corr = data.get("correlationId")
    async with pending_lock:
        fut = pending.get(corr)
        if fut and not fut.done():
            fut.set_result(data.get("result"))
            # limpeza tardia — remoção será feita pelo waiter
    # Dapr requer 200 para marcar como "processado"
    return {"status": "OK"}

@app.websocket("/ws")
async def websocket_endpoint(ws: WebSocket):
    await ws.accept()
    logger.info("WebSocket client connected")
    try:
        while True:
            try:
                raw = await ws.receive_text()
            except WebSocketDisconnect:
                logger.info("WebSocket client disconnected while waiting for message")
                break
            except Exception as e:  # noqa
                logger.exception("Erro recebendo mensagem do WebSocket")
                await ws.send_text(json.dumps({"error": "receive_failed", "detail": str(e)}))
                continue

            # Aceita texto JSON ou string simples
            try:
                payload = json.loads(raw)
            except json.JSONDecodeError:
                payload = {"message": raw}

            corr = str(uuid.uuid4())
            fut: asyncio.Future = asyncio.get_event_loop().create_future()
            async with pending_lock:
                pending[corr] = fut
            logger.info("Dispatching correlationId=%s payload_size=%d", corr, len(raw))

            envelope = {
                "correlationId": corr,
                "replyTopic": REPLY_TOPIC,
                "payload": payload
            }
            try:
                async with httpx.AsyncClient(timeout=REQUEST_TIMEOUT_SEC) as client:
                    pub_url = f"{DAPR_HTTP}/v1.0/publish/{PUBSUB}/{REQUEST_TOPIC}"
                    r = await client.post(pub_url, json=envelope)
                    r.raise_for_status()
            except Exception as e:  # noqa
                logger.exception("Falha ao publicar para Dapr correlationId=%s", corr)
                async with pending_lock:
                    pending.pop(corr, None)
                await ws.send_text(json.dumps({"error": "publish_failed", "detail": str(e)}))
                continue

            try:
                result = await asyncio.wait_for(fut, timeout=REQUEST_TIMEOUT_SEC)
            except asyncio.TimeoutError:
                logger.warning("Timeout aguardando resposta correlationId=%s", corr)
                result = {"error": "timeout waiting for worker response"}
            finally:
                async with pending_lock:
                    pending.pop(corr, None)

            await ws.send_text(json.dumps(result))
    finally:
        logger.info("WebSocket connection closed")