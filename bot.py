import os
import logging
import asyncio
from datetime import datetime, timedelta
from dotenv import load_dotenv
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, ContextTypes, CallbackQueryHandler, ConversationHandler, MessageHandler, filters
import re
from dateutil import parser
import pytz

# Load environment variables from config.env
load_dotenv('config.env', override=True)

# Enable logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Set Central Time zone
CENTRAL_TZ = pytz.timezone('America/Chicago')

def convert_to_central(dt):
    """Convert datetime to Central Time."""
    if dt.tzinfo is None:
        dt = pytz.UTC.localize(dt)
    return dt.astimezone(CENTRAL_TZ)

def get_central_now():
    """Get current time in Central Time."""
    return datetime.now(CENTRAL_TZ)

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

async def get_chat_admins(chat_id: int, bot) -> list:
    """Get all administrators of a chat."""
    try:
        chat_members = await bot.get_chat_administrators(chat_id)
        return [member.user.id for member in chat_members]
    except Exception as e:
        logger.error(f"Error getting chat admins: {str(e)}")
        return []

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Send a message when the command /start is issued."""
    logger.info(f"User {update.effective_user.id} started the bot")
    await update.message.reply_text(
        '👋 Hi! I am NudgeAlertBot, your smart reminder assistant!\n\n'
        'I can help you set reminders in multiple ways:\n\n'
        '📅 Time Formats:\n'
        '- Natural language: "7 may 10:11 am", "tomorrow 9 am"\n'
        '- Quick intervals: 30s, 30m, 1h, 2d\n'
        '- Days of week: mon, tue, wed, thu, fri, sat, sun\n'
        '  (or full names: monday, tuesday, etc.)\n\n'
        '📝 Examples:\n'
        '/remind 30s Take a break\n'
        '/remind 1h Check email\n'
        '/remind 2d Call mom\n'
        '/remind mon Team meeting\n'
        '/remind 7 may 10:11 am Buy groceries\n\n'
        '🔄 Features:\n'
        '- Set reminders in private chats, groups, and channels\n'
        '- Auto-reminders from channel messages\n'
        '- Reschedule or cancel reminders\n'
        '- List all active reminders\n'
        '- Photo reminders with captions\n\n'
        'Type /help for more detailed information!'
    )

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Send a message when the command /help is issued."""
    logger.info(f"User {update.effective_user.id} requested help")
    help_message = await update.message.reply_text(
        '🤖 NudgeAlertBot - Your Smart Reminder Assistant\n\n'
        '📋 Available Commands:\n'
        '/start - Get started with the bot\n'
        '/help - Show this help message\n'
        '/remind <time> <message> - Set a new reminder\n'
        '/list - View all your active reminders\n'
        '/cancel <reminder_id> - Cancel a specific reminder\n\n'
        '⏰ Time Formats:\n'
        '- Natural language: "7 may 10:11 am", "tomorrow 9 am"\n'
        '- Quick intervals: 30s, 30m, 1h, 2d\n'
        '- Days of week: mon, tue, wed, thu, fri, sat, sun\n'
        '  (or full names: monday, tuesday, etc.)\n\n'
        '📝 Example Commands:\n'
        '/remind 30s Take a break\n'
        '/remind 1h Check email\n'
        '/remind 2d Call mom\n'
        '/remind mon Team meeting\n'
        '/remind 7 may 10:11 am Buy groceries\n\n'
        '🔄 Advanced Features:\n'
        '1. Channel Integration:\n'
        '   - Auto-create reminders from channel messages\n'
        '   - Send reminders to all channel admins\n'
        '   - Support for photo messages with captions\n\n'
        '2. Reminder Management:\n'
        '   - Reschedule reminders with quick options\n'
        '   - Cancel reminders anytime\n'
        '   - View all active reminders\n\n'
        '3. Smart Time Parsing:\n'
        '   - Understands natural language dates\n'
        '   - Handles relative times (tomorrow, next week)\n'
        '   - Supports multiple time formats\n\n'
        'Need more help? Just ask!'
    )

    # Auto-delete in groups and channels
    if update.effective_chat.type in ['group', 'supergroup', 'channel']:
        try:
            # Check if the user is an admin
            user = await context.bot.get_chat_member(update.effective_chat.id, update.effective_user.id)
            if user.status in ['creator', 'administrator']:
                logger.info(f"Admin {update.effective_user.id} used /help command in {update.effective_chat.type}")
                bot_member = await context.bot.get_chat_member(update.effective_chat.id, context.bot.id)
                if bot_member.can_delete_messages:
                    async def delete_help():
                        try:
                            await asyncio.sleep(30)
                            # Delete both the command message and the help message
                            await update.message.delete()
                            await help_message.delete()
                            logger.info(f"Successfully deleted /help command and response in {update.effective_chat.type}")
                        except Exception as e:
                            logger.error(f"Error deleting /help messages: {str(e)}")
                    asyncio.create_task(delete_help())
                else:
                    logger.warning(f"Bot doesn't have permission to delete messages in {update.effective_chat.type}")
            else:
                logger.info(f"Non-admin user {update.effective_user.id} used /help command")
        except Exception as e:
            logger.error(f"Error checking permissions for /help command: {str(e)}")

async def send_reminder(context: ContextTypes.DEFAULT_TYPE):
    """Send the reminder message to all admins."""
    job = context.job
    reminder_id = job.data['reminder_id']
    
    if reminder_id in active_reminders:
        reminder = active_reminders[reminder_id]
        logger.info(f"Sending reminder {reminder_id}: {reminder['message']}")
        
        try:
            # Get all admins of the chat
            admin_ids = await get_chat_admins(reminder['chat_id'], context.bot)
            
            # Create keyboard with buttons
            keyboard = [
                [
                    InlineKeyboardButton("Cancel", callback_data=f"cancel:{reminder_id}"),
                    InlineKeyboardButton("Reschedule", callback_data=f"reschedule:{reminder_id}")
                ]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            # Send reminder to each admin
            for admin_id in admin_ids:
                try:
                    if reminder.get('photo_file_id'):
                        logger.info(f"Sending photo reminder with file_id: {reminder['photo_file_id']}")
                        # Send photo with caption
                        await context.bot.send_photo(
                            chat_id=admin_id,
                            photo=reminder['photo_file_id'],
                            caption=f"⏰ REMINDER: {reminder['message']}",
                            reply_markup=reply_markup
                        )
                        logger.info(f"Successfully sent photo reminder to admin {admin_id}")
                    else:
                        # Send text message only
                        await context.bot.send_message(
                            chat_id=admin_id,
                            text=f"⏰ REMINDER: {reminder['message']}",
                            reply_markup=reply_markup
                        )
                        logger.info(f"Successfully sent text reminder to admin {admin_id}")
                except Exception as e:
                    logger.error(f"Error sending reminder to admin {admin_id}: {str(e)}")
                    # Try to send text-only reminder if photo sending fails
                    try:
                        await context.bot.send_message(
                            chat_id=admin_id,
                            text=f"⏰ REMINDER: {reminder['message']}\n(Photo could not be sent)",
                            reply_markup=reply_markup
                        )
                        logger.info(f"Sent text-only reminder to admin {admin_id} after photo failure")
                    except Exception as e2:
                        logger.error(f"Error sending text-only reminder to admin {admin_id}: {str(e2)}")
            
            # Don't delete the reminder here, let it be deleted only when cancelled
            logger.info(f"Reminder {reminder_id} sent to all admins")
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
            await update.message.reply_text('❌ Please provide time and message. Example: /remind 7 may 10:11 am Buy groceries')
            return

        # Find where the time part ends by looking for AM/PM or time pattern
        time_end_index = 0
        for i, arg in enumerate(args):
            if arg.lower() in ['am', 'pm']:
                time_end_index = i + 1
                break
            elif ':' in arg:
                # If we find a time pattern, check if next word is AM/PM
                if i + 1 < len(args) and args[i + 1].lower() in ['am', 'pm']:
                    time_end_index = i + 2
                    break
                else:
                    time_end_index = i + 1
                    break
        
        if time_end_index == 0:
            # If no AM/PM or time pattern found, try to parse the first 3-4 words as time
            time_end_index = min(4, len(args) - 1)
        
        # Join the time parts
        time_str = ' '.join(args[:time_end_index]).lower()
        # Join the remaining parts as message
        message = ' '.join(args[time_end_index:])
        
        logger.info(f"User {update.effective_user.id} setting reminder: {time_str} - {message}")
        
        # Try to parse the time string using dateutil
        try:
            # First try to parse with explicit time
            reminder_time = parser.parse(time_str, fuzzy=True)
            logger.info(f"Successfully parsed time: {reminder_time}")
            
            # Convert to Central Time
            reminder_time = convert_to_central(reminder_time)
            
            # Check if the parsed time has a time component
            if reminder_time.hour == 0 and reminder_time.minute == 0 and reminder_time.second == 0:
                # No time component was provided, set to 10:00 AM Central
                reminder_time = reminder_time.replace(hour=10, minute=0, second=0, microsecond=0)
                logger.info(f"Set default time to 10:00 AM Central: {reminder_time}")
        except Exception as e:
            logger.error(f"Error parsing time: {str(e)}")
            # If parsing fails, set default to 2 days from now at 10 AM Central
            now = get_central_now()
            reminder_time = now + timedelta(days=2)
            reminder_time = reminder_time.replace(hour=10, minute=0, second=0, microsecond=0)
            logger.info(f"Using default time (2 days from now at 10 AM Central): {reminder_time}")

        # If the parsed time is in the past, assume it's for next year
        if reminder_time < get_central_now():
            reminder_time = reminder_time.replace(year=reminder_time.year + 1)
            logger.info(f"Adjusted time to next year: {reminder_time}")

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
            reminder_time - get_central_now(),
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

        # Format the date and time in Central Time
        formatted_date = reminder_time.strftime("%d %b %H:%M %Z")
        confirmation_message = await update.message.reply_text(
            f'✅ Reminder set!\n'
            f'📅 {formatted_date}\n'
            f'📝 Message: {message}\n'
            f'🆔 Reminder ID: {reminder_id}',
            reply_markup=reply_markup,
            parse_mode='HTML'
        )

        # Schedule deletion of confirmation message after 30 seconds if in a group or channel
        if update.effective_chat.type in ['group', 'supergroup', 'channel']:
            try:
                # Check if bot is admin in the group
                bot_member = await context.bot.get_chat_member(update.effective_chat.id, context.bot.id)
                if bot_member.can_delete_messages:
                    async def delete_confirmation():
                        try:
                            await asyncio.sleep(30)  # Wait for 30 seconds
                            await confirmation_message.delete()
                            logger.info(f"Deleted confirmation message for reminder {reminder_id}")
                        except Exception as e:
                            logger.error(f"Error deleting confirmation message: {str(e)}")

                    # Start the deletion task
                    asyncio.create_task(delete_confirmation())
                else:
                    logger.warning("Bot doesn't have permission to delete messages in this group")
            except Exception as e:
                logger.error(f"Error checking bot permissions: {str(e)}")

    except ValueError as e:
        logger.error(f"Error setting reminder: {str(e)}")
        await update.message.reply_text(
            'Invalid time format. Please use:\n'
            '- Natural language (e.g., "7 may 10:11 am", "tomorrow 9 am")\n'
            '- Numbers followed by s, m, h, or d\n'
            '- Day of the week'
        )

async def list_reminders(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """List all active reminders."""
    logger.info(f"User {update.effective_user.id} requested list of reminders")
    if not active_reminders:
        list_message = await update.message.reply_text('No active reminders.')
    else:
        message = "Active reminders:\n\n"
        for reminder_id, reminder in active_reminders.items():
            message += (
                f"ID: {reminder_id}\n"
                f"Time: {reminder['time'].strftime('%Y-%m-%d %H:%M:%S')}\n"
                f"Message: {reminder['message']}\n\n"
            )
        
        # Add a "Cancel All" button
        keyboard = [[InlineKeyboardButton("❌ Cancel All Reminders", callback_data="cancel_all")]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        list_message = await update.message.reply_text(message, reply_markup=reply_markup)

    # Auto-delete in groups and channels
    if update.effective_chat.type in ['group', 'supergroup', 'channel']:
        try:
            # Check if the user is an admin
            user = await context.bot.get_chat_member(update.effective_chat.id, update.effective_user.id)
            if user.status in ['creator', 'administrator']:
                logger.info(f"Admin {update.effective_user.id} used /list command in {update.effective_chat.type}")
                bot_member = await context.bot.get_chat_member(update.effective_chat.id, context.bot.id)
                if bot_member.can_delete_messages:
                    async def delete_list():
                        try:
                            await asyncio.sleep(30)
                            # Delete both the command message and the list message
                            await update.message.delete()
                            await list_message.delete()
                            logger.info(f"Successfully deleted /list command and response in {update.effective_chat.type}")
                        except Exception as e:
                            logger.error(f"Error deleting /list messages: {str(e)}")
                    asyncio.create_task(delete_list())
                else:
                    logger.warning(f"Bot doesn't have permission to delete messages in {update.effective_chat.type}")
            else:
                logger.info(f"Non-admin user {update.effective_user.id} used /list command")
        except Exception as e:
            logger.error(f"Error checking permissions for /list command: {str(e)}")

async def cancel_reminder(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Cancel a reminder."""
    try:
        reminder_id = int(context.args[0])
        logger.info(f"User {update.effective_user.id} attempting to cancel reminder {reminder_id}")
        if reminder_id in active_reminders:
            del active_reminders[reminder_id]
            logger.info(f"Reminder {reminder_id} cancelled successfully")
            confirmation_message = await update.message.reply_text(f'Reminder {reminder_id} has been cancelled.')
            
            # Auto-delete in groups and channels
            if update.effective_chat.type in ['group', 'supergroup', 'channel']:
                try:
                    bot_member = await context.bot.get_chat_member(update.effective_chat.id, context.bot.id)
                    if bot_member.can_delete_messages:
                        async def delete_confirmation():
                            try:
                                await asyncio.sleep(30)
                                await confirmation_message.delete()
                                logger.info(f"Deleted cancellation confirmation message for reminder {reminder_id}")
                            except Exception as e:
                                logger.error(f"Error deleting cancellation confirmation message: {str(e)}")
                        asyncio.create_task(delete_confirmation())
                except Exception as e:
                    logger.error(f"Error checking bot permissions: {str(e)}")
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
        
        if action == 'cancel_all':
            # Clear all reminders
            active_reminders.clear()
            # Cancel all jobs in the job queue
            for job in context.job_queue.jobs():
                job.schedule_removal()
            logger.info("All reminders have been cancelled")
            confirmation_message = await query.message.reply_text("✅ All reminders have been cancelled.")
            
            # Auto-delete in groups and channels
            if query.message.chat.type in ['group', 'supergroup', 'channel']:
                try:
                    # Check if the user is an admin
                    user = await context.bot.get_chat_member(query.message.chat.id, query.from_user.id)
                    if user.status in ['creator', 'administrator']:
                        logger.info(f"Admin {query.from_user.id} cancelled all reminders in {query.message.chat.type}")
                        bot_member = await context.bot.get_chat_member(query.message.chat.id, context.bot.id)
                        if bot_member.can_delete_messages:
                            async def delete_confirmation():
                                try:
                                    await asyncio.sleep(30)
                                    # Delete both the original message and the confirmation
                                    await query.message.delete()
                                    await confirmation_message.delete()
                                    logger.info(f"Successfully deleted cancel all messages in {query.message.chat.type}")
                                except Exception as e:
                                    logger.error(f"Error deleting cancel all messages: {str(e)}")
                            asyncio.create_task(delete_confirmation())
                        else:
                            logger.warning(f"Bot doesn't have permission to delete messages in {query.message.chat.type}")
                except Exception as e:
                    logger.error(f"Error checking permissions for cancel all: {str(e)}")
            return
        
        reminder_id = int(data[1])
        
        logger.info(f"Button callback received - Action: {action}, Reminder ID: {reminder_id}")
        
        if action == 'cancel':
            if reminder_id in active_reminders:
                del active_reminders[reminder_id]
                # Send a new message instead of editing
                confirmation_message = await query.message.reply_text(text=f"❌ Reminder {reminder_id} has been cancelled.")
                
                # Auto-delete in groups and channels
                if query.message.chat.type in ['group', 'supergroup', 'channel']:
                    try:
                        bot_member = await context.bot.get_chat_member(query.message.chat.id, context.bot.id)
                        if bot_member.can_delete_messages:
                            async def delete_confirmation():
                                try:
                                    await asyncio.sleep(30)
                                    await confirmation_message.delete()
                                    logger.info(f"Deleted cancellation confirmation message for reminder {reminder_id}")
                                except Exception as e:
                                    logger.error(f"Error deleting cancellation confirmation message: {str(e)}")
                            asyncio.create_task(delete_confirmation())
                    except Exception as e:
                        logger.error(f"Error checking bot permissions: {str(e)}")
            else:
                await query.message.reply_text(text="❌ Reminder not found.")
        
        elif action == 'reschedule':
            if reminder_id in active_reminders:
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
                        InlineKeyboardButton("📅 Monday", callback_data=f"reschedule_time:{reminder_id}:monday"),
                        InlineKeyboardButton("⚡ Now", callback_data=f"reschedule_time:{reminder_id}:now")
                    ]
                ]
                reply_markup = InlineKeyboardMarkup(keyboard)
                # Send a new message instead of editing
                confirmation_message = await query.message.reply_text(
                    text="⏰ Choose when to reschedule the reminder:",
                    reply_markup=reply_markup
                )
                
                # Auto-delete in groups and channels
                if query.message.chat.type in ['group', 'supergroup', 'channel']:
                    try:
                        bot_member = await context.bot.get_chat_member(query.message.chat.id, context.bot.id)
                        if bot_member.can_delete_messages:
                            async def delete_confirmation():
                                try:
                                    await asyncio.sleep(30)
                                    await confirmation_message.delete()
                                    logger.info(f"Deleted reschedule options message for reminder {reminder_id}")
                                except Exception as e:
                                    logger.error(f"Error deleting reschedule options message: {str(e)}")
                            asyncio.create_task(delete_confirmation())
                    except Exception as e:
                        logger.error(f"Error checking bot permissions: {str(e)}")
            else:
                await query.message.reply_text(text="❌ Reminder not found.")
        
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
                    elif time_option == 'now':
                        # Set to 5 seconds from now for testing
                        new_time = now + timedelta(seconds=5)
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
                    # Send a new message instead of editing
                    confirmation_message = await query.message.reply_text(
                        text=f"✅ Reminder rescheduled!\n"
                             f"📅 {formatted_date}\n"
                             f"🆔 Reminder ID: {reminder_id}",
                        parse_mode='HTML'
                    )
                    
                    # Auto-delete in groups and channels
                    if query.message.chat.type in ['group', 'supergroup', 'channel']:
                        try:
                            bot_member = await context.bot.get_chat_member(query.message.chat.id, context.bot.id)
                            if bot_member.can_delete_messages:
                                async def delete_confirmation():
                                    try:
                                        await asyncio.sleep(30)
                                        await confirmation_message.delete()
                                        logger.info(f"Deleted reschedule confirmation message for reminder {reminder_id}")
                                    except Exception as e:
                                        logger.error(f"Error deleting reschedule confirmation message: {str(e)}")
                                asyncio.create_task(delete_confirmation())
                        except Exception as e:
                            logger.error(f"Error checking bot permissions: {str(e)}")
                else:
                    await query.message.reply_text(text="❌ Reminder not found.")
    
    except Exception as e:
        logger.error(f"Error in button callback: {str(e)}")
        try:
            await query.message.reply_text("❌ An error occurred. Please try again.")
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

async def handle_channel_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle messages in channels and set automatic reminders."""
    logger.info(f"Received message in chat type: {update.effective_chat.type}")
    
    # Check for channel post
    if update.channel_post:
        message = update.channel_post
    elif update.message:
        message = update.message
    else:
        logger.info("No message or channel post found in update")
        return

    # Get the message text or caption
    message_text = None
    photo_file_id = None
    
    # Debug logging for message type
    if message.photo:
        logger.info("Message contains photo")
        # Get the highest quality photo
        photo_file_id = message.photo[-1].file_id
        logger.info(f"Photo file_id: {photo_file_id}")
        if message.caption:
            logger.info(f"Photo has caption: {message.caption}")
            message_text = message.caption
        else:
            logger.info("Photo has no caption")
            message_text = "Photo message"
    elif message.text:
        logger.info(f"Message has text: {message.text}")
        message_text = message.text
    elif message.caption:
        logger.info(f"Message has caption: {message.caption}")
        message_text = message.caption
    else:
        # Handle other message types
        if message.video:
            message_text = "Video message"
        elif message.document:
            message_text = f"Document: {message.document.file_name}"
        elif message.audio:
            message_text = "Audio message"
        elif message.voice:
            message_text = "Voice message"
        else:
            message_text = "Media message"

    # Skip if no message text or caption
    if not message_text:
        logger.info("No message text or caption found")
        return

    # Check if message contains /remind command
    if message_text.startswith('/remind'):
        # Extract the reminder text after /remind
        reminder_text = message_text[7:].strip()
        if not reminder_text:
            logger.info("No reminder text after /remind command")
            return
        message_text = reminder_text
        logger.info(f"Extracted reminder text: {message_text}")

    # Skip if message is from a private chat
    if update.effective_chat.type == 'private':
        logger.info("Skipping private chat message")
        return

    try:
        logger.info(f"Processing message for reminder: {message_text}")
        
        # Try to parse the time from the message
        try:
            # First try to parse with explicit time
            reminder_time = parser.parse(message_text, fuzzy=True)
            logger.info(f"Successfully parsed time: {reminder_time}")
            
            # Convert to Central Time
            reminder_time = convert_to_central(reminder_time)
            
            # Extract the actual reminder message by removing the time part
            time_patterns = [
                r'\b(today|tomorrow|next week|next month)\b',
                r'\b\d{1,2}:\d{2}\s*(?:am|pm)\b',
                r'\b\d{1,2}\s*(?:am|pm)\b',
                r'\b\d{1,2}\s*(?:jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*\b',
                r'\b\d{1,2}\s*(?:january|february|march|april|may|june|july|august|september|october|november|december)\b'
            ]
            
            reminder_message = message_text
            for pattern in time_patterns:
                reminder_message = re.sub(pattern, '', reminder_message, flags=re.IGNORECASE)
            
            # Clean up the message
            reminder_message = ' '.join(reminder_message.split())
            logger.info(f"Extracted reminder message: {reminder_message}")
            
            # Check if the parsed time has a time component
            if reminder_time.hour == 0 and reminder_time.minute == 0 and reminder_time.second == 0:
                # No time component was provided, set to 10:00 AM Central
                reminder_time = reminder_time.replace(hour=10, minute=0, second=0, microsecond=0)
                logger.info(f"Set default time to 10:00 AM Central: {reminder_time}")
        except Exception as e:
            logger.error(f"Error parsing time: {str(e)}")
            # If parsing fails, set default to 2 days from now at 10 AM Central
            now = get_central_now()
            reminder_time = now + timedelta(days=2)
            reminder_time = reminder_time.replace(hour=10, minute=0, second=0, microsecond=0)
            logger.info(f"Using default time (2 days from now at 10 AM Central): {reminder_time}")
            reminder_message = message_text

        # If the parsed time is in the past, assume it's for next year
        if reminder_time < get_central_now():
            reminder_time = reminder_time.replace(year=reminder_time.year + 1)
            logger.info(f"Adjusted time to next year: {reminder_time}")

        # Generate reminder ID
        reminder_id = len(active_reminders) + 1
        
        # Store reminder info
        active_reminders[reminder_id] = {
            'chat_id': update.effective_chat.id,
            'message': reminder_message,
            'time': reminder_time,
            'photo_file_id': photo_file_id  # Store the photo file_id if present
        }
        logger.info(f"Auto-stored reminder {reminder_id} for time {reminder_time}")

        # Schedule the reminder
        context.application.job_queue.run_once(
            send_reminder,
            reminder_time - get_central_now(),
            data={'reminder_id': reminder_id}
        )
        logger.info(f"Auto-scheduled reminder {reminder_id} to run at {reminder_time}")

        # Create keyboard with buttons
        keyboard = [
            [
                InlineKeyboardButton("Cancel", callback_data=f"cancel:{reminder_id}"),
                InlineKeyboardButton("Reschedule", callback_data=f"reschedule:{reminder_id}")
            ]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)

        # Format the date and time in Central Time
        formatted_date = reminder_time.strftime("%d %b %H:%M %Z")
        confirmation_message = await message.reply_text(
            f'⏰ Auto-reminder set!\n'
            f'📅 {formatted_date}\n'
            f'📝 Msg: {reminder_message}\n'
            f'🆔 Reminder ID: {reminder_id}',
            reply_markup=reply_markup,
            parse_mode='HTML'
        )

        # Schedule deletion of confirmation message after 30 seconds
        async def delete_confirmation():
            try:
                await asyncio.sleep(30)  # Wait for 30 seconds
                await confirmation_message.delete()
                logger.info(f"Deleted confirmation message for reminder {reminder_id}")
            except Exception as e:
                logger.error(f"Error deleting confirmation message: {str(e)}")

        # Start the deletion task
        asyncio.create_task(delete_confirmation())

    except Exception as e:
        logger.error(f"Error setting auto-reminder: {str(e)}")
        logger.exception("Full traceback:")

def main():
    """Start the bot."""
    # Get token from environment variable
    TOKEN = os.getenv('TELEGRAM_BOT_TOKEN')
    if not TOKEN:
        logger.error("No TELEGRAM_BOT_TOKEN found in environment variables!")
        return
    
    logger.info("Starting bot...")
    
    # Create application with job queue and increased timeout
    application = (
        Application.builder()
        .token(TOKEN)
        .concurrent_updates(True)  # Enable concurrent updates
        .connect_timeout(30.0)     # Increase connection timeout to 30 seconds
        .read_timeout(30.0)        # Increase read timeout to 30 seconds
        .write_timeout(30.0)       # Increase write timeout to 30 seconds
        .pool_timeout(30.0)        # Increase pool timeout to 30 seconds
        .build()
    )
    
    # Add handlers
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CommandHandler("remind", set_reminder))
    application.add_handler(CommandHandler("list", list_reminders))
    application.add_handler(CommandHandler("cancel", cancel_reminder))
    
    # Add message handler for channel messages - moved before conversation handler
    application.add_handler(MessageHandler(
        (filters.ChatType.CHANNEL | filters.ChatType.GROUP) & ~filters.COMMAND,
        handle_channel_message,
        block=False
    ))
    
    # Add conversation handler for custom time input with per_message=True
    conv_handler = ConversationHandler(
        entry_points=[CallbackQueryHandler(button_callback)],
        states={
            WAITING_FOR_CUSTOM_TIME: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, handle_custom_time, block=False)
            ],
        },
        fallbacks=[],
        per_message=True,  # Changed to True to track each message
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