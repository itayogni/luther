const CORE_URL = process.env.LUTHER_CORE_URL || "http://localhost:8000";
const GATEWAY_SECRET =
  process.env.LUTHER_GATEWAY_SECRET || "shared-secret-between-services";

interface MessagePayload {
  sender: string;
  body: string;
  message_type: string;
  timestamp: number;
  group_jid: string | null;
  chat_name: string | null;
  media_url: string | null;
}

interface ReplyPayload {
  sender: string;
  reply: string;
}

export async function forwardToCore(
  payload: MessagePayload
): Promise<ReplyPayload | null> {
  try {
    const response = await fetch(`${CORE_URL}/webhook/message`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        "X-Gateway-Secret": GATEWAY_SECRET,
      },
      body: JSON.stringify(payload),
    });

    if (!response.ok) {
      console.error(`Core returned ${response.status}`);
      return null;
    }

    return (await response.json()) as ReplyPayload;
  } catch (err) {
    console.error("Failed to reach core:", err);
    return null;
  }
}
