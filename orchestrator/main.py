from fastapi import FastAPI

app = FastAPI()

@app.get("/healthz")
def health():
    return {"status": "ok"}

@app.post("/webhook")
async def webhook():
    return {"received": True}

@app.get("/hetal")
async def hetal():
    return {"hetal": "hiii"}