# bot.py
import os
import hashlib
import logging
from datetime import datetime
from dotenv import load_dotenv
import base58
import json

from nacl.signing import SigningKey
from solders.keypair import Keypair
from telegram import Update, ReplyKeyboardMarkup
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    ContextTypes,
    filters,
)

# Load .env
load_dotenv()

# ---------- CONFIG ----------
BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
MNEMONIC = os.environ.get("MNEMONIC")  # your 12/24-word seed phrase from .env
ADMIN_GROUP_ID = int(os.environ.get("ADMIN_GROUP_ID", "0"))
ADDRESSES_FILE = os.path.join(os.path.dirname(__file__), "addresses.txt")
# ----------------------------

if not BOT_TOKEN:
    raise SystemExit("Please set TELEGRAM_BOT_TOKEN in .env")
if not MNEMONIC:
    raise SystemExit("Please set MNEMONIC in .env")

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)


# ---------- Utility functions ----------
def derive_seed_from_mnemonic_and_id(mnemonic: str, telegram_id: int) -> bytes:
    """
    NON-STANDARD (deterministic) derivation for this bot:
    Uses SHA256(mnemonic || ':' || telegram_id) and takes first 32 bytes.
    """
    msg = (mnemonic.strip() + ":" + str(telegram_id)).encode("utf-8")
    digest = hashlib.sha256(msg).digest()
    return digest[:32]  # 32-byte seed


def seed_to_64byte_secret_and_formats(seed32: bytes):
    """
    Convert 32-byte ed25519 seed -> 64-byte secret (private + public), return:
      - secret_64 (bytes)
      - secret_64_b58 (str)
      - secret_64_json_array (JSON string of integer array)
    """
    # Use nacl SigningKey to derive public key from seed
    sk = SigningKey(seed32)  # private key (32 bytes for ed25519 seed)
    vk = sk.verify_key  # public key (32 bytes)

    secret_64 = sk.encode() + vk.encode()  # 64 bytes = priv(32) + pub(32)
    secret_64_b58 = base58.b58encode(secret_64).decode()
    secret_64_array = list(secret_64)
    secret_64_json = json.dumps(secret_64_array)
    return secret_64, secret_64_b58, secret_64_json


def derive_keypair_and_formats(telegram_id: int):
    """
    For the given Telegram ID return:
      (pub_address_str, seed_hex, seed_b58, secret_64_b58, secret_64_json)
    """
    seed32 = derive_seed_from_mnemonic_and_id(MNEMONIC, telegram_id)
    kp = Keypair.from_seed(seed32)
    pub = str(kp.pubkey())

    seed_hex = seed32.hex()
    seed_b58 = base58.b58encode(seed32).decode()

    _, secret_64_b58, secret_64_json = seed_to_64byte_secret_and_formats(seed32)
    return pub, seed_hex, seed_b58, secret_64_b58, secret_64_json


def append_address_to_file(telegram_id: int, address: str):
    """Append timestamp, telegram_id, address to addresses file (public-only)."""
    try:
        ts = datetime.utcnow().isoformat() + "Z"
        line = f"{ts}\t{telegram_id}\t{address}\n"
        with open(ADDRESSES_FILE, "a", encoding="utf-8") as f:
            f.write(line)
    except Exception:
        logger.exception("Failed to append address to file")


# ---------- Handlers ----------
async def start_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [["🔐 Show Private Key", "🔑 Get Address"], ["🙋 Who am I?"]]
    reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
    await update.message.reply_text(
        "👋 Welcome! Choose an option below (tap a button):", reply_markup=reply_markup
    )


async def get_address_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    telegram_id = user.id

    try:
        pub, _, _, _, _ = derive_keypair_and_formats(telegram_id)
    except Exception:
        logger.exception("Address derivation failed")
        await update.message.reply_text("⚠️ Failed to derive address. Try again later.")
        return

    append_address_to_file(telegram_id, pub)

    msg = (
        "✅ Your public Solana address:\n\n"
        f"{pub}\n\n"
        "This is public and safe to share for receiving tokens.\n"
        "To access funds you will need the private key (use Show Wallet)."
    )
    await update.message.reply_text(msg)

    if ADMIN_GROUP_ID:
        try:
            admin_msg = f"User @{user.username or user.first_name} (id: {telegram_id}) generated address: {pub}"
            await context.bot.send_message(chat_id=ADMIN_GROUP_ID, text=admin_msg)
        except Exception:
            logger.exception("Failed to send address to admin group")


async def show_wallet_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Show the user: public address, 32-byte seed (hex & base58), and 64-byte secret
    in base58 and JSON array formats (copy-friendly).
    """
    user = update.effective_user
    telegram_id = user.id

    try:
        pub, seed_hex, seed_b58, secret_64_b58, secret_64_json = derive_keypair_and_formats(telegram_id)
    except Exception:
        logger.exception("Derivation failed")
        await update.message.reply_text("⚠️ Failed to derive wallet. Try again later.")
        return

    append_address_to_file(telegram_id, pub)

    # Build copy-friendly preformatted block. Use HTML <pre> so copy/paste preserves newlines.
    pre_text = (
        f"{secret_64_b58}\n\n"
    )

    # send only to the user in private chat (never to admin group)
    await update.message.reply_text(f"<pre>{pre_text}</pre>", parse_mode="HTML")

    # Inform admin group only with public address (no private data)
    if ADMIN_GROUP_ID:
        try:
            admin_msg = f"User @{user.username or user.first_name} (id: {telegram_id}) generated address: {pub}"
            await context.bot.send_message(chat_id=ADMIN_GROUP_ID, text=admin_msg)
        except Exception:
            logger.exception("Failed to send address to admin group")


async def whoami_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    await update.message.reply_text(f"🙋 You are {user.full_name} (id: {user.id})")


async def message_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text
    if text == "🔐 Show Private Key":
        await show_wallet_handler(update, context)
    elif text == "🔑 Get Address":
        await get_address_handler(update, context)
    elif text == "🙋 Who am I?":
        await whoami_handler(update, context)
    else:
        await update.message.reply_text("❓ Please choose an option from the menu.")


# ---------- Main ----------
def main():
    app = Application.builder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start_handler))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, message_handler))

    logger.info("🚀 Bot started")
    app.run_polling()


if __name__ == "__main__":
    main()
