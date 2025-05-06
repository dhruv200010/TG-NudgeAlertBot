# Telegram Reminder Bot

A Telegram bot that can send reminders in groups and channels. The bot allows users to set reminders with custom messages and time intervals.

## Features

- Set reminders with custom messages
- Support for different time formats (minutes, hours, days)
- List all active reminders
- Cancel existing reminders
- Works in both private chats and groups/channels

## Setup

1. Create a new bot using [@BotFather](https://t.me/botfather) on Telegram and get your bot token.

2. Create a `.env` file in the project root and add your bot token:
```
TELEGRAM_BOT_TOKEN=your_bot_token_here
```

3. Install the required dependencies:
```bash
pip install -r requirements.txt
```

4. Run the bot:
```bash
python bot.py
```

## Usage

The bot supports the following commands:

- `/start` - Start the bot and get welcome message
- `/help` - Show help message with available commands
- `/remind <time> <message>` - Set a reminder
  - Time formats: 30m (minutes), 1h (hours), 1d (days)
  - Example: `/remind 30m Buy groceries`
- `/list` - List all active reminders
- `/cancel <reminder_id>` - Cancel a specific reminder

## Adding the Bot to Groups/Channels

1. Add the bot to your group or channel as an administrator
2. Make sure the bot has permission to send messages
3. Start using the reminder commands in the group/channel

## Note

The bot needs to be an administrator in groups/channels to send messages. Make sure to grant the necessary permissions when adding the bot to a group or channel. 