from fastapi import FastAPI, Request
from prometheus_fastapi_instrumentator import Instrumentator

app = FastAPI()

Instrumentator().instrument(app).expose(app, endpoint="/metrics")

@app.get("/health")
def health():
    return {"ok": True, "service": "payments"}

@app.post("/charge")
async def charge(req: Request):
    data = await req.json()

    return {"status": "charged", "data": data}