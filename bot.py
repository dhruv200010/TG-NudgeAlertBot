import os
import logging
import asyncio
from datetime import datetime, timedelta
from dotenv import load_dotenv
from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes

# Load environment variables
load_dotenv()

# Enable logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Debug: Print the token (first few characters for security)
token = os.getenv('TELEGRAM_BOT_TOKEN')
if token:
    logger.info(f"Token found: {token[:5]}...")
else:
    logger.error("No token found in environment variables!")

# Dictionary to store active reminders
active_reminders = {}

# Days of the week mapping
DAYS_OF_WEEK = {
    'mon': 0, 'monday': 0,
    'tue': 1, 'tuesday': 1,
    'wed': 2, 'wednesday': 2,
    'thu': 3, 'thursday': 3,
    'fri': 4, 'friday': 4,
    'sat': 5, 'saturday': 5,
    'sun': 6, 'sunday': 6
}

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Send a message when the command /start is issued."""
    logger.info(f"User {update.effective_user.id} started the bot")
    await update.message.reply_text(
        'Hi! I am a reminder bot. Use /remind <time> <message> to set a reminder.\n'
        'Example: /remind 30m Buy groceries\n'
        'Time formats:\n'
        '- 30s (seconds)\n'
        '- 30m (minutes)\n'
        '- 1h (hours)\n'
        '- 1d (days)\n'
        '- thu (Thursday)\n'
        'You can also set reminders in channels/groups!'
    )

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Send a message when the command /help is issued."""
    logger.info(f"User {update.effective_user.id} requested help")
    await update.message.reply_text(
        'Available commands:\n'
        '/start - Start the bot\n'
        '/help - Show this help message\n'
        '/remind <time> <message> - Set a reminder\n'
        'Time formats:\n'
        '- 30s (seconds)\n'
        '- 30m (minutes)\n'
        '- 1h (hours)\n'
        '- 1d (days)\n'
        '- thu (Thursday)\n'
        '/list - List all active reminders\n'
        '/cancel <reminder_id> - Cancel a reminder'
    )

async def send_reminder(context: ContextTypes.DEFAULT_TYPE):
    """Send the reminder message."""
    job = context.job
    reminder_id = job.data['reminder_id']
    
    if reminder_id in active_reminders:
        reminder = active_reminders[reminder_id]
        logger.info(f"Sending reminder {reminder_id}: {reminder['message']}")
        try:
            await context.bot.send_message(
                chat_id=reminder['chat_id'],
                text=f"⏰ REMINDER: {reminder['message']}"
            )
            del active_reminders[reminder_id]
            logger.info(f"Reminder {reminder_id} sent and removed from active reminders")
        except Exception as e:
            logger.error(f"Error sending reminder {reminder_id}: {str(e)}")

def get_next_day_of_week(target_day):
    """Get the next occurrence of a specific day of the week."""
    today = datetime.now()
    days_ahead = target_day - today.weekday()
    if days_ahead <= 0:  # Target day already happened this week
        days_ahead += 7
    return today + timedelta(days=days_ahead)

async def set_reminder(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Set a reminder."""
    try:
        # Parse the time and message
        args = context.args
        if len(args) < 2:
            logger.warning(f"User {update.effective_user.id} provided insufficient arguments")
            await update.message.reply_text('Please provide time and message. Example: /remind 30m Buy groceries')
            return

        time_str = args[0].lower()
        message = ' '.join(args[1:])
        logger.info(f"User {update.effective_user.id} setting reminder: {time_str} - {message}")
        
        # Parse time
        if time_str.endswith('s'):
            seconds = int(time_str[:-1])
            reminder_time = datetime.now() + timedelta(seconds=seconds)
        elif time_str.endswith('m'):
            minutes = int(time_str[:-1])
            reminder_time = datetime.now() + timedelta(minutes=minutes)
        elif time_str.endswith('h'):
            hours = int(time_str[:-1])
            reminder_time = datetime.now() + timedelta(hours=hours)
        elif time_str.endswith('d'):
            days = int(time_str[:-1])
            reminder_time = datetime.now() + timedelta(days=days)
        elif time_str in DAYS_OF_WEEK:
            target_day = DAYS_OF_WEEK[time_str]
            reminder_time = get_next_day_of_week(target_day)
            # Set time to 10:00 AM
            reminder_time = reminder_time.replace(hour=10, minute=0, second=0, microsecond=0)
        else:
            logger.warning(f"User {update.effective_user.id} provided invalid time format: {time_str}")
            await update.message.reply_text(
                'Invalid time format. Use:\n'
                '- s for seconds (e.g., 30s)\n'
                '- m for minutes (e.g., 30m)\n'
                '- h for hours (e.g., 1h)\n'
                '- d for days (e.g., 1d)\n'
                '- Day of week (e.g., thu for Thursday)'
            )
            return

        # Generate reminder ID
        reminder_id = len(active_reminders) + 1
        
        # Store reminder info
        active_reminders[reminder_id] = {
            'chat_id': update.effective_chat.id,
            'message': message,
            'time': reminder_time
        }
        logger.info(f"Stored reminder {reminder_id} for time {reminder_time}")

        # Schedule the reminder
        context.application.job_queue.run_once(
            send_reminder,
            reminder_time - datetime.now(),
            data={'reminder_id': reminder_id}
        )
        logger.info(f"Scheduled reminder {reminder_id} to run at {reminder_time}")

        await update.message.reply_text(
            f'Reminder set for {reminder_time.strftime("%Y-%m-%d %H:%M:%S")}\n'
            f'Message: {message}\n'
            f'Reminder ID: {reminder_id}'
        )

    except ValueError as e:
        logger.error(f"Error setting reminder: {str(e)}")
        await update.message.reply_text('Invalid time format. Please use numbers followed by s, m, h, or d, or a day of the week.')

async def list_reminders(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """List all active reminders."""
    logger.info(f"User {update.effective_user.id} requested list of reminders")
    if not active_reminders:
        await update.message.reply_text('No active reminders.')
        return

    message = "Active reminders:\n\n"
    for reminder_id, reminder in active_reminders.items():
        message += (
            f"ID: {reminder_id}\n"
            f"Time: {reminder['time'].strftime('%Y-%m-%d %H:%M:%S')}\n"
            f"Message: {reminder['message']}\n\n"
        )
    
    await update.message.reply_text(message)

async def cancel_reminder(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Cancel a reminder."""
    try:
        reminder_id = int(context.args[0])
        logger.info(f"User {update.effective_user.id} attempting to cancel reminder {reminder_id}")
        if reminder_id in active_reminders:
            del active_reminders[reminder_id]
            logger.info(f"Reminder {reminder_id} cancelled successfully")
            await update.message.reply_text(f'Reminder {reminder_id} has been cancelled.')
        else:
            logger.warning(f"User {update.effective_user.id} tried to cancel non-existent reminder {reminder_id}")
            await update.message.reply_text('Reminder not found.')
    except (IndexError, ValueError):
        logger.error(f"User {update.effective_user.id} provided invalid reminder ID")
        await update.message.reply_text('Please provide a valid reminder ID.')

def main():
    """Start the bot."""
    # Create the Application
    TOKEN = "8049839564:AAGw-mLyq5ObsoxecQQGGiHpwfPpz8C2KsE"
    logger.info("Starting bot...")
    
    # Create application with job queue
    application = (
        Application.builder()
        .token(TOKEN)
        .concurrent_updates(True)  # Enable concurrent updates
        .build()
    )
    
    # Add handlers
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CommandHandler("remind", set_reminder))
    application.add_handler(CommandHandler("list", list_reminders))
    application.add_handler(CommandHandler("cancel", cancel_reminder))

    logger.info("Bot started successfully")
    # Start the Bot
    application.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == '__main__':
    main() 