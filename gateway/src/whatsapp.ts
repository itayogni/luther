import makeWASocket, {
  DisconnectReason,
  useMultiFileAuthState,
  WASocket,
} from "@whiskeysockets/baileys";
import pino from "pino";
import qrcode from "qrcode";
import { writeFileSync } from "fs";

const logger = pino({ level: "silent" });

let sock: WASocket | null = null;

type MessageHandler = (msg: {
  sender: string;
  body: string;
  messageType: string;
  timestamp: number;
  groupJid: string | null;
  chatName: string | null;
}) => Promise<void>;

let onMessage: MessageHandler | null = null;

export function setMessageHandler(handler: MessageHandler) {
  onMessage = handler;
}

export async function connectWhatsApp(): Promise<void> {
  const { state, saveCreds } = await useMultiFileAuthState("auth_info");

  sock = makeWASocket({ auth: state, logger, printQRInTerminal: false });

  sock.ev.on("creds.update", saveCreds);

  sock.ev.on("connection.update", async (update: any) => {
    const { connection, lastDisconnect, qr } = update;
    if (qr) {
      console.log("QR code ready — saving qr.html...");
      const qrImageUrl = await qrcode.toDataURL(qr);
      const html = `<!DOCTYPE html><html><body style="display:flex;justify-content:center;align-items:center;height:100vh;margin:0;background:#fff"><img src="${qrImageUrl}" style="width:400px;height:400px"/></body></html>`;
      writeFileSync("qr.html", html);
    }
    if (connection === "close") {
      const code = (lastDisconnect?.error as any)?.output?.statusCode;
      if (code !== DisconnectReason.loggedOut) {
        console.log("Reconnecting...");
        connectWhatsApp();
      } else {
        console.log("Logged out — delete auth_info/ and restart to re-scan QR.");
      }
    } else if (connection === "open") {
      console.log("WhatsApp connected successfully.");
    }
  });

  sock.ev.on("messages.upsert", async ({ messages, type }: any) => {
    if (type !== "notify") return;

    for (const msg of messages) {
      if (!msg.message) continue;

      const body =
        msg.message.conversation ||
        msg.message.extendedTextMessage?.text ||
        msg.message.imageMessage?.caption ||
        "";

      if (!body) continue;

      const sender = msg.key.remoteJid || "";
      const isGroup = sender.endsWith("@g.us");
      const groupJid = isGroup ? sender : null;
      const actualSender = isGroup
        ? (msg.key.participant || sender)
        : sender;

      let chatName: string | null = null;
      if (isGroup && sock) {
        try {
          const metadata = await sock.groupMetadata(sender);
          chatName = metadata.subject;
        } catch {
          chatName = null;
        }
      } else if (!isGroup) {
        chatName = actualSender;
      }

      console.log(`[msg] from=${actualSender} chat=${chatName} body=${body.slice(0, 60)}`);

      if (onMessage) {
        await onMessage({
          sender: actualSender,
          body,
          messageType: "text",
          timestamp: (msg.messageTimestamp as number) || Date.now() / 1000,
          groupJid,
          chatName,
        });
      }
    }
  });
}

export async function sendMessage(jid: string, text: string): Promise<void> {
  if (!sock) throw new Error("WhatsApp not connected");
  await sock.sendMessage(jid, { text });
}
