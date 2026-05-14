import { createRequire } from "module";
import qrcode from "qrcode";
import { writeFileSync } from "fs";

const require = createRequire(import.meta.url);
const { Client, LocalAuth } = require("whatsapp-web.js");

type MessageHandler = (msg: {
  sender: string;
  body: string;
  messageType: string;
  timestamp: number;
  groupJid: string | null;
}) => Promise<void>;

let client: any = null;
let onMessage: MessageHandler | null = null;

export function setMessageHandler(handler: MessageHandler) {
  onMessage = handler;
}

export async function connectWhatsApp(): Promise<void> {
  client = new Client({
    authStrategy: new LocalAuth({ dataPath: "auth_info" }),
    puppeteer: {
      headless: true,
      cacheDirectory: ".wwebjs_cache",
      args: ["--no-sandbox", "--disable-setuid-sandbox"],
    },
  });

  client.on("qr", async (qr: string) => {
    console.log("QR code generated — open qr.html in your browser to scan");
    const qrImageUrl = await qrcode.toDataURL(qr);
    const html = `<!DOCTYPE html><html><body style="display:flex;justify-content:center;align-items:center;height:100vh;margin:0;background:#fff"><img src="${qrImageUrl}" style="width:400px;height:400px"/></body></html>`;
    writeFileSync("qr.html", html);
  });

  client.on("ready", () => {
    console.log("WhatsApp connected successfully.");
  });

  client.on("disconnected", (reason: string) => {
    console.log("WhatsApp disconnected:", reason);
    connectWhatsApp();
  });

  client.on("message", async (msg: any) => {
    if (msg.fromMe) return;

    const chat = await msg.getChat();
    const isGroup = chat.isGroup;
    const sender: string = isGroup ? msg.author || msg.from : msg.from;
    const groupJid: string | null = isGroup ? msg.from : null;

    if (onMessage) {
      await onMessage({
        sender,
        body: msg.body,
        messageType: msg.type,
        timestamp: msg.timestamp,
        groupJid,
      });
    }
  });

  await client.initialize();
}

export async function sendMessage(jid: string, text: string): Promise<void> {
  if (!client) throw new Error("WhatsApp not connected");
  await client.sendMessage(jid, text);
}
