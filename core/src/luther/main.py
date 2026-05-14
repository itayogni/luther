import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Header, HTTPException
from pydantic import BaseModel

from luther.brain import think
from luther.config import settings
from luther.db import init_db

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    try:
        await init_db()
    except Exception as exc:  # pragma: no cover
        logger.warning("DB init skipped (no connection): %s", exc)
    yield


app = FastAPI(title="Luther Core", lifespan=lifespan)


class IncomingMessage(BaseModel):
    sender: str
    body: str
    message_type: str
    timestamp: int
    group_jid: str | None = None
    media_url: str | None = None


class OutgoingReply(BaseModel):
    sender: str
    reply: str


@app.get("/health")
async def health():
    return {"status": "ok", "service": "luther-core"}


@app.post("/webhook/message")
async def receive_message(
    msg: IncomingMessage,
    x_gateway_secret: str = Header(None),
) -> OutgoingReply:
    if x_gateway_secret != settings.gateway_secret:
        raise HTTPException(status_code=401, detail="Invalid gateway secret")

    logger.info("Message from %s: %s", msg.sender, msg.body[:60])

    reply_text = await think(sender=msg.sender, message=msg.body, media_url=msg.media_url)

    return OutgoingReply(sender=msg.sender, reply=reply_text)
