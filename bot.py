"""
ICOS Master Telegram Bot
Implements the LOCKED architecture: ONE bot, not per-platform (blueprint Section 8A).
Commands: /start, /upload (via file), /generate <PRODUCT_CODE>, /approve, /reject, /status
"""

import logging
import os
import tempfile

from telegram import Update
from telegram.ext import (
    Application, CommandHandler, MessageHandler, ContextTypes, filters
)

import config
import database as db
import pipeline

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

# Holds the most recent generated bundle in memory, keyed by chat_id,
# so /approve and /reject know what they're acting on. Simple V1 approach.
PENDING_BUNDLES = {}


def _owner_only(func):
    async def wrapper(update: Update, context: ContextTypes.DEFAULT_TYPE):
        user_id = str(update.effective_user.id)
        if config.OWNER_TELEGRAM_ID and user_id != config.OWNER_TELEGRAM_ID:
            await update.message.reply_text("This bot is private.")
            return
        if not config.OWNER_TELEGRAM_ID:
            await update.message.reply_text(
                f"⚠️ Note: OWNER_TELEGRAM_ID is not set yet. Your Telegram ID is: {user_id}\n"
                f"Add this to config.py or as an environment variable to lock the bot to you."
            )
        return await func(update, context)
    return wrapper


@_owner_only
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "👋 Welcome to ICOS — INAYA Content Automation.\n\n"
        "Commands:\n"
        "📄 Send me a product file (.txt or .pdf-as-text) to extract knowledge from it.\n"
        "/generate CODE — generate today's content bundle for a product (e.g. /generate WPPS)\n"
        "/approve — approve all passing content in the current bundle\n"
        "/approve_platform PLATFORM — approve just one platform (e.g. /approve_platform linkedin)\n"
        "/reject — reject the current bundle\n"
        "/status — show system status\n"
    )


@_owner_only
async def status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    products, kus, published = db.get_status_counts()
    await update.message.reply_text(
        f"📊 ICOS Status\n\n"
        f"Products uploaded: {products}\n"
        f"Knowledge Units extracted: {kus}\n"
        f"Content published so far: {published}\n"
    )


@_owner_only
async def handle_document(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """User uploads a product file. We extract text and run the extraction pipeline."""
    doc = update.message.document
    filename = doc.file_name

    await update.message.reply_text(f"📥 Received: {filename}\nDownloading...")

    file = await context.bot.get_file(doc.file_id)
    with tempfile.NamedTemporaryFile(delete=False, suffix=os.path.splitext(filename)[1]) as tmp:
        await file.download_to_drive(tmp.name)
        tmp_path = tmp.name

    text = _extract_text(tmp_path, filename)
    if not text or len(text.strip()) < 50:
        await update.message.reply_text(
            "⚠️ Couldn't read meaningful text from that file. "
            "For V1, plain .txt files work most reliably. PDF support is basic."
        )
        return

    await update.message.reply_text(
        "Which product is this?\n"
        + "\n".join(f"• {code} — {name}" for code, name in config.PRODUCTS.items())
        + "\n\nReply with: PRODUCT_CODE TIER filename_note\n"
          "Example: WPPS Codex my_wpps_codex"
    )
    context.user_data["pending_upload_text"] = text
    context.user_data["pending_upload_filename"] = filename


@_owner_only
async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Catches the product-code reply after a document upload, and other free text."""
    text = update.message.text.strip()

    if "pending_upload_text" in context.user_data:
        parts = text.split()
        if len(parts) < 2 or parts[0].upper() not in config.PRODUCTS:
            await update.message.reply_text(
                "Please reply in this format: PRODUCT_CODE TIER\n"
                "Example: WPPS Codex"
            )
            return

        product_id = parts[0].upper()
        tier = parts[1] if parts[1] in config.VALID_TIERS else "Codex"
        product_name = config.PRODUCTS[product_id]
        product_text = context.user_data.pop("pending_upload_text")
        filename = context.user_data.pop("pending_upload_filename")

        await update.message.reply_text(
            f"🔍 Extracting Knowledge Units from {product_name} ({tier})...\nThis takes a minute."
        )
        ku_ids = pipeline.process_new_product(product_id, product_name, tier, filename, product_text)

        await update.message.reply_text(
            f"✅ Done. Extracted {len(ku_ids)} Knowledge Units from {product_name}.\n\n"
            f"Ready to generate content. Send:\n/generate {product_id}"
        )
        return

    await update.message.reply_text("Send /start to see available commands.")


@_owner_only
async def generate(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("Usage: /generate PRODUCT_CODE  (e.g. /generate WPPS)")
        return

    product_id = context.args[0].upper()
    if product_id not in config.PRODUCTS:
        await update.message.reply_text(f"Unknown product code. Options: {', '.join(config.PRODUCTS)}")
        return

    product_name = config.PRODUCTS[product_id]
    await update.message.reply_text(f"⚙️ Generating today's content bundle for {product_name}...\nThis takes a minute or two.")

    bundle = pipeline.generate_daily_bundle(product_id, product_name)
    if not bundle:
        await update.message.reply_text(
            f"No unused Knowledge Units found for {product_name}. "
            f"Upload a product document first."
        )
        return

    chat_id = update.effective_chat.id
    PENDING_BUNDLES[chat_id] = bundle

    msg = (
        f"═══════════════════════════\n"
        f"📌 DAILY CONTENT — {product_name}\n"
        f"KU: {bundle['ku_core_insight'][:100]}...\n"
        f"═══════════════════════════\n\n"
    )
    await update.message.reply_text(msg)

    for r in bundle["platform_results"]:
        icon = "✅" if r["audit_status"] == "PASS" else "❌"
        preview = r["content_text"][:600]
        reasons = ""
        if r["audit_status"] == "FAIL":
            reasons = "\nReasons: " + "; ".join(r["audit_result"].get("failure_reasons", []))
        await update.message.reply_text(
            f"{icon} {r['platform'].upper()} — {r['audit_status']}\n\n{preview}{reasons}"
        )

    await update.message.reply_text(
        "What next?\n"
        "/approve — approve all PASSING platforms\n"
        "/approve_platform NAME — approve just one\n"
        "/reject — reject everything in this bundle"
    )


@_owner_only
async def approve_all(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    bundle = PENDING_BUNDLES.get(chat_id)
    if not bundle:
        await update.message.reply_text("No pending bundle. Run /generate PRODUCT_CODE first.")
        return

    approved = 0
    for r in bundle["platform_results"]:
        if r["audit_status"] == "PASS":
            pipeline.approve_content(r["content_id"])
            approved += 1

    await update.message.reply_text(
        f"✅ Approved {approved} platform(s). "
        f"(Note: actual posting to each platform's API is not yet connected in V1 — "
        f"content is marked approved and tracked, ready for that step next.)"
    )


@_owner_only
async def approve_platform(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    bundle = PENDING_BUNDLES.get(chat_id)
    if not bundle or not context.args:
        await update.message.reply_text("Usage: /approve_platform linkedin")
        return

    platform = context.args[0].lower()
    match = next((r for r in bundle["platform_results"] if r["platform"] == platform), None)
    if not match:
        await update.message.reply_text(f"No content for platform '{platform}' in this bundle.")
        return

    pipeline.approve_content(match["content_id"])
    await update.message.reply_text(f"✅ Approved {platform}.")


@_owner_only
async def reject_all(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    bundle = PENDING_BUNDLES.pop(chat_id, None)
    if not bundle:
        await update.message.reply_text("No pending bundle.")
        return
    for r in bundle["platform_results"]:
        pipeline.reject_content(r["content_id"])
    await update.message.reply_text("❌ Bundle rejected.")


def _extract_text(filepath, filename):
    if filename.lower().endswith(".txt"):
        with open(filepath, "r", errors="ignore") as f:
            return f.read()
    if filename.lower().endswith(".pdf"):
        try:
            from pypdf import PdfReader
            reader = PdfReader(filepath)
            return "\n".join(page.extract_text() or "" for page in reader.pages)
        except Exception as e:
            logger.error(f"PDF extraction failed: {e}")
            return ""
    return ""


def build_app():
    db.init_db()
    app = Application.builder().token(config.TELEGRAM_BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("status", status))
    app.add_handler(CommandHandler("generate", generate))
    app.add_handler(CommandHandler("approve", approve_all))
    app.add_handler(CommandHandler("approve_platform", approve_platform))
    app.add_handler(CommandHandler("reject", reject_all))
    app.add_handler(MessageHandler(filters.Document.ALL, handle_document))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))

    return app


if __name__ == "__main__":
    if not config.TELEGRAM_BOT_TOKEN:
        raise SystemExit("Set TELEGRAM_BOT_TOKEN environment variable first.")
    if not config.GEMINI_API_KEY:
        raise SystemExit("Set GEMINI_API_KEY environment variable first. Get a free key at https://aistudio.google.com/apikey")

    application = build_app()
    print("🤖 ICOS Bot starting... send /start to your bot in Telegram.")
    application.run_polling()
