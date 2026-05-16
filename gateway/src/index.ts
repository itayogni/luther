import { connectWhatsApp, sendMessage, setMessageHandler } from "./whatsapp.js";
import { forwardToCore } from "./api.js";

async function main() {
  console.log("Luther Gateway starting...");

  setMessageHandler(async (msg) => {
    console.log(`Message from ${msg.sender}: ${msg.body.slice(0, 50)}`);

    try {
      const reply = await forwardToCore({
        sender: msg.sender,
        body: msg.body,
        message_type: msg.messageType,
        timestamp: msg.timestamp,
        group_jid: msg.groupJid,
        chat_name: msg.chatName,
        media_url: null,
      });

      if (reply?.reply) {
        const replyTo = msg.groupJid || msg.sender;
        await sendMessage(replyTo, reply.reply);
      } else if (reply === null) {
        // Core is unreachable — only notify in authorized chat (iron rule)
        const allowedJid = process.env.LUTHER_ALLOWED_GROUP_JID || "";
        const allowedName = process.env.LUTHER_ALLOWED_CHAT_NAME || "לותר ואני";
        if (
          (allowedJid && msg.groupJid === allowedJid) ||
          (!allowedJid && msg.chatName === allowedName)
        ) {
          const replyTo = msg.groupJid || msg.sender;
          await sendMessage(replyTo, "לות'ר לא זמין כרגע. נסה שוב בעוד דקה.");
        }
      }
    } catch (err) {
      console.error("Message handler error:", err);
    }
  });

  await connectWhatsApp();
}

main().catch(console.error);
