import os
import logging
import asyncio
from datetime import datetime, timedelta
from dotenv import load_dotenv
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, ContextTypes, CallbackQueryHandler, ConversationHandler, MessageHandler, filters
import re
from dateutil import parser

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

# Add conversation states
WAITING_FOR_CUSTOM_TIME = 1

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
            await update.message.reply_text('❌ Please provide time and message. Example: /remind 30m Buy groceries')
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
                '❌ Invalid time format. Use:\n'
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

        # Create keyboard with buttons
        keyboard = [
            [
                InlineKeyboardButton("Cancel", callback_data=f"cancel:{reminder_id}"),
                InlineKeyboardButton("Reschedule", callback_data=f"reschedule:{reminder_id}")
            ]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)

        # Format the date and time in the new format
        formatted_date = reminder_time.strftime("%d %b %H:%M")
        await update.message.reply_text(
            f'✅ Reminder set!\n'
            f'📅 {formatted_date}\n'
            f'📝 Msg: {message}\n'
            f'🆔 Reminder ID: {reminder_id}',
            reply_markup=reply_markup,
            parse_mode='HTML'
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

async def button_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle button callbacks."""
    query = update.callback_query
    
    try:
        # First answer the callback query to remove the loading state
        await query.answer()
        
        data = query.data.split(':')
        action = data[0]
        reminder_id = int(data[1])
        
        logger.info(f"Button callback received - Action: {action}, Reminder ID: {reminder_id}")
        
        if action == 'cancel':
            if reminder_id in active_reminders:
                del active_reminders[reminder_id]
                await query.edit_message_text(text=f"❌ Reminder {reminder_id} has been cancelled.")
            else:
                await query.edit_message_text(text="❌ Reminder not found.")
        
        elif action == 'reschedule':
            keyboard = [
                [
                    InlineKeyboardButton("2 Days", callback_data=f"reschedule_time:{reminder_id}:2d"),
                    InlineKeyboardButton("🌅 Next Morning", callback_data=f"reschedule_time:{reminder_id}:morning")
                ],
                [
                    InlineKeyboardButton("🌙 Evening", callback_data=f"reschedule_time:{reminder_id}:evening"),
                    InlineKeyboardButton("🏖️ Weekend", callback_data=f"reschedule_time:{reminder_id}:weekend")
                ],
                [
                    InlineKeyboardButton("📅 Monday", callback_data=f"reschedule_time:{reminder_id}:monday")
                ]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            await query.edit_message_text(
                text="⏰ Choose when to reschedule the reminder:",
                reply_markup=reply_markup
            )
        
        elif action == 'reschedule_time':
            if len(data) == 3:
                time_option = data[2]
                logger.info(f"Reschedule time option selected: {time_option}")
                
                if reminder_id in active_reminders:
                    reminder = active_reminders[reminder_id]
                    now = datetime.now()
                    
                    if time_option == '2d':
                        # Set to day after tomorrow at 10 AM
                        new_time = now + timedelta(days=2)
                        new_time = new_time.replace(hour=10, minute=0, second=0, microsecond=0)
                    elif time_option == 'weekend':
                        # Set to next Saturday at 10 AM
                        days_until_saturday = (5 - now.weekday()) % 7  # 5 is Saturday
                        if days_until_saturday == 0:  # If today is Saturday, set for next Saturday
                            days_until_saturday = 7
                        new_time = now + timedelta(days=days_until_saturday)
                        new_time = new_time.replace(hour=10, minute=0, second=0, microsecond=0)
                    elif time_option == 'morning':
                        # Set to next day at 10 AM
                        new_time = now + timedelta(days=1)
                        new_time = new_time.replace(hour=10, minute=0, second=0, microsecond=0)
                    elif time_option == 'evening':
                        # Set to today at 6 PM if it's before 6 PM, otherwise tomorrow
                        new_time = now.replace(hour=18, minute=0, second=0, microsecond=0)
                        if new_time < now:
                            new_time = new_time + timedelta(days=1)
                    elif time_option == 'monday':
                        # Set to next Monday at 10 AM
                        days_until_monday = (0 - now.weekday()) % 7  # 0 is Monday
                        if days_until_monday == 0:  # If today is Monday, set for next Monday
                            days_until_monday = 7
                        new_time = now + timedelta(days=days_until_monday)
                        new_time = new_time.replace(hour=10, minute=0, second=0, microsecond=0)
                    else:
                        return
                    
                    # Update reminder time
                    active_reminders[reminder_id]['time'] = new_time
                    
                    # Reschedule the job
                    context.application.job_queue.run_once(
                        send_reminder,
                        new_time - now,
                        data={'reminder_id': reminder_id}
                    )
                    
                    # Format the date and time in the new format
                    formatted_date = new_time.strftime("%d %b %H:%M")
                    await query.edit_message_text(
                        text=f"✅ Reminder rescheduled!\n"
                             f"📅 {formatted_date} 🆔 : {reminder_id}",
                        parse_mode='HTML'
                    )
    
    except Exception as e:
        logger.error(f"Error in button callback: {str(e)}")
        try:
            await query.edit_message_text("❌ An error occurred. Please try again.")
        except:
            pass
        return ConversationHandler.END

async def handle_custom_time(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle custom time input for rescheduling."""
    logger.info("handle_custom_time called")
    logger.info(f"User data: {context.user_data}")
    
    if 'rescheduling_reminder_id' not in context.user_data:
        logger.error("No rescheduling_reminder_id in user_data")
        await update.message.reply_text("No reminder is being rescheduled.")
        return ConversationHandler.END
    
    reminder_id = context.user_data['rescheduling_reminder_id']
    logger.info(f"Processing custom time for reminder_id: {reminder_id}")
    
    if reminder_id not in active_reminders:
        logger.error(f"Reminder {reminder_id} not found in active_reminders")
        await update.message.reply_text("Reminder not found.")
        return ConversationHandler.END
    
    try:
        # Parse the custom time input
        time_str = update.message.text.lower()
        logger.info(f"Parsing time string: {time_str}")
        
        # Try to parse the input
        try:
            new_time = parser.parse(time_str, fuzzy=True)
            logger.info(f"Successfully parsed time: {new_time}")
        except Exception as e:
            logger.error(f"Error parsing time: {str(e)}")
            # If parsing fails, try to parse just the date and use 10:00 AM
            try:
                # Add 10:00 AM to the date string
                new_time = parser.parse(f"{time_str} 10:00 am", fuzzy=True)
                logger.info(f"Successfully parsed time with default 10:00 AM: {new_time}")
            except Exception as e:
                logger.error(f"Error parsing time with default: {str(e)}")
                raise ValueError("Could not parse the date")
        
        # If the parsed time is in the past, assume it's for next year
        if new_time < datetime.now():
            new_time = new_time.replace(year=new_time.year + 1)
            logger.info(f"Adjusted time to next year: {new_time}")
        
        # Update reminder time
        active_reminders[reminder_id]['time'] = new_time
        
        # Reschedule the job
        context.application.job_queue.run_once(
            send_reminder,
            new_time - datetime.now(),
            data={'reminder_id': reminder_id}
        )
        
        logger.info(f"Successfully rescheduled reminder {reminder_id} for {new_time}")
        await update.message.reply_text(
            f"Reminder rescheduled for {new_time.strftime('%Y-%m-%d %H:%M:%S')}"
        )
        
    except Exception as e:
        logger.error(f"Error parsing custom time: {str(e)}")
        await update.message.reply_text(
            "Sorry, I couldn't understand that time format. Please try again with a format like:\n"
            "- 10 may (will set for 10:00 AM)\n"
            "- 15 june (will set for 10:00 AM)\n"
            "- 10 may 10 am\n"
            "- tomorrow 9 am\n"
            "- next monday 2 pm"
        )
        return WAITING_FOR_CUSTOM_TIME
    
    # Clear the rescheduling reminder ID
    del context.user_data['rescheduling_reminder_id']
    logger.info("Cleared rescheduling_reminder_id from user_data")
    return ConversationHandler.END

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
    
    # Add conversation handler for custom time input
    conv_handler = ConversationHandler(
        entry_points=[CallbackQueryHandler(button_callback)],
        states={
            WAITING_FOR_CUSTOM_TIME: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, handle_custom_time, block=False)
            ],
        },
        fallbacks=[],
        per_message=False,
        name="custom_time_handler",
        persistent=False,
        allow_reentry=True
    )
    application.add_handler(conv_handler)

    logger.info("Bot started successfully")
    # Start the Bot
    application.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == '__main__':
    main() 