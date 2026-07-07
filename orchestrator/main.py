import logging

from fastapi import FastAPI

from util.log import setup_logging

setup_logging()
logger = logging.getLogger(__name__)

app = FastAPI()

@app.get("/healthz")
def health():
    return {"status": "ok"}

@app.get("/hetal")
async def hetal():
    return {"hetal": "hiii"}