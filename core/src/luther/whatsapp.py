from dataclasses import dataclass

import httpx


@dataclass
class WhatsAppMessage:
    sender: str
    body: str
    message_type: str
    timestamp: int
    group_jid: str | None = None
    media_url: str | None = None

    @property
    def is_group(self) -> bool:
        return self.group_jid is not None


class WhatsAppAdapter:
    def __init__(self, gateway_url: str):
        self.gateway_url = gateway_url

    async def send(self, jid: str, text: str) -> None:
        async with httpx.AsyncClient() as client:
            await client.post(
                f"{self.gateway_url}/send",
                json={"jid": jid, "text": text},
            )
