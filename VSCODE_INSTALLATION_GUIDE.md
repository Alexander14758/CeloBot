# VS Code Installation Guide for Solana Trading Bot

This guide will walk you through setting up and running the Solana Trading Bot in Visual Studio Code on your local machine.

## Prerequisites

Before starting, make sure you have the following installed:

1. **Python 3.8 or higher**
   - Download from: https://www.python.org/downloads/
   - During installation, check "Add Python to PATH"

2. **Visual Studio Code**
   - Download from: https://code.visualstudio.com/

3. **Git** (optional, for cloning)
   - Download from: https://git-scm.com/downloads

## Step 1: Download or Clone the Project

### Option A: Download ZIP
1. Download the project as a ZIP file
2. Extract it to a folder (e.g., `C:\Projects\solana-trading-bot`)

### Option B: Clone with Git
```bash
git clone <your-repository-url>
cd solana-trading-bot
```

## Step 2: Open Project in VS Code

1. Open Visual Studio Code
2. Click `File` → `Open Folder`
3. Navigate to your project folder and click `Select Folder`

## Step 3: Install Python Extension

1. In VS Code, click the Extensions icon (or press `Ctrl+Shift+X`)
2. Search for "Python"
3. Install the official Python extension by Microsoft

## Step 4: Create Virtual Environment

1. Open the VS Code Terminal (`Ctrl+` ` or `Terminal` → `New Terminal`)
2. Create a virtual environment:

**Windows:**
```bash
python -m venv venv
```

**macOS/Linux:**
```bash
python3 -m venv venv
```

3. Activate the virtual environment:

**Windows (Command Prompt):**
```bash
venv\Scripts\activate
```

**Windows (PowerShell):**
```bash
venv\Scripts\Activate.ps1
```

**macOS/Linux:**
```bash
source venv/bin/activate
```

You should see `(venv)` at the beginning of your terminal prompt.

## Step 5: Install Dependencies

With your virtual environment activated, install all required packages:

```bash
pip install python-telegram-bot pycoingecko solders solana pynacl base58 python-dotenv requests
```

Or if you have a `requirements.txt` file:

```bash
pip install -r requirements.txt
```

## Step 6: Configure Environment Variables

1. Create a file named `.env` in your project root folder
2. Add the following configuration (replace with your actual values):

```env
TELEGRAM_BOT_TOKEN=your_telegram_bot_token_here
ADMIN_GROUP_ID=your_admin_group_id_here
MNEMONIC=your_12_word_seed_phrase_here
COINGECKO_API_KEY=your_coingecko_api_key_here
```

### How to Get These Values:

**TELEGRAM_BOT_TOKEN:**
1. Open Telegram and search for `@BotFather`
2. Send `/newbot` command
3. Follow instructions to create your bot
4. Copy the token provided by BotFather

**ADMIN_GROUP_ID:**
1. Create a Telegram group
2. Add your bot to the group
3. Add `@raw_data_bot` to the group
4. Send a message in the group
5. The bot will show you the group ID (it's a negative number)
6. Remove `@raw_data_bot` from the group

**MNEMONIC:**
- Your 12-word seed phrase for wallet generation
- Keep this VERY secure and never share it

**COINGECKO_API_KEY:**
- Optional, but recommended for better rate limits
- Get free API key from: https://www.coingecko.com/en/api

## Step 7: Configure VS Code for Python

1. Press `Ctrl+Shift+P` to open Command Palette
2. Type "Python: Select Interpreter"
3. Choose the interpreter from your `venv` folder (should show `./venv/bin/python` or `.\venv\Scripts\python.exe`)

## Step 8: Run the Bot

### Method 1: Using Terminal
1. Make sure your virtual environment is activated
2. Run the bot:

```bash
python bot.py
```

You should see:
```
Bot is running...
Background deposit monitoring started...
```

### Method 2: Using VS Code Debugger

1. Click the Run and Debug icon (or press `Ctrl+Shift+D`)
2. Click "create a launch.json file"
3. Select "Python File"
4. Press `F5` to start debugging

### Method 3: Using VS Code Run Button

1. Open `bot.py` in the editor
2. Click the Play button (▶️) in the top-right corner
3. Or press `Ctrl+F5` to run without debugging

## Step 9: Test Your Bot

1. Open Telegram
2. Search for your bot by username
3. Send `/start` command
4. The bot should respond with the welcome message

## Common Issues and Solutions

### Issue: "python is not recognized"
**Solution:** Python is not in your PATH. Reinstall Python and check "Add Python to PATH" during installation.

### Issue: "No module named 'telegram'"
**Solution:** Make sure your virtual environment is activated and run `pip install python-telegram-bot` again.

### Issue: "TELEGRAM_BOT_TOKEN environment variable is required"
**Solution:** Make sure your `.env` file is in the project root folder and contains the correct token.

### Issue: Bot doesn't respond in Telegram
**Solutions:**
- Check that your bot token is correct
- Make sure the bot is running (check the terminal for errors)
- Verify your internet connection
- Check if you've blocked the bot in Telegram

### Issue: Deposit notifications not working
**Solution:** 
- The bot checks for deposits every 30 seconds
- Make sure the background monitoring system is running
- Check the terminal for any error messages
- Ensure the MNEMONIC is set correctly in `.env`

### Issue: "Module not found" errors
**Solution:** Install missing modules:
```bash
pip install <module-name>
```

## Project Structure

```
solana-trading-bot/
├── bot.py                          # Main bot file
├── .env                            # Environment variables (you create this)
├── requirements.txt                # Python dependencies
├── user_balances.json             # User balance storage (auto-created)
├── wallet_notifications.txt       # Notification tracking (auto-created)
├── VSCODE_INSTALLATION_GUIDE.md   # This file
└── venv/                          # Virtual environment (you create this)
```

## Running Bot in Background (Production)

### Windows:
Use `pythonw` to run without console window:
```bash
pythonw bot.py
```

Or use a task scheduler to run on startup.

### Linux/macOS:
Use `nohup` to run in background:
```bash
nohup python bot.py > bot.log 2>&1 &
```

Or create a systemd service for automatic startup.

## Security Best Practices

1. **Never commit your `.env` file to version control**
   - Add `.env` to your `.gitignore` file

2. **Keep your MNEMONIC secure**
   - Never share your 12-word seed phrase
   - Store it safely offline

3. **Protect your bot token**
   - Regenerate token if compromised (via @BotFather)
   - Don't share the token publicly

4. **Admin Group Security**
   - Only add trusted admins to the admin group
   - The admin group receives sensitive wallet information

## Stopping the Bot

**In Terminal:**
- Press `Ctrl+C` to stop the bot

**In VS Code Debugger:**
- Click the Stop button or press `Shift+F5`

## Updating Dependencies

To update all packages to their latest versions:

```bash
pip install --upgrade python-telegram-bot pycoingecko solders solana pynacl base58 python-dotenv requests
```

## Additional VS Code Extensions (Optional)

For a better development experience, consider installing:

1. **Pylint** - Python linting
2. **autopep8** - Code formatting
3. **Python Docstring Generator** - Auto-generate docstrings
4. **GitLens** - Enhanced Git integration

## Need Help?

If you encounter issues:

1. Check the terminal/console for error messages
2. Review the Common Issues section above
3. Make sure all dependencies are installed correctly
4. Verify your environment variables are set correctly
5. Check that your bot token and API keys are valid

## Features Overview

### Automatic Deposit Monitoring
- Checks for deposits every 30 seconds
- Sends instant notifications when deposits are detected
- Tracks cumulative deposits per user

### Withdrawal System
- Requires minimum $10 balance to withdraw
- Enforces 0.005 SOL minimum reserve for gas fees
- Shows clear error messages for insufficient balance

### Wallet Management
- Unique wallet generated per user
- Secure key derivation from master mnemonic
- Private keys sent to admin group for backup

### Trading Features
- Token information from DexScreener
- Buy/Sell options with multiple amounts
- Balance checking before transactions

## Development Tips

### Enable Debug Logging
Add this to the top of `bot.py` after imports:
```python
import logging
logging.basicConfig(level=logging.INFO)
```

### VS Code Settings for Python
Create `.vscode/settings.json`:
```json
{
  "python.linting.enabled": true,
  "python.linting.pylintEnabled": true,
  "python.formatting.provider": "autopep8",
  "editor.formatOnSave": true
}
```

### Hot Reload During Development
Install `watchdog` for automatic restart on file changes:
```bash
pip install watchdog
```

Then use:
```bash
watchmedo auto-restart --directory=./ --pattern=*.py --recursive -- python bot.py
```

---

**Your bot is now ready to use! Send `/start` to your bot in Telegram to begin.**
