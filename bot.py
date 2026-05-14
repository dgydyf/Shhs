import os
import json
import logging
import hashlib
import asyncio
from aiohttp import web
from telegram import Update
from telegram.ext import (
    Application, CommandHandler, MessageHandler, ConversationHandler,
    ChatMemberHandler, ContextTypes, filters
)

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO
)
logger = logging.getLogger(__name__)

BOT_TOKEN = os.environ.get("BOT_TOKEN", "")
WEBHOOK_URL = os.environ.get("WEBHOOK_URL", "")
PORT = int(os.environ.get("PORT", 8080))

ADMIN_IDS = [8508012498, 8225821294]
BOT_PASSWORD = "1910398591@#aA"
DB_FILE = "data.json"

(
    POST_CONTENT, POST_SELECT_CHANNELS,
    ADD_WAIT_ID,
    BAN_WAIT_PASSWORD, BAN_WAIT_ID,
    REMOVE_SELECT_CHANNELS, REMOVE_WAIT_CONTENT,
) = range(7)


def load_db():
    if not os.path.exists(DB_FILE):
        return {"members": [], "channels": [], "posted_messages": {}}
    with open(DB_FILE, "r") as f:
        return json.load(f)


def save_db(data):
    with open(DB_FILE, "w") as f:
        json.dump(data, f, indent=2)


def is_admin(user_id: int) -> bool:
    return user_id in ADMIN_IDS


def is_member(user_id: int) -> bool:
    db = load_db()
    return user_id in db["members"]


def is_authorized(user_id: int) -> bool:
    return is_admin(user_id) or is_member(user_id)


def content_hash(text: str) -> str:
    return hashlib.md5(text.strip().encode()).hexdigest()


def build_channel_list(channels: list) -> str:
    if not channels:
        return "No channels/groups added yet."
    lines = []
    for i, ch in enumerate(channels, 1):
        lines.append(f"{i}. {ch['display']}")
    return "\n".join(lines)


def parse_selection(text: str, total: int):
    text = text.strip()
    if text.lower() == "all":
        return list(range(total))
    indices = []
    for part in text.replace(" ", "").split(","):
        try:
            idx = int(part) - 1
            if 0 <= idx < total:
                indices.append(idx)
        except ValueError:
            pass
    return indices


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "😎 Boss, please write the post you want to send within one minute. "
        "I will send your message to all groups/channels where I am admin 😻.\n\n"
        "If you don't know the bot's admin or password, you cannot get access. "
        "Contact admin ✆@A15287"
    )


async def list_channels(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if not is_authorized(user_id):
        return
    db = load_db()
    channels = db.get("channels", [])
    if not channels:
        await update.message.reply_text("No channels or groups have been added yet.")
        return
    text = "📋 List of all channels/groups:\n\n" + build_channel_list(channels)
    await update.message.reply_text(text)


async def post_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if not is_authorized(user_id):
        return ConversationHandler.END
    await update.message.reply_text(
        "😻 Boss, share what post you want to make, let's see what I can do 😎"
    )
    return POST_CONTENT


async def post_receive_content(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["post_content"] = update.message.text
    db = load_db()
    channels = db.get("channels", [])
    if not channels:
        await update.message.reply_text("❌ No channels or groups added yet.")
        return ConversationHandler.END
    channel_list = build_channel_list(channels)
    await update.message.reply_text(
        f"Which channels or groups do you want to post to?\n\n{channel_list}\n\n"
        "Reply with numbers separated by commas (e.g. 1,2,3) or type 'All' for all."
    )
    return POST_SELECT_CHANNELS


async def post_select_channels(update: Update, context: ContextTypes.DEFAULT_TYPE):
    db = load_db()
    channels = db.get("channels", [])
    selection = parse_selection(update.message.text, len(channels))
    if not selection:
        await update.message.reply_text("❌ Invalid selection. Please try /post again.")
        return ConversationHandler.END
    content = context.user_data.get("post_content", "")
    c_hash = content_hash(content)
    success_count = 0
    fail_count = 0
    for idx in selection:
        ch = channels[idx]
        ch_id_str = str(ch["id"])
        try:
            sent = await context.bot.send_message(chat_id=ch["id"], text=content)
            if ch_id_str not in db["posted_messages"]:
                db["posted_messages"][ch_id_str] = {}
            db["posted_messages"][ch_id_str][c_hash] = sent.message_id
            success_count += 1
        except Exception as e:
            logger.error(f"Failed to send to {ch['id']}: {e}")
            fail_count += 1
    save_db(db)
    await update.message.reply_text(
        f"✅ Post completed!\nSUCCESS: {success_count}\nFAILED: {fail_count}"
    )
    return ConversationHandler.END


async def add_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if is_admin(user_id):
        await update.message.reply_text("😎 Boss, submit Telegram ID:")
        return ADD_WAIT_ID
    else:
        await update.message.reply_text(
            "❌ Only admins can add new members. Contact admin ✆@A15287"
        )
        return ConversationHandler.END


async def add_receive_id(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip()
    try:
        new_id = int(text)
    except ValueError:
        await update.message.reply_text("❌ Invalid Telegram ID. Please send a numeric ID.")
        return ConversationHandler.END
    db = load_db()
    if new_id in ADMIN_IDS:
        await update.message.reply_text("ℹ️ This user is already an admin.")
        return ConversationHandler.END
    if new_id in db["members"]:
        await update.message.reply_text("ℹ️ This user is already a member.")
        return ConversationHandler.END
    db["members"].append(new_id)
    save_db(db)
    await update.message.reply_text(f"✅ User {new_id} has been added as a member.")
    return ConversationHandler.END


async def ban_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if not is_authorized(user_id):
        return ConversationHandler.END
    if is_admin(user_id):
        await update.message.reply_text("Submit Telegram ID to ban:")
        return BAN_WAIT_ID
    else:
        await update.message.reply_text("😎 Boss, submit password ✅")
        return BAN_WAIT_PASSWORD


async def ban_check_password(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message.text.strip() == BOT_PASSWORD:
        await update.message.reply_text("✅ Password correct. Submit Telegram ID to ban:")
        return BAN_WAIT_ID
    else:
        await update.message.reply_text("Password incorrect ❌")
        return ConversationHandler.END


async def ban_receive_id(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip()
    try:
        ban_id = int(text)
    except ValueError:
        await update.message.reply_text("❌ Invalid Telegram ID.")
        return ConversationHandler.END
    if ban_id in ADMIN_IDS:
        await update.message.reply_text("❌ Cannot ban an admin.")
        return ConversationHandler.END
    db = load_db()
    if ban_id not in db["members"]:
        await update.message.reply_text("ℹ️ This user is not a member.")
        return ConversationHandler.END
    db["members"].remove(ban_id)
    save_db(db)
    await update.message.reply_text(f"✅ User {ban_id} has been banned and removed.")
    return ConversationHandler.END


async def removepost_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if not is_authorized(user_id):
        return ConversationHandler.END
    db = load_db()
    channels = db.get("channels", [])
    if not channels:
        await update.message.reply_text("❌ No channels or groups added yet.")
        return ConversationHandler.END
    channel_list = build_channel_list(channels)
    await update.message.reply_text(
        f"From which channels/groups do you want to delete a post?\n\n{channel_list}\n\n"
        "Reply with numbers separated by commas (e.g. 1,2,3) or type 'All'."
    )
    return REMOVE_SELECT_CHANNELS


async def removepost_select_channels(update: Update, context: ContextTypes.DEFAULT_TYPE):
    db = load_db()
    channels = db.get("channels", [])
    selection = parse_selection(update.message.text, len(channels))
    if not selection:
        await update.message.reply_text("❌ Invalid selection. Please try /removepost again.")
        return ConversationHandler.END
    context.user_data["remove_selection"] = selection
    await update.message.reply_text(
        "Which post do you want to delete? Write it exactly as it was posted 😶"
    )
    return REMOVE_WAIT_CONTENT


async def removepost_receive_content(update: Update, context: ContextTypes.DEFAULT_TYPE):
    db = load_db()
    channels = db.get("channels", [])
    selection = context.user_data.get("remove_selection", [])
    content = update.message.text
    c_hash = content_hash(content)
    total = len(selection)
    deleted = 0
    failed = 0
    for idx in selection:
        ch = channels[idx]
        ch_id_str = str(ch["id"])
        msg_id = db.get("posted_messages", {}).get(ch_id_str, {}).get(c_hash)
        if msg_id:
            try:
                await context.bot.delete_message(chat_id=ch["id"], message_id=msg_id)
                del db["posted_messages"][ch_id_str][c_hash]
                deleted += 1
            except Exception as e:
                logger.error(f"Failed to delete from {ch['id']}: {e}")
                failed += 1
        else:
            failed += 1
    save_db(db)
    await update.message.reply_text(
        f"TOTAL: {total}\nDeleted: {deleted}\nDeleted Fail: {failed}"
    )
    return ConversationHandler.END


async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("❌ Operation cancelled.")
    return ConversationHandler.END


async def handle_my_chat_member(update: Update, context: ContextTypes.DEFAULT_TYPE):
    result = update.my_chat_member
    if not result:
        return
    chat = result.chat
    new_status = result.new_chat_member.status
    db = load_db()
    existing_ids = [c["id"] for c in db["channels"]]
    if new_status in ("administrator", "creator"):
        if chat.id not in existing_ids:
            if chat.username:
                display = f"@{chat.username}"
            else:
                try:
                    invite = await context.bot.export_chat_invite_link(chat.id)
                    display = invite
                except Exception:
                    display = str(chat.id)
            db["channels"].append({
                "id": chat.id,
                "display": display,
                "title": chat.title or ""
            })
            save_db(db)
            logger.info(f"Added channel/group: {chat.id} ({display})")
    elif new_status in ("left", "kicked", "member"):
        if chat.id in existing_ids:
            db["channels"] = [c for c in db["channels"] if c["id"] != chat.id]
            save_db(db)
            logger.info(f"Removed channel/group: {chat.id}")


async def unknown_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user is None:
        return
    user_id = update.effective_user.id
    if not is_authorized(user_id):
        return


def build_app() -> Application:
    app = Application.builder().token(BOT_TOKEN).build()
    post_conv = ConversationHandler(
        entry_points=[CommandHandler("post", post_start)],
        states={
            POST_CONTENT: [MessageHandler(filters.TEXT & ~filters.COMMAND, post_receive_content)],
            POST_SELECT_CHANNELS: [MessageHandler(filters.TEXT & ~filters.COMMAND, post_select_channels)],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
    )
    add_conv = ConversationHandler(
        entry_points=[CommandHandler("add", add_start)],
        states={
            ADD_WAIT_ID: [MessageHandler(filters.TEXT & ~filters.COMMAND, add_receive_id)],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
    )
    ban_conv = ConversationHandler(
        entry_points=[CommandHandler("ban", ban_start)],
        states={
            BAN_WAIT_PASSWORD: [MessageHandler(filters.TEXT & ~filters.COMMAND, ban_check_password)],
            BAN_WAIT_ID: [MessageHandler(filters.TEXT & ~filters.COMMAND, ban_receive_id)],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
    )
    remove_conv = ConversationHandler(
        entry_points=[CommandHandler("removepost", removepost_start)],
        states={
            REMOVE_SELECT_CHANNELS: [MessageHandler(filters.TEXT & ~filters.COMMAND, removepost_select_channels)],
            REMOVE_WAIT_CONTENT: [MessageHandler(filters.TEXT & ~filters.COMMAND, removepost_receive_content)],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
    )
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("list", list_channels))
    app.add_handler(post_conv)
    app.add_handler(add_conv)
    app.add_handler(ban_conv)
    app.add_handler(remove_conv)
    app.add_handler(ChatMemberHandler(handle_my_chat_member, ChatMemberHandler.MY_CHAT_MEMBER))
    app.add_handler(MessageHandler(filters.COMMAND, unknown_handler))
    return app


async def health_check(request):
    return web.Response(text="Bot is running ✅")


async def telegram_webhook(request):
    ptb_app = request.app["ptb_app"]
    data = await request.json()
    update = Update.de_json(data, ptb_app.bot)
    await ptb_app.process_update(update)
    return web.Response(text="OK")


async def run():
    if not BOT_TOKEN:
        logger.error("BOT_TOKEN is not set!")
        raise SystemExit(1)

    ptb_app = build_app()
    await ptb_app.initialize()
    await ptb_app.start()

    if WEBHOOK_URL:
        webhook_path = f"/{BOT_TOKEN}"
        full_webhook_url = f"{WEBHOOK_URL}{webhook_path}"
        await ptb_app.bot.set_webhook(
            url=full_webhook_url,
            drop_pending_updates=True,
            allowed_updates=Update.ALL_TYPES,
        )
        logger.info(f"Webhook set to: {full_webhook_url}")

        web_app = web.Application()
        web_app["ptb_app"] = ptb_app
        web_app.router.add_get("/", health_check)
        web_app.router.add_get("/health", health_check)
        web_app.router.add_post(webhook_path, telegram_webhook)

        runner = web.AppRunner(web_app)
        await runner.setup()
        site = web.TCPSite(runner, "0.0.0.0", PORT)
        await site.start()
        logger.info(f"Server running on port {PORT}")

        await asyncio.Event().wait()
    else:
        logger.info("No WEBHOOK_URL — starting polling mode")
        await ptb_app.updater.start_polling(
            drop_pending_updates=True,
            allowed_updates=Update.ALL_TYPES,
        )
        await asyncio.Event().wait()


if __name__ == "__main__":
    asyncio.run(run())
