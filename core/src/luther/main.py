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
    chat_name: str | None = None


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

    # Iron rule: only respond in the authorized chat
    # Use group_jid (immutable) if configured, fall back to chat_name
    if settings.allowed_group_jid.strip():
        if msg.group_jid != settings.allowed_group_jid:
            logger.warning("BLOCKED: unauthorized group_jid '%s' from %s", msg.group_jid, msg.sender)
            return OutgoingReply(sender=msg.sender, reply="")
    else:
        if not msg.chat_name:
            logger.warning("BLOCKED: message without chat_name from %s", msg.sender)
            return OutgoingReply(sender=msg.sender, reply="")
        if msg.chat_name != settings.allowed_chat_name:
            logger.warning("BLOCKED: message from unauthorized chat '%s'", msg.chat_name)
            return OutgoingReply(sender=msg.sender, reply="")

    logger.info("Message from %s in '%s': %s", msg.sender, msg.chat_name, msg.body[:60])

    reply_text = await think(sender=msg.sender, message=msg.body, media_url=msg.media_url)

    return OutgoingReply(sender=msg.sender, reply=reply_text)
