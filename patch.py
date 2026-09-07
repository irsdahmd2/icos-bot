import re

with open("bot.py", "r", encoding="utf-8") as f:
    content = f.read()

results = []

ask_pattern = re.compile(
    r'(await update\.message\.reply_text\(\s*"Which product is this\?.*?\)\s*\n)(\s*context\.user_data\["pending_upload_text"\])',
    re.DOTALL
)
new_ask = (
    'await update.message.reply_text(\n'
    '        "Which product is this?\\n"\n'
    '        + "\\n".join(f"\u2022 {code} \u2014 {name}" for code, name in config.PRODUCTS.items())\n'
    '        + "\\n\\nReply with the PRODUCT_CODE only (e.g. WPPS)"\n'
    '    )\n'
)
if ask_pattern.search(content):
    content = ask_pattern.sub(lambda m: new_ask + m.group(2), content, count=1)
    results.append("ask_block: OK")
elif "Reply with the PRODUCT_CODE only" in content:
    results.append("ask_block: ALREADY PRESENT")
else:
    results.append("ask_block: NOT FOUND")

ht_pattern = re.compile(
    r'@_owner_only\nasync def handle_text\(.*?await update\.message\.reply_text\("Send /start to see available commands\."\)',
    re.DOTALL
)
new_handle_text = '''@_owner_only
async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Catches the product-code reply after a document upload, and other free text."""
    text = update.message.text.strip()

    if "pending_upload_text" in context.user_data:
        product_id = text.split()[0].upper() if text.split() else ""
        if product_id not in config.PRODUCTS:
            await update.message.reply_text("Please reply with just the PRODUCT_CODE.\\nExample: WPPS")
            return

        context.user_data["pending_product_id"] = product_id
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("Full Operating System", callback_data="tier:Full_OS")],
            [InlineKeyboardButton("Handbook", callback_data="tier:Handbook")],
            [InlineKeyboardButton("Codex", callback_data="tier:Codex")],
        ])
        await update.message.reply_text(
            f"\U0001F4C4 {config.PRODUCTS[product_id]} received.\\nPlease confirm the tier.",
            reply_markup=keyboard
        )
        return

    await update.message.reply_text("Send /start to see available commands.")


@_owner_only
async def handle_tier_choice(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handles tier button taps after a product code has been confirmed."""
    query = update.callback_query
    await query.answer()
    tier = query.data.split(":", 1)[1]

    product_id = context.user_data.pop("pending_product_id", None)
    product_text = context.user_data.pop("pending_upload_text", None)
    filename = context.user_data.pop("pending_upload_filename", None)

    if not product_id or product_text is None or filename is None:
        await query.edit_message_text("\u26A0\uFE0F Session expired. Please upload the file again.")
        return

    product_name = config.PRODUCTS[product_id]
    await query.edit_message_text(f"\u2705 {product_name} \u2014 {tier} confirmed.\\nStarting knowledge extraction...")

    ku_ids = pipeline.process_new_product(product_id, product_name, tier, filename, product_text)

    await context.bot.send_message(
        chat_id=update.effective_chat.id,
        text=(
            f"\u2705 Done. Extracted {len(ku_ids)} Knowledge Units from {product_name}.\\n\\n"
            f"Ready to generate content. Send:\\n/generate {product_id}"
        )
    )'''

if "handle_tier_choice" in content:
    results.append("handle_text: ALREADY PRESENT")
elif ht_pattern.search(content):
    content = ht_pattern.sub(lambda m: new_handle_text, content, count=1)
    results.append("handle_text: OK")
else:
    results.append("handle_text: NOT FOUND")

old_import = "Application, CommandHandler, MessageHandler, ContextTypes, filters"
if "CallbackQueryHandler" in content:
    results.append("import: ALREADY PRESENT")
elif old_import in content:
    content = content.replace(old_import, old_import.replace("MessageHandler,", "MessageHandler, CallbackQueryHandler,"))
    results.append("import: OK")
else:
    results.append("import: NOT FOUND")

old_reg = 'app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))'
if 'CallbackQueryHandler(handle_tier_choice)' in content:
    results.append("handler_registration: ALREADY PRESENT")
elif old_reg in content:
    content = content.replace(old_reg, old_reg + '\n    app.add_handler(CallbackQueryHandler(handle_tier_choice))')
    results.append("handler_registration: OK")
else:
    results.append("handler_registration: NOT FOUND")

ok_count = sum(1 for r in results if "OK" in r or "ALREADY PRESENT" in r)
if ok_count == 4:
    with open("bot.py", "w", encoding="utf-8") as f:
        f.write(content)
    print("PATCH APPLIED SUCCESSFULLY")
else:
    print("PATCH ABORTED - NO CHANGES WRITTEN")
for r in results:
    print(r)
