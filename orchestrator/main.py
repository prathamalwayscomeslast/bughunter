import logging
from contextlib import asynccontextmanager

from arq import create_pool
from arq.connections import RedisSettings
from fastapi import FastAPI

from config import REDIS_URL
from routers.webhook_router import router as webhook_router
from util.log import setup_logging

setup_logging()
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Runs once on startup / once on shutdown.
    Creates a single shared ARQ Redis pool and stores it on app.state.redis.
    All request handlers and services read from app.state.redis — we never
    create a new pool per request.
    """
    logger.info("Connecting to Redis…")
    app.state.redis = await create_pool(RedisSettings.from_dsn(REDIS_URL))
    logger.info("Redis pool ready")
    yield
    logger.info("Closing Redis pool…")
    await app.state.redis.close()


app = FastAPI(lifespan=lifespan)
app.include_router(webhook_router)


@app.get("/healthz")
def health():
    return {"status": "ok"}
