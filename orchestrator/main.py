from fastapi import FastAPI
from routers.webhook_router import router as webhook_router

app = FastAPI()

app.include_router(webhook_router)

@app.get("/healthz")
def health():
    return {"status": "ok"}

@app.get("/hetal")
async def hetal():
    return {"hetal": "hiii"}