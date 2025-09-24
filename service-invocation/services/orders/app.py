from fastapi import FastAPI
import httpx, os
from prometheus_fastapi_instrumentator import Instrumentator

app = FastAPI()

Instrumentator().instrument(app).expose(app, endpoint="/metrics")

DAPR_HTTP = os.getenv("DAPR_HTTP", "http://localhost:3500")
TARGET_APP_ID = os.getenv("TARGET_APP_ID", "payments")

@app.get("/health")
def health():
    return {"ok": True, "service": "orders"}

@app.post("/orders/{order_id}/charge")
def charge(order_id: str, amount: float = 10.0):
    url = f"{DAPR_HTTP}/v1.0/invoke/{TARGET_APP_ID}/method/charge"
    payload = {"order_id": order_id, "amount": amount}
    r = httpx.post(url, json=payload, timeout=10)
    r.raise_for_status()
    return {"invoked": True, "payments_response": r.json()}