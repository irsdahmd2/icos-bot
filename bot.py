"""
ICOS Telegram Bot — the user interface ONLY. No business logic lives here;
everything calls into pipeline.py / database.py.

CHANGED 2026-09-05 (final locked model):
- Upload flow now asks for a FREEFORM product name (no fixed code list)
- /generate takes NO arguments. It shows buttons for whichever platforms
  are NOT yet completed today for the Master Scheduler's active product.
- Every generated post gets 3 buttons: REFINE / READY TO PUBLISH / CONFIRM PUBLISHED
- No auto-publishing anywhere, no time-based schedule anywhere.
"""

import asyncio
import logging
import traceback

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application, CommandHandler, MessageHandler, CallbackQueryHandler,
    ContextTypes, filters,
)

import config
import database as db
import pipeline

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger("icos")

# In-memory state for the two-step upload flow (PDF -> ask name -> ask tier).
# Keyed by chat_id. This resets if the bot restarts, which is fine — it only
# holds a pending upload, not anything durable.
_pending_uploads = {}


def _owner_only(update: Update) -> bool:
    if not config.OWNER_TELEGRAM_ID:
        return True  # not locked down yet — bot.py will tell you your ID below
    return str(update.effective_user.id) == str(config.OWNER_TELEGRAM_ID)


async def _safe_answer(query):
    """Answers a button tap, but quietly ignores the harmless 'query is too
    old' Telegram error — this happens when a button sits on screen for a
    while, gets double-tapped, or the bot was mid-task when it was pressed.
    It means nothing was lost; there's just nothing useful to tell the user."""
    try:
        await query.answer()
    except Exception as e:
        logger.info(f"Ignored stale callback query: {e}")


def _todays_progress_text():
    """One clear paragraph: where you are today, and what's left. Used by the
    startup welcome message, /start, and after finishing a platform."""
    products = db.get_all_products()
    if not products:
        return "📭 No products uploaded yet. Upload a PDF to get started."

    state = db.get_or_create_todays_active_product()
    products_by_id = {p["product_id"]: p for p in products}
    active = products_by_id.get(state["active_product_id"])
    completed = state.get("platforms_completed") or []
    built_remaining = db.get_remaining_platforms_today(config.ACTIVE_PLATFORMS)

    total_planned = len(config.ALL_PLANNED_PLATFORMS)
    done_count = len([p for p in completed if p in config.ALL_PLANNED_PLATFORMS])
    not_built_yet = [p for p in config.ALL_PLANNED_PLATFORMS if p not in config.ACTIVE_PLATFORMS]

    lines = [
        f"🎯 Today's active product: {active['product_name']}",
        f"✅ Completed today: {done_count} of {total_planned} planned platforms",
    ]
    if built_remaining:
        lines.append(f"🟢 Ready to generate now: {', '.join(PLATFORM_LABELS.get(p, p) for p in built_remaining)}")
    else:
        lines.append("🟢 Nothing left to generate today from what's built.")
    if not_built_yet:
        lines.append(f"🚧 Not built yet (coming later): {', '.join(PLATFORM_LABELS.get(p, p) for p in not_built_yet)}")
    return "\n".join(lines)


def _main_menu_keyboard():
    return InlineKeyboardMarkup([[
        InlineKeyboardButton("📤 Upload New Product", callback_data="menu|upload"),
        InlineKeyboardButton("✍️ Generate Today's Post", callback_data="menu|generate"),
    ]])


async def send_welcome(chat_id, context: ContextTypes.DEFAULT_TYPE):
    """Shown automatically the moment the bot starts, and again on /start —
    so you always land on 'here's where things stand' + 'here's what to do
    next', instead of a blank chat and a list of commands to remember."""
    text = "👋 Welcome, Irshad — what's the agenda for today?\n\n" + _todays_progress_text()
    await context.bot.send_message(chat_id=chat_id, text=text, reply_markup=_main_menu_keyboard())


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not config.OWNER_TELEGRAM_ID:
        await update.message.reply_text(
            f"👋 ICOS is running. Your Telegram ID is: {update.effective_user.id}\n"
            f"Set this as OWNER_TELEGRAM_ID in Termux, then restart, to lock the bot to you only."
        )
        return
    await send_welcome(update.effective_chat.id, context)


async def handle_menu_choice(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await _safe_answer(query)
    _, choice = query.data.split("|")
    if choice == "upload":
        await context.bot.send_message(
            chat_id=query.message.chat_id,
            text="📄 Send me the product PDF now — I'll ask for the product name and tier next."
        )
    elif choice == "generate":
        await _send_generate_options(query.message.chat_id, context)


async def post_init(application: Application):
    """Runs once, right when `python3 bot.py` starts — sends the welcome
    message automatically so you don't have to type /start every time."""
    if not config.OWNER_TELEGRAM_ID:
        return
    try:
        await send_welcome(int(config.OWNER_TELEGRAM_ID), application)
    except Exception as e:
        logger.warning(
            f"Could not send startup welcome message: {e}. "
            f"If this is the very first run, message the bot with /start once first."
        )


async def status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    products, kus, published = db.get_status_counts()
    await update.message.reply_text(
        f"📊 Products: {products}\n📚 Knowledge Units: {kus}\n✅ Published: {published}"
    )


async def dashboard(update: Update, context: ContextTypes.DEFAULT_TYPE):
    rows = db.get_per_product_dashboard()
    if not rows:
        await update.message.reply_text("No products uploaded yet.")
        return
    lines = ["#  | Product | Full OS | Handbook | Codex"]
    for i, r in enumerate(rows, 1):
        lines.append(f"{i}. {r['product_name']} | {r['Full_OS']} | {r['Handbook']} | {r['Codex']}")
    await update.message.reply_text("\n".join(lines))


async def handle_document(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not _owner_only(update):
        return
    doc = update.message.document
    file = await doc.get_file()
    raw_bytes = await file.download_as_bytearray()

    if doc.file_name.lower().endswith(".pdf"):
        raw_text = _extract_pdf_text(bytes(raw_bytes))
    else:
        raw_text = raw_bytes.decode("utf-8", errors="ignore")

    if not raw_text.strip():
        await update.message.reply_text("⚠️ Couldn't read any text from that file.")
        return

    chat_id = update.effective_chat.id
    _pending_uploads[chat_id] = {"raw_text": raw_text, "filename": doc.file_name}
    await update.message.reply_text(
        "📄 Got it. What's the PRODUCT NAME? (type it as plain text, e.g. Household Operating System)"
    )


async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Only used for the one moment a plain-text reply is expected: the
    product name after a PDF upload. Everything else is buttons."""
    if not _owner_only(update):
        return
    chat_id = update.effective_chat.id
    pending = _pending_uploads.get(chat_id)
    if not pending or "product_name" in pending:
        return  # not waiting for a name right now — ignore stray text

    product_name = update.message.text.strip()
    pending["product_name"] = product_name

    keyboard = [[
        InlineKeyboardButton("Full OS (150+ pages)", callback_data=f"tier|{chat_id}|Full_OS"),
        InlineKeyboardButton("Handbook (35-50p)", callback_data=f"tier|{chat_id}|Handbook"),
        InlineKeyboardButton("Codex (6-10p)", callback_data=f"tier|{chat_id}|Codex"),
    ]]
    await update.message.reply_text(
        f"✅ Product: {product_name}\nWhich tier is this document?",
        reply_markup=InlineKeyboardMarkup(keyboard),
    )


async def handle_tier_choice(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await _safe_answer(query)
    _, chat_id_str, tier = query.data.split("|")
    chat_id = int(chat_id_str)
    pending = _pending_uploads.get(chat_id)
    if not pending:
        await query.edit_message_text("⚠️ Upload expired — please send the PDF again.")
        return

    await query.edit_message_text(f"⏳ Extracting Knowledge Units ({tier})... this can take a minute.")
    result = await asyncio.to_thread(
        pipeline.process_new_product,
        product_name=pending["product_name"], tier=tier,
        source_filename=pending["filename"], raw_text=pending["raw_text"],
    )
    del _pending_uploads[chat_id]

    await context.bot.send_message(
        chat_id=chat_id,
        text=(f"✅ Done.\nProduct: {result['product_name']} ({result['product_id']})\n"
              f"Tier: {result['tier']}\nKnowledge Units extracted: {result['ku_count']}\n\n"
              f"Send /generate any time to create the next post.")
    )


PLATFORM_LABELS = {
    "linkedin": "LinkedIn", "blog": "Blog", "facebook": "Facebook",
    "pinterest": "Pinterest", "instagram": "Instagram",
    "youtube_short": "YouTube Short", "youtube_podcast": "YouTube Podcast",
}


async def _send_generate_options(chat_id, context: ContextTypes.DEFAULT_TYPE):
    """Shared by the /generate command AND the '✍️ Generate Today's Post'
    menu button, so there's exactly one place this logic lives."""
    state = db.get_or_create_todays_active_product()
    if not state:
        await context.bot.send_message(chat_id=chat_id, text="No products uploaded yet — upload a PDF first.")
        return

    products = {p["product_id"]: p for p in db.get_all_products()}
    active = products.get(state["active_product_id"])
    remaining = db.get_remaining_platforms_today(config.ACTIVE_PLATFORMS)

    if not remaining:
        await context.bot.send_message(
            chat_id=chat_id,
            text=(f"✅ All available platforms already completed today for {active['product_name']}.\n"
                  f"Come back tomorrow for the next product in rotation.")
        )
        return

    keyboard = [[InlineKeyboardButton(
        PLATFORM_LABELS.get(p, p), callback_data=f"gen|{active['product_id']}|{active.get('tier','')}|{p}"
    )] for p in remaining]
    await context.bot.send_message(
        chat_id=chat_id,
        text=_todays_progress_text() + "\n\nPick a platform to generate:",
        reply_markup=InlineKeyboardMarkup(keyboard),
    )


async def generate(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Command-based, locked model (2026-09-05): NO arguments. Shows buttons
    for whichever platforms are still remaining today for the Master
    Scheduler's active product."""
    if not _owner_only(update):
        return
    await _send_generate_options(update.effective_chat.id, context)


def _format_delivery(result: dict) -> str:
    status_emoji = "✅" if result["audit_status"] == "PASS" else "❌"
    fails = [k for k, v in result["audit_results"].items() if v.get("result") == "FAIL"]
    fail_note = f"\n⚠️ Failed: {', '.join(fails)}" if fails else ""
    return (
        f"{status_emoji} Audit: {result['audit_status']}{fail_note}\n"
        f"Post ID: {result['post_code']} | Angle: {result['editorial_intent']}\n\n"
        f"{result['content_text']}"
    )


def _action_keyboard(content_id: str, can_publish: bool) -> InlineKeyboardMarkup:
    row1 = [InlineKeyboardButton("🔁 Refine", callback_data=f"refine|{content_id}")]
    if can_publish:
        row1.append(InlineKeyboardButton("📤 Ready to Publish", callback_data=f"ready|{content_id}"))
    row2 = [InlineKeyboardButton("✅ Confirm Published", callback_data=f"confirm|{content_id}")]
    return InlineKeyboardMarkup([row1, row2])


async def handle_platform_choice(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await _safe_answer(query)
    _, product_id, tier, platform = query.data.split("|")

    products = {p["product_id"]: p for p in db.get_all_products()}
    product_name = products.get(product_id, {}).get("product_name", product_id)

    await query.edit_message_text(f"⏳ Generating {PLATFORM_LABELS.get(platform, platform)}...")
    result = await asyncio.to_thread(pipeline.generate_for_platform, product_id, product_name, tier, platform)

    if "error" in result:
        await context.bot.send_message(chat_id=query.message.chat_id, text=f"⚠️ {result['error']}")
        return

    can_publish = result["audit_status"] == "PASS"
    await context.bot.send_message(
        chat_id=query.message.chat_id,
        text=_format_delivery(result),
        reply_markup=_action_keyboard(result["content_id"], can_publish),
    )
    db.update_content_status(result["content_id"], "telegram_delivered")


async def handle_refine(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await _safe_answer(query)
    _, content_id = query.data.split("|")
    old = db.get_content(content_id)
    products = {p["product_id"]: p for p in db.get_all_products()}
    product_name = products.get(old["product_id"], {}).get("product_name", old["product_id"]) if old else ""

    await query.edit_message_text("🔁 Refining...")
    result = await asyncio.to_thread(pipeline.refine, content_id, product_name)
    if "error" in result:
        await context.bot.send_message(chat_id=query.message.chat_id, text=f"⚠️ {result['error']}")
        return

    can_publish = result["audit_status"] == "PASS"
    await context.bot.send_message(
        chat_id=query.message.chat_id,
        text=_format_delivery(result),
        reply_markup=_action_keyboard(result["content_id"], can_publish),
    )
    db.update_content_status(result["content_id"], "telegram_delivered")


async def handle_ready_to_publish(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await _safe_answer(query)
    _, content_id = query.data.split("|")
    pipeline.mark_ready_to_publish(content_id)
    await query.edit_message_text(
        query.message.text + "\n\n📤 Marked READY TO PUBLISH — go publish it manually, "
        "then come back and tap Confirm Published."
    )


async def handle_confirm_published(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await _safe_answer(query)
    _, content_id = query.data.split("|")
    pipeline.mark_confirmed_published(content_id)
    await query.edit_message_text(query.message.text + "\n\n✅ CONFIRMED PUBLISHED. Dashboard updated.")
    # Immediately show what's left today, instead of leaving you at a dead end.
    await context.bot.send_message(
        chat_id=query.message.chat_id,
        text=_todays_progress_text(),
        reply_markup=_main_menu_keyboard(),
    )


async def on_error(update: object, context: ContextTypes.DEFAULT_TYPE):
    logger.error("Exception while handling an update:", exc_info=context.error)
    tb = "".join(traceback.format_exception(None, context.error, context.error.__traceback__))
    logger.error(tb)
    if isinstance(update, Update) and update.effective_chat:
        try:
            await context.bot.send_message(
                chat_id=update.effective_chat.id,
                text=f"⚠️ Something broke: {context.error}\n\n(Full trace in Termux logs.)"
            )
        except Exception:
            pass


def _extract_pdf_text(pdf_bytes: bytes) -> str:
    from pypdf import PdfReader
    import io
    reader = PdfReader(io.BytesIO(pdf_bytes))
    return "\n".join(page.extract_text() or "" for page in reader.pages)


def main():
    db.init_db()
    app = Application.builder().token(config.TELEGRAM_BOT_TOKEN).post_init(post_init).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("status", status))
    app.add_handler(CommandHandler("dashboard", dashboard))
    app.add_handler(CommandHandler("generate", generate))
    app.add_handler(MessageHandler(filters.Document.ALL, handle_document))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))

    app.add_handler(CallbackQueryHandler(handle_menu_choice, pattern=r"^menu\|"))
    app.add_handler(CallbackQueryHandler(handle_tier_choice, pattern=r"^tier\|"))
    app.add_handler(CallbackQueryHandler(handle_platform_choice, pattern=r"^gen\|"))
    app.add_handler(CallbackQueryHandler(handle_refine, pattern=r"^refine\|"))
    app.add_handler(CallbackQueryHandler(handle_ready_to_publish, pattern=r"^ready\|"))
    app.add_handler(CallbackQueryHandler(handle_confirm_published, pattern=r"^confirm\|"))

    app.add_error_handler(on_error)

    logger.info("ICOS bot starting...")
    app.run_polling()


if __name__ == "__main__":
    main()
