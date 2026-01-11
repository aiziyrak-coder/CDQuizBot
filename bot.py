import asyncio
import math
import os
import random
import time
import sys
from datetime import datetime, timezone
from io import BytesIO
from pathlib import Path

# Fix Windows console encoding for emoji
if sys.platform == 'win32':
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardMarkup, KeyboardButton, ReplyKeyboardRemove
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    ConversationHandler,
    ContextTypes,
    filters
)
from telegram.constants import ParseMode, ChatAction
from telegram.error import RetryAfter, TimedOut, TelegramError, Conflict

from database import db, User, Test, Question, Answer, TestResult, UserAnswer, Payment, TestAccess
from file_parser import parse_docx, parse_pdf, validate_parsed_test
from sqlalchemy import select, func, and_, desc
from sqlalchemy.ext.asyncio import AsyncSession

# Telegram message length limits
MAX_MESSAGE_LENGTH = 4096  # Maximum characters per message
SAFE_MESSAGE_LENGTH = 4000  # Safe length to avoid issues

# Rate limiting for message updates
MIN_EDIT_INTERVAL = 2.0  # Minimum seconds between edit_message_text calls
last_edit_time = {}  # Track last edit time per chat_id


async def safe_edit_message(msg, text, parse_mode=None, reply_markup=None, **kwargs):
    """Safely edit message with rate limiting and flood control handling"""
    chat_id = None
    try:
        if hasattr(msg, 'chat_id'):
            chat_id = msg.chat_id
        elif hasattr(msg, 'message') and hasattr(msg.message, 'chat_id'):
            chat_id = msg.message.chat_id
    except:
        pass
    
    # Rate limiting - check last edit time
    if chat_id and chat_id in last_edit_time:
        time_since_last = time.time() - last_edit_time[chat_id]
        if time_since_last < MIN_EDIT_INTERVAL:
            await asyncio.sleep(MIN_EDIT_INTERVAL - time_since_last)
    
    max_retries = 3
    for attempt in range(max_retries):
        try:
            result = await msg.edit_text(text, parse_mode=parse_mode, reply_markup=reply_markup, **kwargs)
            if chat_id:
                last_edit_time[chat_id] = time.time()
            return result
        except RetryAfter as e:
            # Flood control - wait and retry
            wait_time = e.retry_after + 1
            if attempt < max_retries - 1:
                await asyncio.sleep(wait_time)
                continue
            else:
                # Last attempt failed, skip this update
                print(f"[WARNING] Flood control: Skipping message edit after {max_retries} attempts")
                return None
        except TelegramError as e:
            # Other Telegram errors - skip
            error_str = str(e).lower()
            if "message is not modified" in error_str or "message not found" in error_str:
                # Message content is the same or deleted, this is OK
                if chat_id:
                    last_edit_time[chat_id] = time.time()
                return None
            if attempt < max_retries - 1:
                await asyncio.sleep(1)
                continue
            else:
                print(f"[WARNING] Telegram error during edit: {e}")
                return None
        except Exception as e:
            # Other errors - skip after first attempt
            if attempt == 0:
                print(f"[WARNING] Error during message edit: {e}")
            return None
    
    return None


async def safe_send_message(bot, chat_id, text, parse_mode=None, reply_markup=None, **kwargs):
    """Safely send message with flood control handling"""
    max_retries = 3
    for attempt in range(max_retries):
        try:
            if reply_markup:
                return await bot.send_message(chat_id, text, parse_mode=parse_mode, reply_markup=reply_markup, **kwargs)
            else:
                return await bot.send_message(chat_id, text, parse_mode=parse_mode, **kwargs)
        except RetryAfter as e:
            # Flood control - wait and retry
            wait_time = e.retry_after + 1
            if attempt < max_retries - 1:
                await asyncio.sleep(wait_time)
                continue
            else:
                print(f"[WARNING] Flood control: Skipping message send after {max_retries} attempts")
                return None
        except TelegramError as e:
            if attempt < max_retries - 1:
                await asyncio.sleep(1)
                continue
            else:
                print(f"[WARNING] Telegram error during send: {e}")
                return None
        except Exception as e:
            if attempt == 0:
                print(f"[WARNING] Error during message send: {e}")
            return None
    
    return None


async def send_long_message(bot, chat_id, text, parse_mode=None, reply_markup=None, **kwargs):
    """Send a message, splitting it into multiple parts if too long"""
    if len(text) <= MAX_MESSAGE_LENGTH:
        # Use safe_send_message to handle flood control
        result = await safe_send_message(bot, chat_id, text, parse_mode=parse_mode, reply_markup=reply_markup, **kwargs)
        if result:
            return result
        # If failed, try without formatting
        if parse_mode:
            return await safe_send_message(bot, chat_id, text.replace('<b>', '').replace('</b>', '').replace('<code>', '').replace('</code>', ''), reply_markup=reply_markup, **kwargs)
        return None
    
    # Split message into parts
    parts = []
    current_part = ""
    
    # Split by newlines first to keep lines together
    lines = text.split('\n')
    
    for line in lines:
        # Check if adding this line would exceed limit
        if len(current_part) + len(line) + 1 > SAFE_MESSAGE_LENGTH:
            if current_part:
                parts.append(current_part.strip())
            current_part = line + '\n'
        else:
            current_part += line + '\n'
    
    # Add remaining part
    if current_part.strip():
        parts.append(current_part.strip())
    
    # If a single line is too long, split by characters
    if len(parts) == 0 or (len(parts) == 1 and len(parts[0]) > SAFE_MESSAGE_LENGTH):
        parts = []
        while len(text) > SAFE_MESSAGE_LENGTH:
            # Find last space or newline before limit
            split_pos = text.rfind('\n', 0, SAFE_MESSAGE_LENGTH)
            if split_pos == -1:
                split_pos = text.rfind(' ', 0, SAFE_MESSAGE_LENGTH)
            if split_pos == -1:
                split_pos = SAFE_MESSAGE_LENGTH
            
            parts.append(text[:split_pos])
            text = text[split_pos:].lstrip()
        
        if text:
            parts.append(text)
    
    # Send parts with delay to avoid flood control
    sent_messages = []
    for i, part in enumerate(parts):
        # Add delay between messages to avoid flood control (except first message)
        if i > 0:
            await asyncio.sleep(1.5)  # Wait 1.5 seconds between parts
        
        # Only add reply_markup to last message
        msg_markup = reply_markup if i == len(parts) - 1 else None
        
        # Try to send with formatting first
        msg = await safe_send_message(bot, chat_id, part, parse_mode=parse_mode, reply_markup=msg_markup, **kwargs)
        if msg:
            sent_messages.append(msg)
            continue
        
        # If failed, try without formatting
        if parse_mode:
            part_no_html = part.replace('<b>', '').replace('</b>', '').replace('<code>', '').replace('</code>', '').replace('<i>', '').replace('</i>', '')
            msg = await safe_send_message(bot, chat_id, part_no_html, reply_markup=msg_markup, **kwargs)
            if msg:
                sent_messages.append(msg)
                continue
        
        # Last resort: truncate and send
        if len(part) > SAFE_MESSAGE_LENGTH:
            part = part[:SAFE_MESSAGE_LENGTH] + "\n\n...[Xabar kesilgan]"
        msg = await safe_send_message(bot, chat_id, part, reply_markup=msg_markup, **kwargs)
        if msg:
            sent_messages.append(msg)
        elif i == 0:
            # First message failed, stop sending more to avoid flood control
            break
    
    return sent_messages[0] if sent_messages else None


async def edit_long_message(query_or_message, context, text, parse_mode=None, reply_markup=None, **kwargs):
    """Edit a message, handling long messages by splitting"""
    # Get bot instance
    bot = None
    chat_id = None
    message_id = None
    
    # Try to get bot from various sources
    if context and hasattr(context, 'bot'):
        bot = context.bot
    elif hasattr(query_or_message, 'bot'):
        bot = query_or_message.bot
    elif hasattr(query_or_message, 'message') and hasattr(query_or_message.message, 'bot'):
        bot = query_or_message.message.bot
        chat_id = query_or_message.message.chat_id
        message_id = query_or_message.message.message_id
    
    if not bot:
        # Try to get from kwargs
        bot = kwargs.get('bot')
    
    # If message is short enough, try to edit normally
    if len(text) <= MAX_MESSAGE_LENGTH and hasattr(query_or_message, 'edit_message_text'):
        try:
            if reply_markup:
                return await query_or_message.edit_message_text(text, parse_mode=parse_mode, reply_markup=reply_markup, **kwargs)
            else:
                return await query_or_message.edit_message_text(text, parse_mode=parse_mode, **kwargs)
        except Exception as e:
            # If edit fails due to length or other issues, fall through to delete and resend
            error_msg = str(e).lower()
            if "message is too long" in error_msg or "message too long" in error_msg:
                # Message is actually too long, need to split
                pass
            else:
                # Other error, try without formatting
                try:
                    text_no_html = text.replace('<b>', '').replace('</b>', '').replace('<code>', '').replace('</code>', '').replace('<i>', '').replace('</i>', '')
                    if len(text_no_html) > MAX_MESSAGE_LENGTH:
                        text_no_html = text_no_html[:SAFE_MESSAGE_LENGTH] + "\n\n...[Xabar kesilgan]"
                    if reply_markup:
                        return await query_or_message.edit_message_text(text_no_html, reply_markup=reply_markup, **kwargs)
                    else:
                        return await query_or_message.edit_message_text(text_no_html, **kwargs)
                except:
                    pass
    
    # Message too long or edit failed - delete and send as new messages
    # Get chat_id and message_id from query if not already set
    if not chat_id and hasattr(query_or_message, 'message'):
        chat_id = query_or_message.message.chat_id
        message_id = query_or_message.message.message_id
    
    if bot and chat_id:
        # Delete old message if possible
        if message_id:
            try:
                await bot.delete_message(chat_id=chat_id, message_id=message_id)
            except:
                pass
        
        # Send new message(s)
        return await send_long_message(bot, chat_id, text, parse_mode=parse_mode, reply_markup=reply_markup, **kwargs)
    elif hasattr(query_or_message, 'edit_message_text'):
        # Last resort: try to edit without formatting (truncated)
        try:
            text_no_html = text.replace('<b>', '').replace('</b>', '').replace('<code>', '').replace('</code>', '').replace('<i>', '').replace('</i>', '')
            if len(text_no_html) > MAX_MESSAGE_LENGTH:
                text_no_html = text_no_html[:SAFE_MESSAGE_LENGTH] + "\n\n...[Xabar kesilgan]"
            if reply_markup:
                return await query_or_message.edit_message_text(text_no_html, reply_markup=reply_markup, **kwargs)
            else:
                return await query_or_message.edit_message_text(text_no_html, **kwargs)
        except Exception as e:
            # If everything fails and we have bot, try to get chat_id from message and send new
            if bot and hasattr(query_or_message, 'message'):
                try:
                    await query_or_message.message.delete()
                except:
                    pass
                if hasattr(query_or_message.message, 'chat_id'):
                    chat_id = query_or_message.message.chat_id
                    return await send_long_message(bot, chat_id, text, parse_mode=parse_mode, reply_markup=reply_markup, **kwargs)

# Bot token
BOT_TOKEN = "8450348603:AAFluXVOO99MevP6MfdT9UkbsSXqf3WvPIg"

# Constants
ADMIN_GROUP_ID = -5143660617
ADMIN_IDS = [5573250102, 6417011612]  # Admin ID'lari ro'yxati
TEST_CREATION_COST = 0.0  # Test yaratish bepul
PAYMENT_AMOUNTS = [10000, 20000, 50000]
CARD_NUMBER = "5614 6887 1938 3324"
# Bot username will be fetched dynamically from bot info

# Conversation states
WAITING_FOR_TEST_NAME, WAITING_FOR_TEST_FILE, WAITING_FOR_PAYMENT_SCREENSHOT, TAKING_TEST = range(4)


def calculate_test_cost(question_count: int) -> float:
    """
    Calculate test cost based on number of questions.
    - 100 tagacha: 10000 so'm
    - Har 100 ta qo'shilganda: 5000 so'm qo'shiladi
    Masalan: 178 ta = 15000 so'm, 200 ta = 20000 so'm, 299 ta = 20000 so'm
    """
    base_price = 10000.0
    if question_count <= 100:
        return base_price
    # 100 dan ortiq bo'lsa, har 100 ta uchun 5000 so'm qo'shiladi
    # 101-199: 1 ta qo'shimcha (15000), 200-299: 2 ta qo'shimcha (20000), va hokazo
    if question_count < 200:
        return base_price + 5000.0  # 101-199: 15000
    if question_count < 300:
        return base_price + 10000.0  # 200-299: 20000
    # 300 dan boshlab har 100 ta uchun 5000 so'm qo'shiladi
    additional_100s = math.ceil((question_count - 300) / 100.0)
    return base_price + 10000.0 + (additional_100s * 5000.0)  # 20000 + qo'shimcha


async def get_or_create_user(telegram_id: int, username: str = None, first_name: str = None) -> User:
    """Get or create user"""
    async with db.async_session() as session:
        result = await session.execute(select(User).where(User.telegram_id == telegram_id))
        user = result.scalar_one_or_none()
        
        if not user:
            user = User(telegram_id=telegram_id, username=username, first_name=first_name, balance=0.0)
            session.add(user)
            await session.commit()
            await session.refresh(user)
        else:
            # Update username if changed
            if username and user.username != username:
                user.username = username
                if first_name:
                    user.first_name = first_name
                await session.commit()
        
        return user


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Start command handler"""
    user = await get_or_create_user(
        update.effective_user.id,
        update.effective_user.username,
        update.effective_user.first_name
    )
    
    # Check if user came via test link (e.g., /start test_123)
    if context.args and len(context.args) > 0:
        start_param = context.args[0]
        if start_param.startswith("test_"):
            try:
                test_id = int(start_param.split("_")[1])
                # Handle test start via deep link
                from telegram import User as TGUser
                
                # Handle test start via deep link - directly call test start logic
                async with db.async_session() as session:
                    result = await session.execute(select(Test).where(Test.id == test_id))
                    test = result.scalar_one_or_none()
                    
                    if not test:
                        await update.message.reply_text("❌ Test topilmadi!")
                        return
                    
                    # Check if user has access
                    result = await session.execute(
                        select(TestAccess).where(
                            and_(
                                TestAccess.user_id == user.telegram_id,
                                TestAccess.test_id == test_id
                            )
                        )
                    )
                    test_access = result.scalar_one_or_none()
                    
                    # Get questions count to calculate cost
                    result = await session.execute(
                        select(func.count(Question.id)).where(Question.test_id == test_id)
                    )
                    question_count = result.scalar() or 0
                    test_cost = calculate_test_cost(question_count)
                    
                    if not test_access:
                        if user.balance < test_cost:
                            text = (
                                f"⚠️ <b>Balansingiz yetarli emas!</b>\n\n"
                                f"Testni bajarish uchun {test_cost:,.0f} so'm kerak.\n"
                                f"Sizning balansingiz: {user.balance:,.0f} so'm\n\n"
                                f"Balansni to'ldiring va testni yechishni boshlang.\n"
                                f"💡 <b>Eslatma:</b> Bir marta to'laganingizdan keyin, bu testni cheksiz yechishingiz mumkin."
                            )
                            keyboard = [
                                [InlineKeyboardButton("💳 Balansni to'ldirish", callback_data="topup_balance")],
                                [InlineKeyboardButton("⬅️ Bosh menyu", callback_data="back_to_menu")]
                            ]
                            reply_markup = InlineKeyboardMarkup(keyboard)
                            await update.message.reply_text(text, reply_markup=reply_markup, parse_mode=ParseMode.HTML)
                            return
                        
                        # Deduct balance and create test access
                        user.balance -= test_cost
                        test_access = TestAccess(
                            user_id=user.telegram_id,
                            test_id=test_id
                        )
                        session.add(test_access)
                        await session.merge(user)
                        await session.commit()
                    
                    # Get questions
                    result = await session.execute(
                        select(Question).where(Question.test_id == test_id).order_by(Question.question_number)
                    )
                    questions = result.scalars().all()
                    
                    if not questions:
                        await update.message.reply_text("❌ Testda savollar topilmadi!")
                        return
                    
                    # Create test result
                    test_result = TestResult(
                        test_id=test_id,
                        user_id=user.telegram_id,
                        correct_answers=0,
                        wrong_answers=0,
                        skipped_answers=0,
                        duration_seconds=0
                    )
                    session.add(test_result)
                    await session.flush()
                    
                    # Store start time
                    context.user_data[f'test_start_{test_result.id}'] = time.time()
                    context.user_data[f'test_current_question_{test_result.id}'] = 0
                    
                    await session.commit()
                    
                    # Create fake query for show_question
                    class FakeQuery:
                        def __init__(self, msg):
                            self.message = msg
                            self.edit_message_text = lambda text, reply_markup=None, parse_mode=None: msg.reply_text(text, reply_markup=reply_markup, parse_mode=parse_mode)
                        
                        async def answer(self, text="", show_alert=False):
                            pass
                    
                    fake_query = FakeQuery(update.message)
                    await show_question(fake_query, context, test_result.id, 0)
                return
            except (ValueError, IndexError):
                pass  # Invalid test ID, show normal menu
    
    welcome_text = (
        "👋 <b>Xush kelibsiz!</b>\n\n"
        "Bu bot orqali siz:\n"
        "✅ Testlar yaratishingiz mumkin (BEPUL)\n"
        "✅ Boshqa foydalanuvchilar tomonidan yaratilgan testlarni yechishingiz mumkin\n"
        "✅ Natijalaringizni ko'rishingiz va yetakchilar jadvalidagi o'rningizni bilishingiz mumkin\n\n"
        "Quyidagi funksiyalardan foydalaning:"
    )
    
    keyboard = [
        [
            InlineKeyboardButton("📝 Test yaratish", callback_data="create_test"),
            InlineKeyboardButton("📋 Testlar ro'yxati", callback_data="test_list")
        ],
        [
            InlineKeyboardButton("💰 Hisobim", callback_data="my_account"),
            InlineKeyboardButton("💳 Balansni to'ldirish", callback_data="topup_balance")
        ]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await update.message.reply_text(
        welcome_text,
        reply_markup=reply_markup,
        parse_mode=ParseMode.HTML
    )


async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle inline button clicks"""
    query = update.callback_query
    await query.answer()
    
    data = query.data
    
    # Skip create_test here - it's handled by ConversationHandler entry point
    if data == "create_test":
        return
    elif data == "test_list":
        await handle_test_list(query, context)
    elif data == "my_account":
        await handle_my_account(query, context)
    elif data == "topup_balance":
        # Clear waiting payment state if canceling
        if context.user_data.get('waiting_payment'):
            context.user_data.pop('waiting_payment', None)
            context.user_data.pop('pending_payment_id', None)
            context.user_data.pop('expected_amount', None)
        await handle_topup_balance(query, context)
    elif data.startswith("test_"):
        try:
            test_id = int(data.split("_")[1])
            await handle_start_test(query, context, test_id)
        except (ValueError, IndexError) as e:
            print(f"[ERROR] Test callback parsing error: {e}")
            await query.answer("❌ Xatolik! Test topilmadi.", show_alert=True)
    elif data.startswith("answer_"):
        try:
            parts = data.split("_")
            if len(parts) < 4:
                await query.answer("❌ Xatolik! Qaytadan urinib ko'ring.", show_alert=True)
                return
            test_result_id = int(parts[1])
            question_id = int(parts[2])
            answer_id = int(parts[3]) if parts[3] != "skip" else None
            await handle_answer_question(query, context, test_result_id, question_id, answer_id)
        except (ValueError, IndexError) as e:
            print(f"[ERROR] Answer callback parsing error: {e}")
            await query.answer("❌ Xatolik! Qaytadan urinib ko'ring.", show_alert=True)
    elif data.startswith("topup_") and data != "topup_balance":
        try:
            amount = int(data.split("_")[1])
            await handle_select_topup_amount(query, context, amount)
        except (ValueError, IndexError) as e:
            print(f"[ERROR] Topup callback parsing error: {e}")
            await query.answer("❌ Xatolik! Qaytadan urinib ko'ring.", show_alert=True)
    elif data.startswith("continue_test_"):
        try:
            # Handle continue test callback
            test_result_id = int(data.split("_")[2])
            await handle_continue_test(query, context, test_result_id)
        except (ValueError, IndexError) as e:
            print(f"[ERROR] Continue test callback parsing error: {e}")
            await query.answer("❌ Xatolik! Qaytadan urinib ko'ring.", show_alert=True)
    elif data.startswith("restart_test_"):
        try:
            # Handle restart test callback
            test_id = int(data.split("_")[2])
            await handle_restart_test(query, context, test_id)
        except (ValueError, IndexError) as e:
            print(f"[ERROR] Restart test callback parsing error: {e}")
            await query.answer("❌ Xatolik! Qaytadan urinib ko'ring.", show_alert=True)
    elif data == "back_to_menu":
        await start_from_callback(query, context)


async def start_from_callback(query, context):
    """Start command from callback"""
    user = await get_or_create_user(
        query.from_user.id,
        query.from_user.username,
        query.from_user.first_name
    )
    
    welcome_text = (
        "👋 <b>Xush kelibsiz!</b>\n\n"
        "Bu bot orqali siz:\n"
        "✅ Testlar yaratishingiz mumkin\n"
        "✅ Boshqa foydalanuvchilar tomonidan yaratilgan testlarni yechishingiz mumkin\n"
        "✅ Natijalaringizni ko'rishingiz va yetakchilar jadvalidagi o'rningizni bilishingiz mumkin\n\n"
        "Quyidagi funksiyalardan foydalaning:"
    )
    
    keyboard = [
        [
            InlineKeyboardButton("📝 Test yaratish", callback_data="create_test"),
            InlineKeyboardButton("📋 Testlar ro'yxati", callback_data="test_list")
        ],
        [
            InlineKeyboardButton("💰 Hisobim", callback_data="my_account"),
            InlineKeyboardButton("💳 Balansni to'ldirish", callback_data="topup_balance")
        ]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await query.edit_message_text(
        welcome_text,
        reply_markup=reply_markup,
        parse_mode=ParseMode.HTML
    )


async def handle_create_test(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle test creation start - ConversationHandler entry point"""
    query = update.callback_query
    if query:
        await query.answer()
    
    user = await get_or_create_user(
        query.from_user.id if query else update.effective_user.id,
        query.from_user.username if query else update.effective_user.username,
        query.from_user.first_name if query else update.effective_user.first_name
    )
    
    # Test yaratish bepul, balans tekshiruvi kerak emas
    text = (
        "📝 <b>Test yaratish</b>\n\n"
        "Test nomini kiriting:"
    )
    keyboard = [[InlineKeyboardButton("⬅️ Orqaga", callback_data="back_to_menu")]]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    if query:
        await query.edit_message_text(text, reply_markup=reply_markup, parse_mode=ParseMode.HTML)
    else:
        await update.message.reply_text(text, reply_markup=reply_markup, parse_mode=ParseMode.HTML)
    
    # Return next state
    return WAITING_FOR_TEST_NAME


async def handle_back_to_menu_in_conversation(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle back_to_menu callback in conversation - returns END to exit conversation"""
    # This will be called from button_handler, not from ConversationHandler
    # So we just return END if we're in a conversation
    if update.callback_query:
        await update.callback_query.answer()
        context.user_data.clear()
        await start_from_callback(update.callback_query, context)
    return ConversationHandler.END


async def receive_test_name(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Receive test name"""
    # Check if it's a callback query (back button)
    if update.callback_query and update.callback_query.data == "back_to_menu":
        await update.callback_query.answer()
        context.user_data.clear()
        await start_from_callback(update.callback_query, context)
        return ConversationHandler.END
    
    if update.message.text == "⬅️ Bekor qilish" or update.message.text == "⬅️ Orqaga":
        context.user_data.clear()
        await update.message.reply_text(
            "❌ Test yaratish bekor qilindi.",
            reply_markup=ReplyKeyboardRemove()
        )
        await start(update, context)
        return ConversationHandler.END
    
    test_name = update.message.text.strip()
    
    if len(test_name) < 3:
        await update.message.reply_text("❌ Test nomi juda qisqa. Kamida 3 ta belgi kiriting:")
        return WAITING_FOR_TEST_NAME
    
    context.user_data['test_name'] = test_name
    
    instruction_text = (
        "📄 <b>Test faylini yuklang</b>\n\n"
        "Quyidagi formatda Word (.docx) yoki PDF fayl yuklang:\n\n"
        "📌 <b>Format ko'rsatmalari:</b>\n"
        "• <code>++++</code> belgisi yangi testni boshlaydi\n"
        "• Savollar tartib raqam bilan beriladi (masalan: <code>1. Savol matni</code>)\n"
        "• Javoblar <code>====</code> bilan ajratiladi\n"
        "• To'g'ri javob oldiga <code>#</code> belgisi qo'yiladi\n\n"
        "<b>Misol:</b>\n"
        "<code>++++\n"
        "1. Nechinchi yilda federal hukumat...?\n"
        "====\n"
        "#1950 va 1960-yillarda\n"
        "====\n"
        "1960 yilda\n"
        "====\n"
        "1974 yilda\n"
        "====\n"
        "1975 yilda</code>\n\n"
        "Word yoki PDF fayl yuklang:"
    )
    
    keyboard = [[KeyboardButton("⬅️ Bekor qilish")]]
    reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
    
    await update.message.reply_text(
        instruction_text,
        reply_markup=reply_markup,
        parse_mode=ParseMode.HTML
    )
    
    return WAITING_FOR_TEST_FILE


async def receive_test_file(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Receive and process test file"""
    # Check if it's a callback query (back button)
    if update.callback_query and update.callback_query.data == "back_to_menu":
        await update.callback_query.answer()
        context.user_data.clear()
        await start_from_callback(update.callback_query, context)
        return ConversationHandler.END
    
    user = await get_or_create_user(
        update.effective_user.id,
        update.effective_user.username,
        update.effective_user.first_name
    )
    
    # Test yaratish bepul, balans tekshiruvi kerak emas
    
    if not (update.message.document or update.message.photo):
        if update.message.text == "⬅️ Bekor qilish" or update.message.text == "⬅️ Orqaga":
            context.user_data.clear()
            await update.message.reply_text(
                "❌ Test yaratish bekor qilindi.",
                reply_markup=ReplyKeyboardRemove()
            )
            await start(update, context)
            return ConversationHandler.END
        
        await update.message.reply_text(
            "❌ Iltimos, Word (.docx) yoki PDF fayl yuklang yoki 'Bekor qilish' tugmasini bosing."
        )
        return WAITING_FOR_TEST_FILE
    
    file = None
    file_extension = None
    
    if update.message.document:
        file = await context.bot.get_file(update.message.document.file_id)
        file_name = update.message.document.file_name.lower()
        if file_name.endswith('.docx'):
            file_extension = 'docx'
        elif file_name.endswith('.pdf'):
            file_extension = 'pdf'
        else:
            await update.message.reply_text(
                "❌ Faqat Word (.docx) yoki PDF fayllar qabul qilinadi."
            )
            return WAITING_FOR_TEST_FILE
    else:
        await update.message.reply_text(
            "❌ Iltimos, fayl sifatida yuklang (document, emas rasmi)."
        )
        return WAITING_FOR_TEST_FILE
    
    # Show typing action - fayl tahlil qilinmoqda
    await context.bot.send_chat_action(chat_id=update.message.chat_id, action=ChatAction.TYPING)
    
    # Show initial progress message
    progress_msg = await update.message.reply_text(
        "⏳ <b>Fayl qabul qilindi. Tahlil qilinmoqda...</b>\n\n"
        "Iltimos, kuting. Bu biroz vaqt olishi mumkin.",
        parse_mode=ParseMode.HTML
    )
    
    # Download file
    try:
        file_bytes = BytesIO()
        await file.download_to_memory(file_bytes)
        file_bytes.seek(0)
    except Exception as e:
        await progress_msg.edit_text(
            f"❌ Faylni yuklashda xatolik: {str(e)[:200]}",
            parse_mode=ParseMode.HTML
        )
        context.user_data.clear()
        return ConversationHandler.END
    
    # Parse file - get all tests
    try:
        # Update progress - parsing
        await safe_edit_message(
            progress_msg,
            "⏳ <b>Fayl tahlil qilinmoqda...</b>\n\n"
            "Testlar ajratilmoqda. Iltimos, kuting...",
            parse_mode=ParseMode.HTML
        )
        try:
            await context.bot.send_chat_action(chat_id=update.message.chat_id, action=ChatAction.TYPING)
        except:
            pass
        
        if file_extension == 'docx':
            parsed_tests = parse_docx(file_bytes.read(), return_all=True)
        else:
            parsed_tests = parse_pdf(file_bytes.read(), return_all=True)
        
        if not parsed_tests or len(parsed_tests) == 0:
            await safe_edit_message(
                progress_msg,
                "❌ <b>Test fayli to'g'ri formatda emas.</b>\n\n"
                "Iltimos, ko'rsatilgan formatda fayl yuklang.",
                parse_mode=ParseMode.HTML,
                reply_markup=ReplyKeyboardRemove()
            )
            context.user_data.clear()
            return ConversationHandler.END
        
        # Get bot username once (needed for links)
        bot_info = await context.bot.get_me()
        bot_username = bot_info.username
        
        # Update progress - creating tests
        await safe_edit_message(
            progress_msg,
            f"⏳ <b>Testlar yaratilmoqda...</b>\n\n"
            f"Topilgan testlar: {len(parsed_tests)} ta\n"
            f"Ma'lumotlar bazasiga saqlanmoqda. Iltimos, kuting...",
            parse_mode=ParseMode.HTML
        )
        try:
            await context.bot.send_chat_action(chat_id=update.message.chat_id, action=ChatAction.TYPING)
        except:
            pass
        
        # Combine all parsed tests into one test (all questions in one test)
        all_questions = []
        for parsed_test in parsed_tests:
            # Validate parsed test
            is_valid, message = validate_parsed_test(parsed_test)
            if not is_valid:
                continue  # Skip invalid tests
            
            # Add all questions from this parsed test
            all_questions.extend(parsed_test['questions'])
        
        # Check if we have any questions
        if len(all_questions) == 0:
            await safe_edit_message(
                progress_msg,
                "❌ <b>Hech qanday to'g'ri test topilmadi.</b>\n\n"
                "Iltimos, fayl formati to'g'riligini tekshiring.",
                parse_mode=ParseMode.HTML,
                reply_markup=ReplyKeyboardRemove()
            )
            context.user_data.clear()
            return ConversationHandler.END
        
        # Sort questions by question_number to maintain order
        all_questions.sort(key=lambda x: x['question_number'])
        
        # Update progress - creating single test
        await safe_edit_message(
            progress_msg,
            f"⏳ <b>Test yaratilmoqda...</b>\n\n"
            f"Topilgan savollar: {len(all_questions)} ta\n"
            f"Ma'lumotlar bazasiga saqlanmoqda. Iltimos, kuting...",
            parse_mode=ParseMode.HTML
        )
        try:
            await context.bot.send_chat_action(chat_id=update.message.chat_id, action=ChatAction.TYPING)
        except:
            pass
        
        # Create ONE test with all questions
        test_name = context.user_data['test_name']
        total_questions = len(all_questions)
        
        async with db.async_session() as session:
            # Save file
            files_dir = Path("test_files")
            files_dir.mkdir(exist_ok=True)
            
            # Create single test
            test = Test(
                creator_id=user.telegram_id,
                name=test_name
            )
            session.add(test)
            await session.flush()
            
            # Save file
            file_path = files_dir / f"test_{test.id}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.{file_extension}"
            file_bytes.seek(0)
            with open(file_path, 'wb') as f:
                f.write(file_bytes.read())
            test.file_path = str(file_path)
            
            # Create all questions and answers in one test
            for q_data in all_questions:
                question = Question(
                    test_id=test.id,
                    question_number=q_data['question_number'],  # Use actual number from file
                    question_text=q_data['question_text']
                )
                session.add(question)
                await session.flush()
                
                # Add answers
                letters = ['A', 'B', 'C', 'D', 'E', 'F']
                for idx, answer_data in enumerate(q_data['answers']):
                    answer = Answer(
                        question_id=question.id,
                        answer_text=answer_data['text'],
                        is_correct=answer_data['is_correct'],
                        answer_letter=letters[idx] if idx < len(letters) else chr(ord('A') + idx)
                    )
                    session.add(answer)
                
                # Update progress every 20 questions to avoid flood control
                if q_data['question_number'] % 20 == 0:
                    try:
                        await safe_edit_message(
                            progress_msg,
                            f"⏳ <b>Test yaratilmoqda...</b>\n\n"
                            f"Saqlangan savollar: {q_data['question_number']}/{total_questions} ta\n"
                            f"Ma'lumotlar bazasiga saqlanmoqda. Iltimos, kuting...",
                            parse_mode=ParseMode.HTML
                        )
                    except:
                        pass
            
            await session.commit()
        
        # Generate ONE link for the single test
        test_link = f"https://t.me/{bot_username}?start=test_{test.id}"
        
        # Check if test was created successfully
        if total_questions == 0:
            await safe_edit_message(
                progress_msg,
                "❌ <b>Hech qanday to'g'ri test topilmadi.</b>\n\n"
                "Iltimos, fayl formati to'g'riligini tekshiring.",
                parse_mode=ParseMode.HTML,
                reply_markup=ReplyKeyboardRemove()
            )
            context.user_data.clear()
            return ConversationHandler.END
        
        # Update progress - finalizing
        await safe_edit_message(
            progress_msg,
            f"✅ <b>Test yaratildi!</b>\n\n"
            f"Jami savollar: {total_questions} ta\n\n"
            f"Natijalar tayyorlanmoqda...",
            parse_mode=ParseMode.HTML
        )
        try:
            await context.bot.send_chat_action(chat_id=update.message.chat_id, action=ChatAction.TYPING)
        except:
            pass
        
        # Send success message with single link (one test with all questions)
        success_text = (
            f"✅ <b>Test muvaffaqiyatli yaratildi!</b>\n\n"
            f"📝 <b>Test nomi:</b> {test_name}\n"
            f"❓ <b>Jami savollar:</b> {total_questions} ta\n\n"
            f"🔗 <b>Test linki:</b>\n"
            f"<code>{test_link}</code>\n\n"
            f"📤 <b>Testni bajarish uchun:</b>\n"
            f"• Yuqoridagi linkni bosing yoki nusxalab boshqa foydalanuvchilar bilan ulashing\n"
            f"• Yoki 'Testlar ro'yxati' bo'limidan testni tanlang\n\n"
            f"💵 <b>Test bajarish narxi:</b> {calculate_test_cost(total_questions):,.0f} so'm\n"
            f"💰 Bir marta to'lagandan keyin, testni cheksiz yechish mumkin."
        )
        
        bot = context.bot if context and hasattr(context, 'bot') else update.message.bot
        # Delete progress message and send final result
        try:
            await progress_msg.delete()
        except:
            pass
        await send_long_message(
            bot,
            update.message.chat_id,
            success_text,
            parse_mode=ParseMode.HTML,
            reply_to_message_id=update.message.message_id
        )
        
        # Test creation is complete, no need for additional message
        
        context.user_data.clear()
        await start(update, context)
        
    except Exception as e:
        error_msg = str(e)
        # Try to delete progress message if exists
        try:
            if 'progress_msg' in locals():
                await safe_edit_message(
                    progress_msg,
                    "❌ <b>Xatolik yuz berdi!</b>\n\n"
                    "Testlar yaratishda muammo bo'ldi.",
                    parse_mode=ParseMode.HTML
                )
        except:
            pass
        
        # Check error type and handle appropriately
        if "Message is too long" in error_msg or "message is too long" in error_msg:
            await safe_send_message(
                context.bot,
                update.message.chat_id,
                "❌ Xatolik: Xabar juda uzun.\n\nIltimos, fayldagi testlar sonini kamaytiring yoki adminlarga murojaat qiling.",
                reply_markup=ReplyKeyboardRemove()
            )
        elif "flood control" in error_msg.lower() or "retry after" in error_msg.lower():
            # Flood control error - inform user and suggest retry
            await safe_send_message(
                context.bot,
                update.message.chat_id,
                "⚠️ Telegram flood control limitiga tushildi.\n\n"
                "Ko'p testlar yaratilmoqda. Biroz kuting va qayta urinib ko'ring.\n"
                "Yoki fayldagi testlar sonini kamaytiring.",
                reply_markup=ReplyKeyboardRemove()
            )
        else:
            # Truncate error message if too long
            error_text = f"❌ Xatolik yuz berdi: {error_msg[:500]}\n\nIltimos, fayl formati to'g'riligini tekshiring."
            if len(error_text) > MAX_MESSAGE_LENGTH:
                error_text = error_text[:SAFE_MESSAGE_LENGTH] + "..."
            await safe_send_message(
                context.bot,
                update.message.chat_id,
                error_text,
                reply_markup=ReplyKeyboardRemove()
            )
        context.user_data.clear()
    
    return ConversationHandler.END


async def handle_test_list(query, context):
    """Show list of available tests"""
    async with db.async_session() as session:
        result = await session.execute(
            select(Test).order_by(desc(Test.created_at))
        )
        tests = result.scalars().all()
    
    if not tests:
        text = "📋 Hozircha testlar mavjud emas."
        keyboard = [[InlineKeyboardButton("⬅️ Orqaga", callback_data="back_to_menu")]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.edit_message_text(text, reply_markup=reply_markup)
        return
    
    # Build keyboard first (buttons don't count in message length)
    keyboard = []
    for test in tests:
        test_name_display = test.name[:40] + "..." if len(test.name) > 40 else test.name
        keyboard.append([
            InlineKeyboardButton(
                f"📝 {test_name_display}",
                callback_data=f"test_{test.id}"
            )
        ])
    
    keyboard.append([InlineKeyboardButton("⬅️ Orqaga", callback_data="back_to_menu")])
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    # Build text message with limited tests to avoid too long message
    text = "📋 <b>Mavjud testlar:</b>\n\n"
    max_tests_in_message = 30  # Limit tests shown in text
    
    # Count questions for first batch of tests
    for i, test in enumerate(tests[:max_tests_in_message]):
        async with db.async_session() as session:
            result = await session.execute(
                select(func.count(Question.id)).where(Question.test_id == test.id)
            )
            question_count = result.scalar() or 0
        
        # Truncate test name if too long
        test_name_display = test.name[:50] + "..." if len(test.name) > 50 else test.name
        text += f"📝 {test_name_display}\n"
        text += f"   Savollar: {question_count} ta\n\n"
    
    if len(tests) > max_tests_in_message:
        text += f"... va yana {len(tests) - max_tests_in_message} ta test.\n\n"
        text += "Yuqoridagi tugmalardan barcha testlarni ko'rishingiz mumkin."
    
    # Use edit_long_message to handle long messages
    await edit_long_message(query, context, text, parse_mode=ParseMode.HTML, reply_markup=reply_markup)


async def handle_start_test(query, context, test_id: int):
    """Start taking a test"""
    # Handle both callback query and message (deep link)
    if hasattr(query, 'from_user'):
        user_id = query.from_user.id
        username = query.from_user.username
        first_name = query.from_user.first_name
    else:
        # For deep links via start command
        user_id = context._effective_user.id if hasattr(context, '_effective_user') else None
        username = None
        first_name = None
    
    if not user_id:
        if hasattr(query, 'message'):
            user_id = query.message.from_user.id
            username = query.message.from_user.username
            first_name = query.message.from_user.first_name
        else:
            await query.reply_text("❌ Xatolik! Qaytadan urinib ko'ring.")
            return
    
    user = await get_or_create_user(user_id, username, first_name)
    
    async with db.async_session() as session:
        result = await session.execute(select(Test).where(Test.id == test_id))
        test = result.scalar_one_or_none()
        
        if not test:
            if hasattr(query, 'answer'):
                await query.answer("❌ Test topilmadi!", show_alert=True)
            elif hasattr(query, 'message'):
                await query.message.reply_text("❌ Test topilmadi!")
            elif hasattr(query, 'reply_text'):
                await query.reply_text("❌ Test topilmadi!")
            return
        
        # Check if user has already paid for this test
        result = await session.execute(
            select(TestAccess).where(
                and_(
                    TestAccess.user_id == user.telegram_id,
                    TestAccess.test_id == test_id
                )
            )
        )
        test_access = result.scalar_one_or_none()
        
        # Get questions count to calculate cost
        result = await session.execute(
            select(func.count(Question.id)).where(Question.test_id == test_id)
        )
        question_count = result.scalar() or 0
        test_cost = calculate_test_cost(question_count)
        
        # If not paid, check balance and require payment
        if not test_access:
            if user.balance < test_cost:
                text = (
                    f"⚠️ <b>Balansingiz yetarli emas!</b>\n\n"
                    f"Testni bajarish uchun {test_cost:,.0f} so'm kerak.\n"
                    f"Sizning balansingiz: {user.balance:,.0f} so'm\n\n"
                    f"Balansni to'ldiring va testni yechishni boshlang.\n"
                    f"💡 <b>Eslatma:</b> Bir marta to'laganingizdan keyin, bu testni cheksiz yechishingiz mumkin."
                )
                keyboard = [
                    [InlineKeyboardButton("💳 Balansni to'ldirish", callback_data="topup_balance")],
                    [InlineKeyboardButton("⬅️ Orqaga", callback_data="back_to_menu")]
                ]
                reply_markup = InlineKeyboardMarkup(keyboard)
                if hasattr(query, 'edit_message_text'):
                    await query.edit_message_text(text, reply_markup=reply_markup, parse_mode=ParseMode.HTML)
                elif hasattr(query, 'message'):
                    await query.message.reply_text(text, reply_markup=reply_markup, parse_mode=ParseMode.HTML)
                elif hasattr(query, 'reply_text'):
                    await query.reply_text(text, reply_markup=reply_markup, parse_mode=ParseMode.HTML)
                return
            
            # Deduct balance and create test access
            user.balance -= test_cost
            test_access = TestAccess(
                user_id=user.telegram_id,
                test_id=test_id
            )
            session.add(test_access)
            await session.merge(user)
            await session.commit()
        
        # Check for incomplete test result (test boshlangan lekin tugatilmagan)
        result = await session.execute(
            select(TestResult).where(
                and_(
                    TestResult.test_id == test_id,
                    TestResult.user_id == user.telegram_id,
                    TestResult.completed_at.is_(None)  # Tugatilmagan test
                )
            ).order_by(TestResult.id.desc()).limit(1)
        )
        incomplete_result = result.scalar_one_or_none()
        
        # Get total questions count
        result = await session.execute(
            select(func.count(Question.id)).where(Question.test_id == test_id)
        )
        total_questions = result.scalar() or 0
        
        if incomplete_result:
            # Count answered questions
            result = await session.execute(
                select(func.count(UserAnswer.id)).where(
                    and_(
                        UserAnswer.test_result_id == incomplete_result.id,
                        UserAnswer.is_skipped == False
                    )
                )
            )
            answered_count = result.scalar() or 0
            
            # Check if all questions answered (should not happen, but safety check)
            if answered_count >= total_questions:
                # All answered but not finished - auto finish it
                incomplete_result.completed_at = datetime.now(timezone.utc)
                await session.commit()
                incomplete_result = None
        
        if incomplete_result:
            # User has incomplete test - offer to continue or restart
            text = (
                f"📝 <b>\"{test.name[:60] if len(test.name) > 60 else test.name}\" testi</b>\n\n"
                f"Siz allaqachon ushbu testni boshlagansiz.\n\n"
                f"📊 <b>Joriy holat:</b>\n"
                f"✅ To'g'ri: {incomplete_result.correct_answers}\n"
                f"❌ Xato: {incomplete_result.wrong_answers}\n"
                f"⏭️ O'tkazib yuborilgan: {incomplete_result.skipped_answers}\n"
                f"📋 Javob berilgan: {answered_count}/{total_questions}\n\n"
                f"Qanday davom etamiz?"
            )
            keyboard = [
                [
                    InlineKeyboardButton("▶️ Davom ettirish", callback_data=f"continue_test_{incomplete_result.id}"),
                    InlineKeyboardButton("🔄 Yangidan boshlash", callback_data=f"restart_test_{test_id}")
                ],
                [InlineKeyboardButton("⬅️ Orqaga", callback_data="back_to_menu")]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            if hasattr(query, 'edit_message_text'):
                await query.edit_message_text(text, reply_markup=reply_markup, parse_mode=ParseMode.HTML)
            elif hasattr(query, 'message'):
                await query.message.reply_text(text, reply_markup=reply_markup, parse_mode=ParseMode.HTML)
            elif hasattr(query, 'reply_text'):
                await query.reply_text(text, reply_markup=reply_markup, parse_mode=ParseMode.HTML)
            return
        
        # Get questions
        result = await session.execute(
            select(Question).where(Question.test_id == test_id).order_by(Question.question_number)
        )
        questions = result.scalars().all()
        
        if not questions:
            if hasattr(query, 'answer'):
                await query.answer("❌ Testda savollar topilmadi!", show_alert=True)
            elif hasattr(query, 'message'):
                await query.message.reply_text("❌ Testda savollar topilmadi!")
            elif hasattr(query, 'reply_text'):
                await query.reply_text("❌ Testda savollar topilmadi!")
            return
        
        # Create new test result
        test_result = TestResult(
            test_id=test_id,
            user_id=user.telegram_id,
            correct_answers=0,
            wrong_answers=0,
            skipped_answers=0,
            duration_seconds=0,
            completed_at=None  # Test tugatilmagan
        )
        session.add(test_result)
        await session.flush()
        
        # Store start time
        context.user_data[f'test_start_{test_result.id}'] = time.time()
        context.user_data[f'test_current_question_{test_result.id}'] = 0
        
        await session.commit()
    
    # Show first question
    await show_question(query, context, test_result.id, 0)


async def handle_continue_test(query, context, test_result_id: int):
    """Continue an incomplete test"""
    await query.answer()
    
    async with db.async_session() as session:
        result = await session.execute(select(TestResult).where(TestResult.id == test_result_id))
        test_result = result.scalar_one_or_none()
        
        if not test_result or test_result.completed_at is not None:
            # Test not found or already completed
            if hasattr(query, 'edit_message_text'):
                await query.edit_message_text("❌ Test topilmadi yoki allaqachon tugatilgan!", parse_mode=ParseMode.HTML)
            elif hasattr(query, 'message'):
                await query.message.reply_text("❌ Test topilmadi yoki allaqachon tugatilgan!")
            return
        
        # Get user ID
        user_id = query.from_user.id if hasattr(query, 'from_user') else None
        if not user_id and hasattr(query, 'message'):
            user_id = query.message.from_user.id
        
        if user_id and test_result.user_id != user_id:
            if hasattr(query, 'answer'):
                await query.answer("❌ Sizda bu testni davom ettirish uchun ruxsat yo'q!", show_alert=True)
            return
        
        # Get all questions
        result = await session.execute(
            select(Question).where(Question.test_id == test_result.test_id).order_by(Question.question_number)
        )
        all_questions = result.scalars().all()
        
        # Find first unanswered question - check all UserAnswers (both skipped and answered)
        result = await session.execute(
            select(UserAnswer.question_id).where(
                UserAnswer.test_result_id == test_result_id
            )
        )
        answered_question_ids = set([row[0] for row in result.all()])
        
        # Find next unanswered question index
        next_question_index = len(all_questions)  # Default to end (all answered)
        for i, question in enumerate(all_questions):
            if question.id not in answered_question_ids:
                next_question_index = i
                break
        
        # If all answered, finish the test
        if next_question_index >= len(all_questions):
            # Mark as completed and show results
            test_result.completed_at = datetime.now(timezone.utc)
            await session.commit()
            await finish_test(query, context, test_result_id)
            return
        
        # Restore start time if not exists
        if f'test_start_{test_result_id}' not in context.user_data:
            context.user_data[f'test_start_{test_result_id}'] = time.time()
        
        context.user_data[f'test_current_question_{test_result_id}'] = next_question_index
    
    # Show question from where user left off
    await show_question(query, context, test_result_id, next_question_index)


async def handle_restart_test(query, context, test_id: int):
    """Restart a test (mark old incomplete result as finished and start new)"""
    await query.answer()
    
    async with db.async_session() as session:
        # Get user
        user_id = query.from_user.id if hasattr(query, 'from_user') else None
        if not user_id and hasattr(query, 'message'):
            user_id = query.message.from_user.id
        
        if not user_id:
            if hasattr(query, 'answer'):
                await query.answer("❌ Xatolik!", show_alert=True)
            return
        
        user = await get_or_create_user(
            user_id,
            query.from_user.username if hasattr(query, 'from_user') else None,
            query.from_user.first_name if hasattr(query, 'from_user') else None
        )
        
        # Mark old incomplete results as completed (with a flag to indicate restart)
        result = await session.execute(
            select(TestResult).where(
                and_(
                    TestResult.test_id == test_id,
                    TestResult.user_id == user.telegram_id,
                    TestResult.completed_at.is_(None)
                )
            )
        )
        incomplete_results = result.scalars().all()
        
        for old_result in incomplete_results:
            old_result.completed_at = datetime.now(timezone.utc)
        
        await session.commit()
        
        # Now start fresh test
        await handle_start_test(query, context, test_id)


async def show_question(query, context, test_result_id: int, question_index: int):
    """Show question with answer options as a new message"""
    async with db.async_session() as session:
        result = await session.execute(select(TestResult).where(TestResult.id == test_result_id))
        test_result = result.scalar_one_or_none()
        
        if not test_result:
            return
        
        # Get all questions for this test
        result = await session.execute(
            select(Question).where(Question.test_id == test_result.test_id).order_by(Question.question_number)
        )
        all_questions = result.scalars().all()
        
        if question_index >= len(all_questions):
            # Test completed
            await finish_test(query, context, test_result_id)
            return
        
        question = all_questions[question_index]
        
        # Get answers
        result = await session.execute(
            select(Answer).where(Answer.question_id == question.id)
        )
        answers = list(result.scalars().all())  # Convert to list for shuffling
        
        # Shuffle answers to randomize their order (but keep original answer_id intact)
        # This ensures different order each time test is shown, but correct answer tracking remains correct
        shuffled_answers = answers.copy()
        random.shuffle(shuffled_answers)
        
        # Assign new display letters (A, B, C, D, etc.) to shuffled answers
        letters = ['A', 'B', 'C', 'D', 'E', 'F', 'G', 'H']
        for idx, answer in enumerate(shuffled_answers):
            if idx < len(letters):
                answer.display_letter = letters[idx]
            else:
                answer.display_letter = chr(ord('A') + idx)
        
        # Check if user already answered this question
        result = await session.execute(
            select(UserAnswer).where(
                and_(
                    UserAnswer.test_result_id == test_result_id,
                    UserAnswer.question_id == question.id
                )
            )
        )
        existing_answer = result.scalar_one_or_none()
        
        # Format question text
        text = f"<b>[{question_index + 1}/{len(all_questions)}]</b>\n\n"
        text += f"{question.question_text}\n\n"
        
        keyboard = []
        for answer in shuffled_answers:
            # Show existing answer status
            prefix = ""
            if existing_answer:
                if existing_answer.answer_id == answer.id:
                    if existing_answer.is_correct:
                        prefix = "✅ "
                    elif not existing_answer.is_skipped:
                        prefix = "❌ "
            
            # Use display_letter instead of answer_letter for randomized display
            display_letter = getattr(answer, 'display_letter', answer.answer_letter)
            keyboard.append([
                InlineKeyboardButton(
                    f"{prefix}{display_letter}. {answer.answer_text[:50]}",
                    callback_data=f"answer_{test_result_id}_{question.id}_{answer.id}"
                )
            ])
        
        # Skip button
        keyboard.append([
            InlineKeyboardButton(
                "⏭️ O'tkazib yuborish",
                callback_data=f"answer_{test_result_id}_{question.id}_skip"
            )
        ])
        
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        # Get chat_id and message to reply to
        chat_id = None
        reply_to_message_id = None
        
        if hasattr(query, 'message'):
            chat_id = query.message.chat_id
            reply_to_message_id = query.message.message_id
        elif hasattr(query, 'from_user'):
            # For callback queries, use from_user.id as chat_id
            chat_id = query.from_user.id
            if hasattr(query, 'message') and query.message:
                reply_to_message_id = query.message.message_id
        
        # Send as new message (not edit)
        bot = context.bot if context and hasattr(context, 'bot') else None
        if not bot and hasattr(query, 'bot'):
            bot = query.bot
        elif not bot and hasattr(query, 'message') and hasattr(query.message, 'bot'):
            bot = query.message.bot
        
        if bot and chat_id:
            sent_msg = await bot.send_message(
                chat_id=chat_id,
                text=text,
                reply_markup=reply_markup,
                parse_mode=ParseMode.HTML,
                reply_to_message_id=reply_to_message_id
            )
            # Store last message ID for next question
            context.user_data[f'last_question_msg_{test_result_id}'] = sent_msg.message_id
        else:
            # Fallback to old method
            if hasattr(query, 'edit_message_text'):
                await query.edit_message_text(text, reply_markup=reply_markup, parse_mode=ParseMode.HTML)
            elif hasattr(query, 'message'):
                await query.message.reply_text(text, reply_markup=reply_markup, parse_mode=ParseMode.HTML)
            elif hasattr(query, 'reply_text'):
                await query.reply_text(text, reply_markup=reply_markup, parse_mode=ParseMode.HTML)
        
        # Update current question index
        context.user_data[f'test_current_question_{test_result_id}'] = question_index


async def handle_answer_question(query, context, test_result_id: int, question_id: int, answer_id: int):
    """Handle answer selection"""
    await query.answer()
    
    async with db.async_session() as session:
        # Get test result
        result = await session.execute(select(TestResult).where(TestResult.id == test_result_id))
        test_result = result.scalar_one_or_none()
        
        # Get user ID from query
        user_id = query.from_user.id if hasattr(query, 'from_user') else None
        if not user_id and hasattr(query, 'message'):
            user_id = query.message.from_user.id
        
        if not test_result or (user_id and test_result.user_id != user_id):
            if hasattr(query, 'answer'):
                await query.answer("❌ Xatolik!", show_alert=True)
            return
        
        # Check if already answered
        result = await session.execute(
            select(UserAnswer).where(
                and_(
                    UserAnswer.test_result_id == test_result_id,
                    UserAnswer.question_id == question_id
                )
            )
        )
        existing_answer = result.scalar_one_or_none()
        
        is_correct = False  # Initialize is_correct
        selected_answer = None
        
        if answer_id is None:
            # Skipped
            is_correct = False
            if existing_answer:
                old_skipped = existing_answer.is_skipped
                old_correct = existing_answer.is_correct
                
                existing_answer.is_skipped = True
                existing_answer.is_correct = False
                existing_answer.answer_id = None
                
                # Update counters
                if not old_skipped:
                    if old_correct:
                        test_result.correct_answers = max(0, test_result.correct_answers - 1)
                    else:
                        test_result.wrong_answers = max(0, test_result.wrong_answers - 1)
                    test_result.skipped_answers += 1
            else:
                user_answer = UserAnswer(
                    test_result_id=test_result_id,
                    question_id=question_id,
                    answer_id=None,
                    is_correct=False,
                    is_skipped=True
                )
                session.add(user_answer)
                test_result.skipped_answers += 1
        else:
            # Get selected answer
            result = await session.execute(select(Answer).where(Answer.id == answer_id))
            selected_answer = result.scalar_one_or_none()
            
            if not selected_answer:
                if hasattr(query, 'answer'):
                    await query.answer("❌ Xatolik!", show_alert=True)
                return
            
            is_correct = selected_answer.is_correct
            
            if existing_answer:
                # Update existing answer
                old_correct = existing_answer.is_correct
                old_skipped = existing_answer.is_skipped
                
                existing_answer.answer_id = answer_id
                existing_answer.is_correct = is_correct
                existing_answer.is_skipped = False
                
                # Update counters based on old vs new answer
                if old_skipped:
                    test_result.skipped_answers = max(0, test_result.skipped_answers - 1)
                elif old_correct:
                    test_result.correct_answers = max(0, test_result.correct_answers - 1)
                elif not old_correct and not old_skipped:
                    test_result.wrong_answers = max(0, test_result.wrong_answers - 1)
                
                # Add new answer counters
                if is_correct:
                    test_result.correct_answers += 1
                else:
                    test_result.wrong_answers += 1
            else:
                # New answer
                user_answer = UserAnswer(
                    test_result_id=test_result_id,
                    question_id=question_id,
                    answer_id=answer_id,
                    is_correct=is_correct,
                    is_skipped=False
                )
                session.add(user_answer)
                
                if is_correct:
                    test_result.correct_answers += 1
                else:
                    test_result.wrong_answers += 1
        
        # Get correct answer for feedback (before committing)
        result = await session.execute(
            select(Answer).where(
                and_(
                    Answer.question_id == question_id,
                    Answer.is_correct == True
                )
            )
        )
        correct_answer_obj = result.scalar_one_or_none()
        
        # Store correct answer info for feedback (before session closes)
        # Note: We don't use answer_letter in feedback since answers are shuffled each time
        correct_answer_exists = correct_answer_obj is not None
        correct_answer_text = correct_answer_obj.answer_text if correct_answer_obj else ""
        
        await session.commit()
    
    # Get current question index
    current_index = context.user_data.get(f'test_current_question_{test_result_id}', 0)
    
    # Get chat_id and message for feedback
    chat_id = None
    if hasattr(query, 'message'):
        chat_id = query.message.chat_id
    elif hasattr(query, 'from_user'):
        chat_id = query.from_user.id
    
    bot = context.bot if context and hasattr(context, 'bot') else None
    if not bot and hasattr(query, 'bot'):
        bot = query.bot
    elif not bot and hasattr(query, 'message') and hasattr(query.message, 'bot'):
        bot = query.message.bot
    
    # Show feedback message with animation based on answer
    if answer_id is not None:
        # Answer was selected
        if is_correct:
            # Correct answer - green animation
            feedback_text = "✅ <b>To'g'ri!</b> 🎉"
            feedback_emoji = "✅"
        else:
            # Wrong answer - red animation with correct answer
            if correct_answer_exists:
                feedback_text = f"❌ <b>Noto'g'ri.</b>\n\n✅ To'g'ri javob: <b>{correct_answer_text}</b>"
            else:
                feedback_text = "❌ <b>Noto'g'ri.</b> To'g'ri javob topilmadi."
            feedback_emoji = "❌"
    else:
        # Skipped - show correct answer
        if correct_answer_exists:
            feedback_text = f"⏭️ <b>O'tkazib yuborildi.</b>\n\n✅ To'g'ri javob: <b>{correct_answer_text}</b>"
        else:
            feedback_text = "⏭️ <b>O'tkazib yuborildi.</b>"
        feedback_emoji = "⏭️"
    
    # Answer callback query with animation
    if hasattr(query, 'answer'):
        # Use emoji for visual feedback
        await query.answer(feedback_emoji, show_alert=False)
    
    # Send feedback as a message with animation
    if bot and chat_id:
        # Get last question message to reply to
        last_msg_id = context.user_data.get(f'last_question_msg_{test_result_id}')
        
        # Send feedback message
        try:
            feedback_msg = await bot.send_message(
                chat_id=chat_id,
                text=feedback_text,
                parse_mode=ParseMode.HTML,
                reply_to_message_id=last_msg_id
            )
        except Exception as e:
            print(f"[WARNING] Feedback message send error: {e}")
            feedback_msg = None
        
        # Wait a moment for user to see feedback
        await asyncio.sleep(1.5)
        
        # Show next question automatically
        await show_question(query, context, test_result_id, current_index + 1)
    else:
        # Fallback: show alert and then next question
        if hasattr(query, 'answer'):
            alert_text = feedback_text.replace('<b>', '').replace('</b>', '')
            if len(alert_text) > 200:
                alert_text = alert_text[:197] + "..."
            await query.answer(alert_text, show_alert=True)
        
        # Wait a moment for user to see feedback
        await asyncio.sleep(1.5)
        
        # Show next question
        await show_question(query, context, test_result_id, current_index + 1)


async def finish_test(query, context, test_result_id: int):
    """Finish test and show results"""
    async with db.async_session() as session:
        result = await session.execute(select(TestResult).where(TestResult.id == test_result_id))
        test_result = result.scalar_one_or_none()
        
        if not test_result:
            return
        
        # Calculate duration
        start_time = context.user_data.get(f'test_start_{test_result_id}', time.time())
        duration = int(time.time() - start_time)
        test_result.duration_seconds = duration
        
        # Get test info
        result = await session.execute(select(Test).where(Test.id == test_result.test_id))
        test = result.scalar_one_or_none()
        
        # Count actual skipped answers from UserAnswer records
        result = await session.execute(
            select(func.count(UserAnswer.id)).where(
                and_(
                    UserAnswer.test_result_id == test_result_id,
                    UserAnswer.is_skipped == True
                )
            )
        )
        actual_skipped = result.scalar() or 0
        test_result.skipped_answers = actual_skipped
        
        # Get total questions for verification
        result = await session.execute(
            select(func.count(Question.id)).where(Question.test_id == test_result.test_id)
        )
        total_questions = result.scalar() or 0
        
        # Check for previous best result (get maximum correct answers from all previous attempts)
        result = await session.execute(
            select(func.max(TestResult.best_correct)).where(
                and_(
                    TestResult.test_id == test_result.test_id,
                    TestResult.user_id == test_result.user_id,
                    TestResult.id != test_result_id
                )
            )
        )
        previous_best_correct = result.scalar() or 0
        
        # Get the best previous result details if exists
        if previous_best_correct > 0:
            result = await session.execute(
                select(TestResult).where(
                    and_(
                        TestResult.test_id == test_result.test_id,
                        TestResult.user_id == test_result.user_id,
                        TestResult.id != test_result_id,
                        TestResult.best_correct == previous_best_correct
                    )
                ).order_by(TestResult.best_duration).limit(1)
            )
            previous_best = result.scalar_one_or_none()
            
            # Update best score if this attempt is better
            if previous_best and (test_result.correct_answers > previous_best_correct or \
               (test_result.correct_answers == previous_best_correct and duration < previous_best.best_duration)):
                test_result.best_correct = test_result.correct_answers
                test_result.best_wrong = test_result.wrong_answers
                test_result.best_skipped = test_result.skipped_answers
                test_result.best_duration = duration
                test_result.best_score = test_result.correct_answers
            elif previous_best:
                # Keep previous best
                test_result.best_correct = previous_best.best_correct
                test_result.best_wrong = previous_best.best_wrong
                test_result.best_skipped = previous_best.best_skipped
                test_result.best_duration = previous_best.best_duration
                test_result.best_score = previous_best.best_score
            else:
                # Should not happen, but handle it
                test_result.best_correct = test_result.correct_answers
                test_result.best_wrong = test_result.wrong_answers
                test_result.best_skipped = test_result.skipped_answers
                test_result.best_duration = duration
                test_result.best_score = test_result.correct_answers
        else:
            # First attempt
            test_result.best_correct = test_result.correct_answers
            test_result.best_wrong = test_result.wrong_answers
            test_result.best_skipped = test_result.skipped_answers
            test_result.best_duration = duration
            test_result.best_score = test_result.correct_answers
        
        # Get leaderboard stats
        result = await session.execute(
            select(func.count(TestResult.id)).where(TestResult.test_id == test_result.test_id)
        )
        total_participants = result.scalar() or 0
        
        result = await session.execute(
            select(func.count(TestResult.id)).where(
                and_(
                    TestResult.test_id == test_result.test_id,
                    TestResult.correct_answers > test_result.correct_answers
                )
            )
        )
        better_count = result.scalar() or 0
        
        position = better_count + 1
        percentage = ((total_participants - better_count) / total_participants * 100) if total_participants > 0 else 100
        
        test_result.completed_at = datetime.now(timezone.utc)
        await session.commit()
    
    # Format duration
    minutes = duration // 60
    seconds = duration % 60
    duration_str = f"{minutes} daqiqa {seconds} soniya"
    
    best_minutes = test_result.best_duration // 60
    best_seconds = test_result.best_duration % 60
    best_duration_str = f"{best_minutes} daqiqa {best_seconds} soniya"
    
    # Check if this is first completion or has previous results
    has_previous_results = previous_best_correct > 0 or total_participants > 1
    
    # Build result message (truncate test name if too long)
    test_name_display = test.name[:60] + "..." if len(test.name) > 60 else test.name
    text = f"🎲 <b>\"{test_name_display}\" testi</b>\n\n"
    
    if has_previous_results:
        text += "Siz allaqachon ushbu testda qatnashdingiz.\n"
        text += "Eng yaxshi natijangiz:\n\n"
        text += f"✅ To'g'ri – {test_result.best_correct}\n"
        text += f"❌ Xato – {test_result.best_wrong}\n"
        text += f"⌛️ Tashlab ketilgan – {test_result.best_skipped}\n"
        text += f"⏱ {best_duration_str}\n\n"
        text += "Yetakchilardagi natijangiz:\n\n"
    else:
        text += "✅ <b>Test muvaffaqiyatli yakunlandi!</b>\n\n"
        text += "Natijangiz:\n\n"
    
    text += f"✅ To'g'ri – {test_result.correct_answers}\n"
    text += f"❌ Xato – {test_result.wrong_answers}\n"
    text += f"⌛️ Tashlab ketilgan – {test_result.skipped_answers}\n"
    text += f"⏱ {duration_str}\n\n"
    
    # Format position text (limit length) - only if has other participants
    if total_participants > 1:
        position_text = f"{position} tadan 🥇{position}-o'rin."
        if total_participants > 0:
            # Calculate percentage safely
            percentage = ((total_participants - better_count) / total_participants * 100) if total_participants > 0 else 100
            position_text += f" Siz ushbu testda ishtirok etgan {percentage:.0f}% odamlardan yuqoriroq ball to'pladingiz."
        text += position_text + "\n\n"
    
    text += "Bu testni qayta ishlash uchun quyidagi tugmani bosing."
    
    # Ensure text doesn't exceed limit
    if len(text) > SAFE_MESSAGE_LENGTH:
        # Truncate if necessary (shouldn't happen, but safety check)
        text = text[:SAFE_MESSAGE_LENGTH - 50] + "\n\n...[Natija kesilgan]"
    
    keyboard = [
        [InlineKeyboardButton("🔄 Testni qayta ishlash", callback_data=f"restart_test_{test_result.test_id}")],
        [InlineKeyboardButton("📋 Boshqa testlar", callback_data="test_list")],
        [InlineKeyboardButton("🏠 Bosh menyu", callback_data="back_to_menu")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    # Handle both callback query and message updates using edit_long_message
    await edit_long_message(query, context, text, parse_mode=ParseMode.HTML, reply_markup=reply_markup)
    
    # Clean up user data
    context.user_data.pop(f'test_start_{test_result_id}', None)
    context.user_data.pop(f'test_current_question_{test_result_id}', None)
    context.user_data.pop(f'last_question_msg_{test_result_id}', None)


async def handle_my_account(query, context):
    """Show user account info"""
    user = await get_or_create_user(
        query.from_user.id,
        query.from_user.username,
        query.from_user.first_name
    )
    
    async with db.async_session() as session:
        # Get user's tests count
        result = await session.execute(
            select(func.count(Test.id)).where(Test.creator_id == user.telegram_id)
        )
        tests_created = result.scalar() or 0
        
        # Get tests taken
        result = await session.execute(
            select(func.count(TestResult.id)).where(TestResult.user_id == user.telegram_id)
        )
        tests_taken = result.scalar() or 0
    
    text = (
        f"💰 <b>Hisobim</b>\n\n"
        f"👤 Foydalanuvchi: {user.first_name or 'Anonim'}\n"
        f"💵 Balans: {user.balance:,.0f} so'm\n\n"
        f"📊 Statistika:\n"
        f"📝 Yaratilgan testlar: {tests_created} ta\n"
        f"✅ Yechilgan testlar: {tests_taken} ta"
    )
    
    keyboard = [
        [InlineKeyboardButton("💳 Balansni to'ldirish", callback_data="topup_balance")],
        [InlineKeyboardButton("⬅️ Orqaga", callback_data="back_to_menu")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await query.edit_message_text(text, reply_markup=reply_markup, parse_mode=ParseMode.HTML)


async def handle_topup_balance(query, context):
    """Show top-up options"""
    text = (
        "💳 <b>Balansni to'ldirish</b>\n\n"
        "Quyidagi summadan birini tanlang:"
    )
    
    keyboard = []
    for amount in PAYMENT_AMOUNTS:
        keyboard.append([
            InlineKeyboardButton(
                f"{amount:,.0f} so'm",
                callback_data=f"topup_{amount}"
            )
        ])
    
    keyboard.append([InlineKeyboardButton("⬅️ Orqaga", callback_data="back_to_menu")])
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await query.edit_message_text(text, reply_markup=reply_markup, parse_mode=ParseMode.HTML)


async def handle_select_topup_amount(query, context, amount: int):
    """Handle selected top-up amount"""
    # Generate random last 2 digits
    random_suffix = random.randint(1, 99)
    expected_amount = amount + random_suffix
    
    async with db.async_session() as session:
        # Create payment record
        payment = Payment(
            user_id=query.from_user.id,
            amount=amount,
            expected_amount=expected_amount,
            is_verified=False
        )
        session.add(payment)
        await session.flush()
        payment_id = payment.id
        await session.commit()
    
    context.user_data['pending_payment_id'] = payment_id
    context.user_data['expected_amount'] = expected_amount
    context.user_data['waiting_payment'] = True
    
    text = (
        f"⚠️ <b>DIQQAT!</b>\n\n"
        f"To'lov qilish uchun quyidagi kartaga <b>{expected_amount:,.0f} so'm</b> yuborishingiz kerak.\n\n"
        f"💳 <b>Karta raqami:</b>\n"
        f"<code>{CARD_NUMBER}</code>\n\n"
        f"🔔 <b>Muhim:</b>\n"
        f"• To'lov qilgandan so'ng chekni (screenshot) yuborishingiz kerak\n"
        f"• Adminlar 5-10 daqiqada tekshirib tasdiqlaydi\n"
        f"• Faqat {expected_amount:,.0f} so'm to'laganingizni tekshiring\n\n"
        f"💰 To'lov summasi: <b>{amount:,.0f} so'm</b>\n"
        f"🔢 Tasdiqlash kodi: <b>{random_suffix:02d}</b> (oxirgi 2 raqam)\n"
        f"📊 Jami: <b>{expected_amount:,.0f} so'm</b>\n\n"
        f"To'lov chekini screenshot qilib yuboring:"
    )
    
    keyboard = [[InlineKeyboardButton("⬅️ Bekor qilish", callback_data="topup_balance")]]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await query.edit_message_text(text, reply_markup=reply_markup, parse_mode=ParseMode.HTML)
    
    # Set waiting state for payment screenshot
    context.user_data['waiting_payment'] = True


async def receive_payment_screenshot(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Receive payment screenshot"""
    if not context.user_data.get('waiting_payment'):
        # Not in payment flow, ignore
        return
    
    # Check if user wants to cancel
    if update.message.text and ("bekor" in update.message.text.lower() or "cancel" in update.message.text.lower() or "⬅️" in update.message.text):
        context.user_data.pop('waiting_payment', None)
        context.user_data.pop('pending_payment_id', None)
        context.user_data.pop('expected_amount', None)
        await update.message.reply_text(
            "❌ To'lov bekor qilindi.",
            reply_markup=ReplyKeyboardRemove()
        )
        await start(update, context)
        return
    
    payment_id = context.user_data.get('pending_payment_id')
    expected_amount = context.user_data.get('expected_amount')
    
    if not payment_id:
        await update.message.reply_text("❌ Xatolik! Qaytadan urinib ko'ring.")
        context.user_data.pop('waiting_payment', None)
        return
    
    # Get photo
    if not update.message.photo:
        await update.message.reply_text("❌ Iltimos, chek rasmini yuboring (screenshot).")
        return
    
    photo = update.message.photo[-1]  # Get largest photo
    
    # Download photo
    file = await context.bot.get_file(photo.file_id)
    screenshots_dir = Path("payment_screenshots")
    screenshots_dir.mkdir(exist_ok=True)
    screenshot_path = screenshots_dir / f"payment_{payment_id}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.jpg"
    
    await file.download_to_drive(screenshot_path)
    
    # Update payment record and get payment amount
    payment_amount = 0
    async with db.async_session() as session:
        result = await session.execute(select(Payment).where(Payment.id == payment_id))
        payment = result.scalar_one_or_none()
        
        if payment:
            payment_amount = payment.amount
            payment.screenshot_path = str(screenshot_path)
            await session.commit()
        else:
            await update.message.reply_text("❌ To'lov topilmadi! Qaytadan urinib ko'ring.")
            context.user_data.pop('waiting_payment', None)
            context.user_data.pop('pending_payment_id', None)
            context.user_data.pop('expected_amount', None)
            return
    
    # Send to admin group
    verification_code = int(expected_amount - payment_amount)
    admin_text = (
        f"💰 <b>Yangi to'lov so'rovi</b>\n\n"
        f"👤 Foydalanuvchi: @{update.effective_user.username or 'Noma\'lum'}\n"
        f"🆔 ID: {update.effective_user.id}\n"
        f"💵 Summa: {expected_amount:,.0f} so'm\n"
        f"💰 To'lov summasi: {payment_amount:,.0f} so'm\n"
        f"🔢 Tasdiqlash kodi: {verification_code:02d}\n"
        f"📅 Vaqt: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n"
        f"Tasdiqlash uchun chekni tekshiring."
    )
    
    try:
        # Send photo to admin group
        sent_photo = await context.bot.send_photo(
            chat_id=ADMIN_GROUP_ID,
            photo=photo.file_id,
            caption=admin_text,
            parse_mode=ParseMode.HTML
        )
        print(f"[OK] Chek admin guruhiga yuborildi. Message ID: {sent_photo.message_id}")
        
        # Send button for admin to verify
        verify_keyboard = InlineKeyboardMarkup([
            [
                InlineKeyboardButton("✅ Tasdiqlash", callback_data=f"verify_payment_{payment_id}"),
                InlineKeyboardButton("❌ Rad etish", callback_data=f"reject_payment_{payment_id}")
            ]
        ])
        
        sent_message = await context.bot.send_message(
            chat_id=ADMIN_GROUP_ID,
            text=(
                f"📋 <b>To'lov ma'lumotlari</b>\n\n"
                f"🆔 To'lov ID: <code>{payment_id}</code>\n"
                f"💵 Kutilayotgan summa: <b>{expected_amount:,.0f} so'm</b>\n"
                f"💰 To'lov summasi: <b>{payment_amount:,.0f} so'm</b>\n\n"
                f"Yuqoridagi chekni tekshirib, tasdiqlang yoki rad eting."
            ),
            reply_markup=verify_keyboard,
            parse_mode=ParseMode.HTML
        )
        print(f"[OK] Tasdiqlash tugmalari yuborildi. Message ID: {sent_message.message_id}")
        
        # Also notify admins directly
        for admin_id in ADMIN_IDS:
            try:
                await context.bot.send_message(
                    chat_id=admin_id,
                    text=(
                        f"💰 <b>Yangi to'lov so'rovi</b>\n\n"
                        f"👤 Foydalanuvchi: @{update.effective_user.username or 'Noma\'lum'}\n"
                        f"🆔 ID: {update.effective_user.id}\n"
                        f"💵 Summa: {expected_amount:,.0f} so'm\n"
                        f"🆔 To'lov ID: {payment_id}\n\n"
                        f"Guruhga yuborilgan chekni tekshiring: {ADMIN_GROUP_ID}"
                    ),
                    parse_mode=ParseMode.HTML
                )
            except Exception as admin_error:
                print(f"[WARNING] Admin {admin_id} ga xabar yuborishda xatolik: {admin_error}")
        
    except Exception as e:
        error_msg = f"Admin guruhiga yuborishda xatolik: {str(e)}"
        print(f"[ERROR] {error_msg}")
        
        # Check if it's a "Chat not found" error
        if "Chat not found" in str(e) or "chat not found" in str(e).lower():
            error_detail = (
                f"Bot guruhga qo'shilmagan yoki guruh ID noto'g'ri!\n\n"
                f"Guruh ID: {ADMIN_GROUP_ID}\n"
                f"To'lov ID: {payment_id}\n\n"
                f"Iltimos, botni guruhga qo'shing va admin huquqlarini bering."
            )
        else:
            error_detail = f"{error_msg}\n\nGuruh ID: {ADMIN_GROUP_ID}\nTo'lov ID: {payment_id}"
        
        # Try to send error to admins
        for admin_id in ADMIN_IDS:
            try:
                await context.bot.send_message(
                    chat_id=admin_id,
                    text=f"⚠️ {error_detail}"
                )
            except Exception as admin_err:
                print(f"[ERROR] Admin {admin_id} ga xatolik yuborishda muammo: {admin_err}")
    
    await update.message.reply_text(
        "✅ Chek qabul qilindi!\n\n"
        "⏳ Adminlar tekshirib 5-10 daqiqada javob berishadi.\n"
        "Tasdiqlanganidan so'ng balansingiz avtomatik to'ldiriladi.",
        reply_markup=ReplyKeyboardRemove()
    )
    
    # Clear payment state
    context.user_data.pop('waiting_payment', None)
    context.user_data.pop('pending_payment_id', None)
    context.user_data.pop('expected_amount', None)
    
    await start(update, context)


async def handle_verify_payment(query, context, payment_id: int, verify: bool):
    """Handle payment verification by admin"""
    if query.from_user.id not in ADMIN_IDS:
        await query.answer("❌ Sizda ruxsat yo'q! Faqat adminlar tasdiqlay oladi.", show_alert=True)
        return
    
    await query.answer()
    
    async with db.async_session() as session:
        result = await session.execute(select(Payment).where(Payment.id == payment_id))
        payment = result.scalar_one_or_none()
        
        if not payment:
            await query.edit_message_text("❌ To'lov topilmadi!")
            return
        
        if payment.is_verified:
            await query.edit_message_text("⚠️ Bu to'lov allaqachon tasdiqlangan!")
            return
        
        if verify:
            payment.is_verified = True
            payment.verified_by = query.from_user.id
            payment.verified_at = datetime.now(timezone.utc)
            
            # Add balance to user
            result = await session.execute(select(User).where(User.telegram_id == payment.user_id))
            user = result.scalar_one_or_none()
            
            if user:
                user.balance += payment.amount
                await session.commit()
                
                # Notify user
                try:
                    await context.bot.send_message(
                        chat_id=payment.user_id,
                        text=(
                            f"✅ <b>To'lov tasdiqlandi!</b>\n\n"
                            f"💵 Summa: {payment.amount:,.0f} so'm\n"
                            f"💰 Yangi balans: {user.balance:,.0f} so'm\n\n"
                            f"Endi test yaratishingiz mumkin!"
                        ),
                        parse_mode=ParseMode.HTML
                    )
                except Exception as e:
                    print(f"[ERROR] Foydalanuvchiga xabar yuborishda xatolik: {e}")
                
                await query.edit_message_text(
                    f"✅ To'lov tasdiqlandi!\n"
                    f"Foydalanuvchi balansi: {user.balance:,.0f} so'm"
                )
            else:
                await query.edit_message_text("❌ Foydalanuvchi topilmadi!")
        else:
            await session.delete(payment)
            await session.commit()
            
            # Notify user
            try:
                await context.bot.send_message(
                    chat_id=payment.user_id,
                    text=(
                        "❌ <b>To'lov rad etildi</b>\n\n"
                        "Iltimos, to'lov summasi va chekni qayta tekshiring.\n"
                        "Muammo bo'lsa, qo'llab-quvvatlash bilan bog'laning."
                    ),
                    parse_mode=ParseMode.HTML
                )
            except Exception as e:
                print(f"Error notifying user: {e}")
            
            await query.edit_message_text("❌ To'lov rad etildi!")


async def payment_verification_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle payment verification buttons"""
    query = update.callback_query
    data = query.data
    
    if data.startswith("verify_payment_"):
        payment_id = int(data.split("_")[2])
        await handle_verify_payment(query, context, payment_id, True)
    elif data.startswith("reject_payment_"):
        payment_id = int(data.split("_")[2])
        await handle_verify_payment(query, context, payment_id, False)


async def setup_application():
    """Setup application with handlers (async part)"""
    # Initialize database
    await db.init_db()
    
    # Create application
    application = Application.builder().token(BOT_TOKEN).build()
    
    # Add handlers
    application.add_handler(CommandHandler("start", start))
    
    # Message handler for payment screenshots (when waiting)
    async def check_payment_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
        if context.user_data.get('waiting_payment'):
            await receive_payment_screenshot(update, context)
    
    # Message handler for test creation
    async def check_test_creation_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
        if context.user_data.get('creating_test'):
            if 'test_name' not in context.user_data:
                return await receive_test_name(update, context)
            else:
                return await receive_test_file(update, context)
    
    # Conversation handler for test creation
    # Note: per_message=False because we have MessageHandler in states
    # CallbackQueryHandler in states works with per_message=False but won't track per message
    # This is fine for our use case since we track by conversation state
    test_creation_handler = ConversationHandler(
        entry_points=[CallbackQueryHandler(handle_create_test, pattern="^create_test$")],
        states={
            WAITING_FOR_TEST_NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, receive_test_name)],
            WAITING_FOR_TEST_FILE: [MessageHandler(filters.Document.ALL | filters.TEXT, receive_test_file)],
        },
        fallbacks=[CommandHandler("start", start)],
        per_chat=True,
        per_user=True,
        per_message=False  # False is correct when mixing MessageHandler and CallbackQueryHandler
    )
    
    # Add handlers - IMPORTANT: ConversationHandler must come before general CallbackQueryHandler
    application.add_handler(test_creation_handler)  # Must be first to catch create_test
    application.add_handler(CallbackQueryHandler(payment_verification_handler, pattern="^(verify|reject)_payment_"))
    application.add_handler(CallbackQueryHandler(button_handler))  # General handler for other buttons
    application.add_handler(MessageHandler(filters.PHOTO | filters.TEXT, check_payment_message), group=1)
    
    return application


def main():
    """Main function to run the bot (synchronous wrapper)"""
    print("[INFO] Bot ishga tushmoqda...")
    
    # Setup application (async)
    application = asyncio.run(setup_application())
    
    print("[INFO] Polling boshlandi...")
    
    # Use run_polling which handles webhook deletion and conflicts automatically
    # This is the recommended approach and handles conflicts more robustly
    application.run_polling(
        allowed_updates=Update.ALL_TYPES,
        drop_pending_updates=True,  # Drop pending updates to avoid conflicts
        stop_signals=None  # Don't stop on signals (systemd handles this)
    )


if __name__ == "__main__":
    main()
