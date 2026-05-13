import makeWASocket, {
  DisconnectReason,
  useMultiFileAuthState,
  WASocket,
} from "@whiskeysockets/baileys";
import pino from "pino";

const logger = pino({ level: "warn" });

let sock: WASocket | null = null;

type MessageHandler = (msg: {
  sender: string;
  body: string;
  messageType: string;
  timestamp: number;
  groupJid: string | null;
}) => Promise<void>;

let onMessage: MessageHandler | null = null;

export function setMessageHandler(handler: MessageHandler) {
  onMessage = handler;
}

export async function connectWhatsApp(): Promise<void> {
  const { state, saveCreds } = await useMultiFileAuthState("auth_info");

  sock = makeWASocket({
    auth: state,
    logger,
    printQRInTerminal: true,
  });

  sock.ev.on("creds.update", saveCreds);

  sock.ev.on("connection.update", (update) => {
    const { connection, lastDisconnect } = update;
    if (connection === "close") {
      const statusCode = (lastDisconnect?.error as any)?.output?.statusCode;
      if (statusCode !== DisconnectReason.loggedOut) {
        console.log("Connection lost. Reconnecting...");
        connectWhatsApp();
      } else {
        console.log("Logged out. Delete auth_info/ and restart to re-scan QR.");
      }
    } else if (connection === "open") {
      console.log("WhatsApp connected successfully.");
    }
  });

  sock.ev.on("messages.upsert", async ({ messages }) => {
    for (const msg of messages) {
      if (!msg.message || msg.key.fromMe) continue;

      const sender = msg.key.remoteJid || "";
      const isGroup = sender.endsWith("@g.us");
      const body =
        msg.message.conversation ||
        msg.message.extendedTextMessage?.text ||
        "";
      const messageType = body ? "text" : "media";
      const timestamp = msg.messageTimestamp as number;

      if (onMessage) {
        await onMessage({
          sender: isGroup ? (msg.key.participant || sender) : sender,
          body,
          messageType,
          timestamp,
          groupJid: isGroup ? sender : null,
        });
      }
    }
  });
}

export async function sendMessage(jid: string, text: string): Promise<void> {
  if (!sock) throw new Error("WhatsApp not connected");
  await sock.sendMessage(jid, { text });
}
