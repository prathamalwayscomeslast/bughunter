from fastapi import FastAPI

app = FastAPI()

@app.get("/healthz")
def health():
    return {"status": "ok"}

@app.post("/webhook")
async def webhook():
    return {"received": True}