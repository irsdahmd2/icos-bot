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
import os
import logging
import traceback
import json

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application, CommandHandler, MessageHandler, CallbackQueryHandler,
    ContextTypes, filters,
)

import config
import database as db
import pipeline
import ai_client

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger("icos")

# In-memory state for the two-step upload flow (PDF -> ask name -> ask tier).
# Keyed by chat_id. This resets if the bot restarts, which is fine — it only
# holds a pending upload, not anything durable.
_pending_uploads = {}
_pending_engagement = {}


def _owner_only(update: Update) -> bool:
    if not config.OWNER_TELEGRAM_ID:
        return True  # not locked down yet — bot.py will tell you your ID below
    return str(update.effective_user.id) == str(config.OWNER_TELEGRAM_ID)


async def _send_with_retry(context: ContextTypes.DEFAULT_TYPE, chat_id, text, reply_markup=None, attempts=3):
    """Sends a message, retrying a couple of times on a transient network
    blip (dropped connection, brief mobile network hiccup) instead of losing
    the result of a long-running extraction/generation call. Only network
    errors are retried — a real bug still surfaces immediately."""
    from telegram.error import NetworkError, TimedOut
    last_error = None
    for attempt in range(1, attempts + 1):
        try:
            return await context.bot.send_message(chat_id=chat_id, text=text, reply_markup=reply_markup)
        except (NetworkError, TimedOut) as e:
            last_error = e
            logger.warning(f"send_message network hiccup (attempt {attempt}/{attempts}): {e}")
            await asyncio.sleep(2 * attempt)
    logger.error(f"send_message failed after {attempts} attempts: {last_error}")
    raise last_error


async def _safe_answer(query, text: str = None):
    """Answers a button tap with a brief visible toast (so you always see
    SOMETHING happened, even before the fuller response arrives) and quietly
    ignores the harmless 'query is too old' Telegram error — that happens
    when a button sits on screen a while, gets double-tapped, or the bot was
    mid-task when it was pressed. It means nothing was lost."""
    try:
        await query.answer(text=text) if text else await query.answer()
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
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("📤 Upload New Product", callback_data="menu|upload")],
        [InlineKeyboardButton("✍️ Generate Today's Post", callback_data="menu|generate")],
    ])


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
    await _safe_answer(query, "Got it")
    _, choice = query.data.split("|")
    if choice == "upload":
        await context.bot.send_message(
            chat_id=query.message.chat_id,
            text="📤 Please upload your product PDF now."
        )
    elif choice == "generate":
        await _send_generate_options(query.message.chat_id, context)


async def post_init(application: Application):
    """Runs once, right when `python3 bot.py` starts. CHANGED 2026-09-13:
    used to auto-send the welcome menu on every restart — but Render restarts
    the bot on every deploy and occasionally on the free tier, which meant
    unsolicited messages Irshad never asked for. Per his explicit preference
    (system should only speak when asked, never self-showcase), this now
    just logs quietly instead of messaging Telegram at all."""
    logger.info("ICOS bot started — no startup message sent (by design; use /start when you want it).")


async def status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    products, kus, published = db.get_status_counts()
    await update.message.reply_text(
        f"📊 Products: {products}\n📚 Knowledge Units: {kus}\n✅ Published: {published}"
    )


DASHBOARD_MSG_ID_KEY = "pinned_dashboard_message_id"


def _render_dashboard_text():
    rows = db.get_per_product_dashboard()
    if not rows:
        return "📊 Dashboard (live)\n\nNo products uploaded yet."
    lines = ["📊 Dashboard (live — stays updated in place)\n"]
    for i, r in enumerate(rows, 1):
        block = (
            f"{i}. {r['product_name']}\n"
            f"   📚 KUs extracted — Total: {r['total_kus']} "
            f"(Full OS: {r['Full_OS']} | Handbook: {r['Handbook']} | Codex: {r['Codex']})\n"
            f"   ✍️ Posts generated: {r['posts_generated']} | ✅ Audit passed: {r['audit_passed']}\n"
            f"   📤 Confirmed published: {r['confirmed_published']}"
        )
        if r["awaiting_publish_count"]:
            codes = ", ".join(r["awaiting_publish_codes"])
            block += f"\n   🟡 Awaiting publish ({r['awaiting_publish_count']}): {codes}"
        lines.append(block)
    return "\n\n".join(lines)


async def refresh_pinned_dashboard(chat_id, context: ContextTypes.DEFAULT_TYPE):
    """Keeps ONE message updated in place with current stats, pinned to the
    top — so you can delete every other message in the chat each day and
    this one stays put with the real numbers."""
    text = _render_dashboard_text()
    msg_id = db.get_setting(DASHBOARD_MSG_ID_KEY)
    if msg_id:
        try:
            await context.bot.edit_message_text(chat_id=chat_id, message_id=int(msg_id), text=text)
            return
        except Exception as e:
            logger.info(f"Pinned dashboard message gone, sending a fresh one: {e}")

    sent = await context.bot.send_message(chat_id=chat_id, text=text)
    try:
        await context.bot.pin_chat_message(chat_id=chat_id, message_id=sent.message_id, disable_notification=True)
    except Exception as e:
        logger.warning(f"Could not pin dashboard message: {e}")
    db.set_setting(DASHBOARD_MSG_ID_KEY, str(sent.message_id))


async def dashboard(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await refresh_pinned_dashboard(update.effective_chat.id, context)


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
        "📄 Got it — please confirm, what product is this? (type the name as plain text, e.g. Household Operating System)"
    )


async def handle_screenshot(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """NEW 2026-09-13, PRECISION MATCHING added same day: send an analytics
    screenshot from ANY platform, and the bot (1) identifies which platform
    the screenshot is actually from by its UI, (2) pulls ONLY that
    platform's published posts as candidates — never mixing platforms —
    (3) runs a real content-match on the post's own visible text against
    those candidates, and (4) presents the single best match for a one-tap
    confirm, with a manual fallback list if no confident match is found.
    Numbers are NEVER auto-attached without the user confirming which post."""
    if not _owner_only(update):
        return
    chat_id = update.effective_chat.id
    photo = update.message.photo[-1]
    file = await photo.get_file()
    image_bytes = bytes(await file.download_as_bytearray())

    await update.message.reply_text("🔎 Reading the screenshot...")

    extraction_prompt = (
        "This is a screenshot of a social media post's analytics (likes, comments, "
        "shares/reposts, possibly impressions). Identify which platform this screenshot "
        "is from based on its visual UI (icons, layout, colors, terminology) — one of: "
        "linkedin, facebook, instagram, pinterest, blog, youtube_short, youtube_podcast, "
        "or unknown if you genuinely can't tell. Read the engagement numbers exactly as "
        "shown. Also transcribe the first ~20 words of the post's own text if visible "
        "anywhere in the screenshot, word for word, so it can be matched to the correct "
        "stored post — this is the most important field, be as exact as possible. "
        "Return ONLY valid JSON with these exact keys: platform (string), likes (integer), "
        "comments (integer), shares (integer), impressions (integer or null), "
        "post_text_snippet (string, exact transcription, empty string if none visible). "
        "No other text before or after the JSON."
    )
    raw = ai_client.generate_with_image(extraction_prompt, image_bytes, mime_type="image/jpeg")
    raw = raw.strip()
    if raw.startswith("```"):
        raw = "\n".join(l for l in raw.split("\n") if not l.strip().startswith("```"))
    try:
        metrics = json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        await update.message.reply_text(
            "⚠️ Couldn't read clear numbers from that screenshot — try a clearer/closer crop "
            "of the likes, comments, and shares."
        )
        return

    detected_platform = (metrics.get("platform") or "").lower().strip()
    snippet = (metrics.get("post_text_snippet") or "").strip()

    candidates = db.get_published_posts_by_platform(detected_platform) if detected_platform in PLATFORM_LABELS else []
    if not candidates:
        # Platform wasn't identified confidently, or nothing published yet on
        # that platform — fall back to the recent-across-all-platforms list
        # rather than silently failing.
        candidates = db.get_recent_published_posts(limit=8)

    if not candidates:
        await update.message.reply_text("No confirmed-published posts on record yet to match this against.")
        return

    _pending_engagement[chat_id] = metrics
    best_match = None
    if snippet and len(candidates) > 1:
        best_match = await asyncio.to_thread(_match_post_by_snippet, snippet, candidates)

    metrics_line = (
        f"📊 Platform detected: {detected_platform or 'unknown'}\n"
        f"👍 {metrics.get('likes',0)} | 💬 {metrics.get('comments',0)} | 🔁 {metrics.get('shares',0)}"
        + (f" | 👁️ {metrics['impressions']}" if metrics.get("impressions") else "")
    )
    if snippet:
        metrics_line += f"\nDetected post snippet: \"{snippet}\""

    if best_match:
        keyboard = [
            [InlineKeyboardButton(
                f"✅ Yes — {best_match['post_code']}",
                callback_data=f"engage|{chat_id}|{best_match['content_id']}|{best_match['post_code']}|{best_match['platform']}"
            )],
            [InlineKeyboardButton("Show other options instead", callback_data=f"engagemore|{chat_id}|{detected_platform}")],
        ]
        await update.message.reply_text(
            f"{metrics_line}\n\nBest match found: **{best_match['post_code']}** — confirm?",
            reply_markup=InlineKeyboardMarkup(keyboard),
        )
    else:
        keyboard = [
            [InlineKeyboardButton(
                f"{c['post_code']} ({c['platform']})",
                callback_data=f"engage|{chat_id}|{c['content_id']}|{c['post_code']}|{c['platform']}"
            )]
            for c in candidates[:8]
        ]
        await update.message.reply_text(
            f"{metrics_line}\n\nNo confident automatic match — which post is this for?",
            reply_markup=InlineKeyboardMarkup(keyboard),
        )


def _match_post_by_snippet(snippet: str, candidates: list):
    """Real content-matching, not a guess: asks the AI to pick the single
    candidate whose stored content_text genuinely contains/matches the
    screenshot's transcribed opening text. Returns None (not a forced guess)
    if no candidate is a confident match, so the caller falls back to a
    manual list instead of silently attaching to the wrong post."""
    listing = "\n".join(
        f"{i}: post_code={c['post_code']} | opening_text=\"{c['content_text'][:120]}\""
        for i, c in enumerate(candidates)
    )
    prompt = (
        "A social media analytics screenshot showed this transcribed opening text from a post:\n"
        f"\"{snippet}\"\n\n"
        f"Here are candidate stored posts:\n{listing}\n\n"
        "Which candidate index is genuinely the SAME post (allowing for minor transcription "
        "errors)? Return ONLY a JSON object: {\"match_index\": <integer>} if confident, or "
        "{\"match_index\": null} if none are a real match. No other text."
    )
    try:
        response = ai_client.get_client().messages.create(
            model=config.AI_MODEL, max_tokens=200,
            messages=[{"role": "user", "content": prompt}]
        )
        raw = response.content[0].text.strip()
        if raw.startswith("```"):
            raw = "\n".join(l for l in raw.split("\n") if not l.strip().startswith("```"))
        result = json.loads(raw)
        idx = result.get("match_index")
        if idx is not None and 0 <= idx < len(candidates):
            return candidates[idx]
    except Exception:
        pass
    return None


async def handle_engagement_show_more(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Fallback path from the 'Show other options instead' button — lists
    candidates for manual selection instead of the auto-matched guess."""
    query = update.callback_query
    await _safe_answer(query, "Showing options")
    _, chat_id_str, detected_platform = query.data.split("|")
    chat_id = int(chat_id_str)
    candidates = db.get_published_posts_by_platform(detected_platform) if detected_platform in PLATFORM_LABELS else []
    if not candidates:
        candidates = db.get_recent_published_posts(limit=8)
    keyboard = [
        [InlineKeyboardButton(
            f"{c['post_code']} ({c['platform']})",
            callback_data=f"engage|{chat_id}|{c['content_id']}|{c['post_code']}|{c['platform']}"
        )]
        for c in candidates[:8]
    ]
    await query.edit_message_text("Which post is this for?", reply_markup=InlineKeyboardMarkup(keyboard))


async def handle_engagement_confirm(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await _safe_answer(query, "Saved")
    _, chat_id_str, content_id, post_code, platform = query.data.split("|")
    chat_id = int(chat_id_str)
    metrics = _pending_engagement.pop(chat_id, None)
    if not metrics:
        await query.edit_message_text("⚠️ That screenshot's data expired — please resend it.")
        return

    db.save_post_engagement(
        content_id=content_id, post_code=post_code, platform=platform,
        likes=metrics.get("likes", 0), comments=metrics.get("comments", 0),
        shares=metrics.get("shares", 0), impressions=metrics.get("impressions"),
    )
    await query.edit_message_text(
        f"✅ Saved engagement for {post_code}: 👍 {metrics.get('likes',0)} | "
        f"💬 {metrics.get('comments',0)} | 🔁 {metrics.get('shares',0)}"
    )


async def insights(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """/insights — plain-language trend analysis over REAL saved engagement
    data (which angles/products/posts perform best). Distinct from the
    stats Q&A, which only knows counts, not performance."""
    if not _owner_only(update):
        return
    rows = db.get_engagement_report()
    if not rows:
        await update.message.reply_text(
            "No engagement data recorded yet — send a screenshot of a post's analytics "
            "(likes/comments/shares) every few days and I'll track it here."
        )
        return
    data_summary = "\n".join(
        f"- {r['post_code']} ({r['platform']}, angle={r.get('editorial_angle','')}): "
        f"likes={r['likes']}, comments={r['comments']}, shares={r['shares']}, "
        f"recorded={r['recorded_at'][:10]}"
        for r in rows
    )
    prompt = (
        "You are ICOS's data assistant. Using ONLY the real engagement data below, answer "
        "which editorial angles, products, or posts are performing best and worst, in 3-4 "
        "short plain sentences. Never invent a number not in the data.\n\n"
        f"DATA:\n{data_summary}\n\nQUESTION: {' '.join(context.args) if context.args else 'Summarize overall performance so far.'}"
    )
    response = ai_client.get_client().messages.create(
        model=config.AI_MODEL, max_tokens=500,
        messages=[{"role": "user", "content": prompt}]
    )
    await update.message.reply_text(response.content[0].text.strip())


async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Two jobs: (1) capture the product name right after a PDF upload, or
    (2) if that's not what's happening, treat the message as a plain-language
    question about real stats (KUs, posts, audits, published counts) and
    answer it using the actual database — not a guess."""
    if not _owner_only(update):
        return
    chat_id = update.effective_chat.id
    pending = _pending_uploads.get(chat_id)
    if pending and "product_name" not in pending:
        product_name = update.message.text.strip()
        pending["product_name"] = product_name

        keyboard = [
            [InlineKeyboardButton("Full OS (150+ pages)", callback_data=f"tier|{chat_id}|Full_OS")],
            [InlineKeyboardButton("Handbook (35-50p)", callback_data=f"tier|{chat_id}|Handbook")],
            [InlineKeyboardButton("Codex (6-10p)", callback_data=f"tier|{chat_id}|Codex")],
        ]
        await update.message.reply_text(
            f"✅ Confirmed: {product_name}\nWhich tier is this document?",
            reply_markup=InlineKeyboardMarkup(keyboard),
        )
        return

    await _answer_stats_question(update, context)


async def _answer_stats_question(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Answers plain-language questions like 'how many KUs for HOS Handbook'
    or 'how many posts published so far' using the REAL numbers from the
    database — never a guess. If nothing's been uploaded yet, says so plainly."""
    rows = db.get_per_product_dashboard()
    if not rows:
        await update.message.reply_text("No products uploaded yet, so there's nothing to report on.")
        return

    stats_summary = "\n".join(
        f"- {r['product_name']} (code {r['product_id']}): "
        f"Full OS KUs={r['Full_OS']}, Handbook KUs={r['Handbook']}, Codex KUs={r['Codex']}, "
        f"posts_generated={r['posts_generated']}, audit_passed={r['audit_passed']}, "
        f"confirmed_published={r['confirmed_published']}"
        for r in rows
    )
    last_7 = db.get_recent_activity_counts(days=7)
    last_30 = db.get_recent_activity_counts(days=30)
    recent_summary = (
        "LAST 7 DAYS by platform: " + json.dumps(last_7) +
        "\nLAST 30 DAYS by platform: " + json.dumps(last_30)
    )
    prompt = (
        "You are ICOS's data assistant. Answer the user's question using ONLY the real data "
        "below — never invent a number. Reply in one or two short plain sentences, no markdown, "
        "no headers. If the question doesn't match any product name closely, say which products "
        "you do have data for instead of guessing.\n\n"
        f"ALL-TIME DATA:\n{stats_summary}\n\nRECENT ACTIVITY:\n{recent_summary}\n\n"
        f"QUESTION: {update.message.text.strip()}"
    )
    response = ai_client.get_client().messages.create(
        model=config.AI_MODEL, max_tokens=300,
        messages=[{"role": "user", "content": prompt}]
    )
    await update.message.reply_text(response.content[0].text.strip())


async def handle_tier_choice(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await _safe_answer(query, "Tier selected")
    _, chat_id_str, tier = query.data.split("|")
    chat_id = int(chat_id_str)
    pending = _pending_uploads.get(chat_id)
    if not pending:
        await query.edit_message_text("⚠️ Upload expired — please send the PDF again.")
        return

    await query.edit_message_text("⏳ Processing... please wait.")
    result = await asyncio.to_thread(
        pipeline.process_new_product,
        product_name=pending["product_name"], tier=tier,
        source_filename=pending["filename"], raw_text=pending["raw_text"],
    )
    del _pending_uploads[chat_id]

    dup_line = ""
    if result.get("duplicates_skipped"):
        dup_line = f"⏭️ Skipped {result['duplicates_skipped']} duplicate insight(s) already covered by another tier.\n\n"

    await _send_with_retry(
        context, chat_id,
        text=(f"✅ Processing complete.\n\n"
              f"Product: {result['product_name']}\n"
              f"Tier: {result['tier']}\n"
              f"Unique Knowledge Units saved: {result['ku_count']}\n\n"
              f"{dup_line}"
              f"Ready to generate posts — tap Generate Today's Post whenever you're ready.")
    )
    await refresh_pinned_dashboard(chat_id, context)


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
    attempts_note = f" (took {result['attempts']} attempts)" if result.get("attempts", 1) > 1 else ""
    return (
        f"✅ Ready to publish{attempts_note}\n"
        f"Post ID: {result['post_code']} | Angle: {result['editorial_intent']}\n\n"
        f"{result['content_text']}"
    )


def _action_keyboard(content_id: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🔁 Refine", callback_data=f"refine|{content_id}")],
        [InlineKeyboardButton("📤 Ready to Publish", callback_data=f"ready|{content_id}")],
        [InlineKeyboardButton("✅ Confirm Published", callback_data=f"confirm|{content_id}")],
    ])


async def handle_platform_choice(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await _safe_answer(query, "Starting generation")
    _, product_id, tier, platform = query.data.split("|")

    products = {p["product_id"]: p for p in db.get_all_products()}
    product_name = products.get(product_id, {}).get("product_name", product_id)

    await query.edit_message_text("⏳ Processing... please wait.")
    result = await asyncio.to_thread(pipeline.generate_for_platform, product_id, product_name, tier, platform)

    if "error" in result:
        await context.bot.send_message(chat_id=query.message.chat_id, text=f"⚠️ {result['error']}")
        return

    await _send_with_retry(
        context, query.message.chat_id,
        text=_format_delivery(result),
        reply_markup=_action_keyboard(result["content_id"]),
    )
    db.update_content_status(result["content_id"], "telegram_delivered")
    await refresh_pinned_dashboard(query.message.chat_id, context)


async def handle_refine(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await _safe_answer(query, "Refining")
    _, content_id = query.data.split("|")
    old = db.get_content(content_id)
    products = {p["product_id"]: p for p in db.get_all_products()}
    product_name = products.get(old["product_id"], {}).get("product_name", old["product_id"]) if old else ""

    await query.edit_message_text("⏳ Processing... please wait.")
    result = await asyncio.to_thread(pipeline.refine, content_id, product_name)
    if "error" in result:
        await context.bot.send_message(chat_id=query.message.chat_id, text=f"⚠️ {result['error']}")
        return

    await _send_with_retry(
        context, query.message.chat_id,
        text=_format_delivery(result),
        reply_markup=_action_keyboard(result["content_id"]),
    )
    db.update_content_status(result["content_id"], "telegram_delivered")
    await refresh_pinned_dashboard(query.message.chat_id, context)


async def handle_ready_to_publish(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await _safe_answer(query, "Marked")
    _, content_id = query.data.split("|")
    pipeline.mark_ready_to_publish(content_id)
    await query.edit_message_text(
        query.message.text + "\n\n📤 Marked READY TO PUBLISH — go publish it manually, "
        "then come back and tap Confirm Published."
    )
    await refresh_pinned_dashboard(query.message.chat_id, context)


async def handle_confirm_published(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await _safe_answer(query, "Confirmed")
    _, content_id = query.data.split("|")
    pipeline.mark_confirmed_published(content_id)
    await query.edit_message_text(query.message.text + "\n\n✅ CONFIRMED PUBLISHED. Dashboard updated.")
    await refresh_pinned_dashboard(query.message.chat_id, context)
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
        error_name = type(context.error).__name__
        if error_name in ("NetworkError", "TimedOut"):
            text = "📶 Connection hiccup — nothing broke. Just try that same action again."
        else:
            text = f"⚠️ Something broke: {context.error}\n\n(Full trace in Render's Logs tab.)"
        try:
            await context.bot.send_message(chat_id=update.effective_chat.id, text=text)
        except Exception:
            pass


def _extract_pdf_text(pdf_bytes: bytes) -> str:
    from pypdf import PdfReader
    import io
    reader = PdfReader(io.BytesIO(pdf_bytes))
    return "\n".join(page.extract_text() or "" for page in reader.pages)


def _start_keepalive_server_if_needed():
    """Termux/local fallback ONLY (polling mode). Render (and similar hosts)
    require the app to answer HTTP requests on the assigned port or they
    consider it dead — but as of 2026-09-16 the Render deploy uses
    run_webhook() instead (see main()), which already binds and answers on
    that port itself, so this lightweight server is now skipped whenever
    RENDER_EXTERNAL_URL is set. It only still matters for a polling run
    that nonetheless has a PORT set (rare, kept for safety)."""
    port = os.environ.get("PORT")
    if not port:
        return
    import http.server
    import threading

    class _Health(http.server.BaseHTTPRequestHandler):
        def do_GET(self):
            self.send_response(200)
            self.end_headers()
            self.wfile.write(b"ICOS bot is running.")

        def log_message(self, *args):
            pass  # keep Render's logs from filling up with ping noise

    server = http.server.HTTPServer(("0.0.0.0", int(port)), _Health)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    logger.info(f"Keep-alive server listening on port {port} (Render/cloud mode).")


def main():
    db.init_db()
    app = (
        Application.builder()
        .token(config.TELEGRAM_BOT_TOKEN)
        .post_init(post_init)
        .connect_timeout(30)
        .read_timeout(30)
        .write_timeout(30)
        .pool_timeout(30)
        .build()
    )

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("status", status))
    app.add_handler(CommandHandler("dashboard", dashboard))
    app.add_handler(CommandHandler("generate", generate))
    app.add_handler(CommandHandler("insights", insights))
    app.add_handler(MessageHandler(filters.Document.ALL, handle_document))
    app.add_handler(MessageHandler(filters.PHOTO, handle_screenshot))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))

    app.add_handler(CallbackQueryHandler(handle_menu_choice, pattern=r"^menu\|"))
    app.add_handler(CallbackQueryHandler(handle_tier_choice, pattern=r"^tier\|"))
    app.add_handler(CallbackQueryHandler(handle_platform_choice, pattern=r"^gen\|"))
    app.add_handler(CallbackQueryHandler(handle_refine, pattern=r"^refine\|"))
    app.add_handler(CallbackQueryHandler(handle_ready_to_publish, pattern=r"^ready\|"))
    app.add_handler(CallbackQueryHandler(handle_confirm_published, pattern=r"^confirm\|"))
    app.add_handler(CallbackQueryHandler(handle_engagement_confirm, pattern=r"^engage\|"))
    app.add_handler(CallbackQueryHandler(handle_engagement_show_more, pattern=r"^engagemore\|"))

    app.add_error_handler(on_error)

    # CHANGED 2026-09-16: webhook mode on Render, so the service only needs
    # inbound HTTP (which resets Render's free-tier 15-min spin-down timer)
    # instead of an always-open outbound polling connection (which generates
    # NO inbound traffic and would leave a genuine Free instance asleep
    # almost permanently). RENDER_EXTERNAL_URL is set automatically by
    # Render on every web service — nothing to configure manually. Falls
    # back to polling automatically when that variable is absent (Termux,
    # local dev, or any non-Render environment), so nothing else changes
    # there.
    render_url = os.environ.get("RENDER_EXTERNAL_URL")
    port = int(os.environ.get("PORT", "10000"))
    if render_url:
        webhook_path = config.TELEGRAM_BOT_TOKEN  # token-as-path: only Telegram knows this URL
        logger.info(f"ICOS bot starting in WEBHOOK mode on port {port} ({render_url})...")
        app.run_webhook(
            listen="0.0.0.0",
            port=port,
            url_path=webhook_path,
            webhook_url=f"{render_url}/{webhook_path}",
            secret_token=config.TELEGRAM_BOT_TOKEN.replace(":", ""),
        )
    else:
        _start_keepalive_server_if_needed()
        logger.info("ICOS bot starting in POLLING mode (no RENDER_EXTERNAL_URL set)...")
        app.run_polling()


if __name__ == "__main__":
    main()
