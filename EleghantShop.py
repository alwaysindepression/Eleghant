import asyncio
import aiosqlite
import logging
import aiohttp
import html
import os
import time
from datetime import datetime, timedelta, timezone
from typing import Dict, Optional, Tuple, List, Any
from contextlib import asynccontextmanager
from asyncio import Semaphore
from functools import lru_cache, wraps

from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command, CommandStart
from aiogram.types import ReplyKeyboardMarkup, KeyboardButton, InlineKeyboardMarkup, BotCommand, FSInputFile
from aiogram.utils.keyboard import InlineKeyboardBuilder
from aiogram.utils.markdown import hbold, hcode, hlink
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.exceptions import TelegramBadRequest, TelegramRetryAfter

# --- ТОКЕНЫ ---
BOT_TOKEN = "8768689509:AAE4YMkLYeoZiuM7tGhRmvS2vM5rw-pYsOI"
CRYPTO_PAY_TOKEN = "598185:AApLNI3hDYU9Ykl6mVZ6sw4ZXnx4tZtEHgU"
XROCKET_PAY_TOKEN = "4651fe8e4fa224c3ca95b7592"
ADMIN_ID = 7096591314

# Константы
PAYMENT_CHECK_INTERVAL = 10
PAYMENT_CHECK_ATTEMPTS = 30
MAX_PAYMENT_WAIT_TIME = PAYMENT_CHECK_INTERVAL * PAYMENT_CHECK_ATTEMPTS
MAX_QUANTITY_PER_PURCHASE = 100
MAX_PROMO_ATTEMPTS = 5
PROMO_BLOCK_TIME = 3600
RATE_LIMIT = 2
CLEANUP_INTERVAL = 3600
MAX_CONCURRENT_PAYMENT_CHECKS = 10
DB_VERSION = 2
MAX_BULK_ADD = 1000

AGREEMENT_URL = "https://telegra.ph/Pravila-EleghantShopBot-03-26"
SUPPORT_URL = "https://t.me/EleghantSup3_Bot"

# --- РЕЖИМ ТЕХ. РАБОТ ---
MAINTENANCE_MODE = False

# --- КАСТОМНЫЕ ЭМОДЗИ (ПРЕМИУМ) ---
class CustomEmoji:
    CATALOG = "5431646131941556182"
    PROFILE = "6276264803753266907"
    DEPOSIT = "5316711376876485361"
    HELP = "5420323339723881652"
    PREORDER = "5893102202817352158"
    ACCEPT = "5206607081334906820"
    BACK = "5220070652756635426"
    CRYPTO_PAY = "5361914370068613491"
    XROCKET_PAY = "5379612946747921985"
    BALANCE_PAY = "5972185809300753162"
    CHECKMARK = "5895514131896733546"
    GY = "5343742152985839675"
    GY_EMOJI = "5440746682310469677"
    MTS = "5262690652616931769"
    MEGAFON = "5470134961673612788"
    BEELINE = "5469796926272580161"
    YOTA = "5469769180783849063"
    T2 = "5440552665752820072"
    GUN = "5226443873122808829"
    PROFILE_EMOJI = "5454156248813432363"
    SHIELD = "5893365724830765382"
    CHECK = "5902002809573740949"
    LOCK = "5224372410395947583"
    UP = "5208615906258731489"
    TROPHY = "5893376775781617954"
    USER = "5902335789798265487"
    PLUS = "5397916757333654639"
    PROMO = "5902453596456227896"
    LINK = "5271604874419647061"
    MONEY = "5409048419211682843"
    WARNING = "5274099962655816924"
    QUESTION = "5436113877181941026"
    DIAMOND = "5427168083074628963"
    PIN = "5397782960512444700"
    SUPPORT = "5444965061749644170"
    TIME = "5316575093269214796"
    HISTORY = "5395444784611480792"
    PREORDER_CLOCK = "5893102202817352158"
    PREORDER_CHECK = "5895713431264170680"
    PREORDER_SETTINGS = "5902432207519093015"
    PREORDER_STATS = "5895444149699612825"
    PREORDER_BOX = "5893102202817352158"
    PREORDER_CALENDAR = "5893102202817352158"
    PREORDER_WAIT = "5893102202817352158"
    PREORDER_COMPLETED = "5895514131896733546"
    PIN_EMOJI = "5895440460322706085"
    BUYKB = "5312057711091813718"
    WITHDRAW = "5409048419211682843"

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('bot.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher(storage=MemoryStorage())

# --- MIDDLEWARE ДЛЯ ОТСЛЕЖИВАНИЯ ПОЛЬЗОВАТЕЛЕЙ ---
class UserTrackingMiddleware:
    async def __call__(self, handler, event: types.Update, data: dict):
        user_info = None
        event_type = "unknown"

        if event.message and event.message.from_user:
            user_info = event.message.from_user
            event_type = "message"
        elif event.callback_query and event.callback_query.from_user:
            user_info = event.callback_query.from_user
            event_type = "callback_query"
        elif event.inline_query and event.inline_query.from_user:
            user_info = event.inline_query.from_user
            event_type = "inline_query"
        elif event.chosen_inline_result and event.chosen_inline_result.from_user:
            user_info = event.chosen_inline_result.from_user
            event_type = "chosen_inline_result"

        if user_info:
            user_display = self._format_user_info(user_info)
            action_info = self._get_action_info(event, event_type)

            logger.info(f"\n{'='*80}\n"
                       f"👤 ПОЛЬЗОВАТЕЛЬ ВЗАИМОДЕЙСТВУЕТ С БОТОМ\n"
                       f"{'='*80}\n"
                       f"{user_display}\n"
                       f"📱 Тип события: {event_type.upper()}\n"
                       f"🎯 Действие: {action_info}\n"
                       f"{'='*80}\n")

            await self._save_user_interaction(user_info, event_type, action_info)

        return await handler(event, data)

    def _format_user_info(self, user: types.User) -> str:
        info = []
        info.append(f"🆔 ID: {user.id}")
        if user.first_name:
            info.append(f"📛 Имя: {user.first_name}")
        if user.last_name:
            info.append(f"🏷 Фамилия: {user.last_name}")
        if user.username:
            info.append(f"🔗 Username: @{user.username}")
        if user.language_code:
            info.append(f"🌐 Язык: {user.language_code}")
        if user.is_premium:
            info.append(f"⭐ Премиум: Да")
        if user.username:
            info.append(f"🔗 Ссылка: https://t.me/{user.username}")
        else:
            info.append(f"🔗 Ссылка: tg://user?id={user.id}")
        return "\n".join(info)

    def _get_action_info(self, event: types.Update, event_type: str) -> str:
        if event_type == "message" and event.message:
            msg = event.message
            if msg.text:
                action = f"Текст: {msg.text[:100]}{'...' if len(msg.text) > 100 else ''}"
            elif msg.photo:
                action = "Отправил фото"
            elif msg.video:
                action = "Отправил видео"
            elif msg.document:
                action = f"Отправил документ: {msg.document.file_name if msg.document.file_name else 'без имени'}"
            elif msg.sticker:
                action = f"Отправил стикер: {msg.sticker.emoji if msg.sticker.emoji else 'без эмодзи'}"
            elif msg.voice:
                action = "Отправил голосовое сообщение"
            elif msg.contact:
                action = f"Отправил контакт: {msg.contact.first_name}"
            elif msg.location:
                action = "Отправил геолокацию"
            else:
                action = f"Отправил {msg.content_type}"
            if msg.text and msg.text.startswith('/'):
                action += " (команда)"
            return action
        elif event_type == "callback_query" and event.callback_query:
            cb = event.callback_query
            action = f"Нажал на кнопку: {cb.data[:100]}{'...' if len(cb.data) > 100 else ''}"
            if cb.message:
                action += f"\n   📍 В сообщении: {cb.message.text[:50] if cb.message.text else 'без текста'}"
            return action
        elif event_type == "inline_query" and event.inline_query:
            return f"Inline запрос: {event.inline_query.query[:100]}"
        return "Неизвестное действие"

    async def _save_user_interaction(self, user: types.User, event_type: str, action_info: str):
        try:
            log_dir = "user_interactions"
            os.makedirs(log_dir, exist_ok=True)
            all_logs_file = os.path.join(log_dir, "all_interactions.log")
            user_log_file = os.path.join(log_dir, f"user_{user.id}.log")
            timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            log_entry = (
                f"[{timestamp}] "
                f"User: {user.id} (@{user.username if user.username else 'no_username'}) "
                f"| {user.first_name or ''} {user.last_name or ''} "
                f"| Type: {event_type} "
                f"| Action: {action_info}\n"
            )
            with open(all_logs_file, "a", encoding="utf-8") as f:
                f.write(log_entry)
            with open(user_log_file, "a", encoding="utf-8") as f:
                f.write(log_entry)
        except Exception as e:
            logger.error(f"Ошибка при сохранении лога взаимодействия: {e}")

dp.update.middleware(UserTrackingMiddleware())

# --- MIDDLEWARE ТЕХ. РАБОТ ---
class MaintenanceMiddleware:
    async def __call__(self, handler, event: types.Update, data: dict):
        global MAINTENANCE_MODE
        if not MAINTENANCE_MODE:
            return await handler(event, data)

        user_id = None
        if event.message and event.message.from_user:
            user_id = event.message.from_user.id
        elif event.callback_query and event.callback_query.from_user:
            user_id = event.callback_query.from_user.id

        if user_id == ADMIN_ID:
            return await handler(event, data)

        maintenance_text = (
            '🛠 <b>Технические работы</b>\n\n'
            'В данный момент ведутся тех. работы.\n'
            'Попробуйте зайти позже — скоро всё заработает!'
        )
        kb = InlineKeyboardBuilder()
        kb.button(text="📢 Наш канал", url="https://t.me/EleghantNews")
        kb.button(text="🆘 Поддержка", url="https://t.me/EleghantSup3_Bot")
        kb.button(text="🔐 EleghantVPN", url="https://t.me/EleghantVPNRobot")
        kb.button(text="📄 Пользовательское соглашение", url="https://telegra.ph/Pravila-EleghantShopBot-03-26")
        kb.adjust(2)

        if event.callback_query:
            try:
                await event.callback_query.answer(
                    "🛠 Ведутся тех. работы. Попробуйте позже.", show_alert=True
                )
            except Exception:
                pass
            try:
                await event.callback_query.message.answer(
                    maintenance_text, parse_mode="HTML", reply_markup=kb.as_markup()
                )
            except Exception:
                pass
        elif event.message:
            try:
                await event.message.answer(
                    maintenance_text, parse_mode="HTML", reply_markup=kb.as_markup()
                )
            except Exception:
                pass
        return

dp.update.middleware(MaintenanceMiddleware())

pending_payments: Dict[int, Dict] = {}
pending_balance_payments: Dict[int, Dict] = {}
user_promo_attempts: Dict[int, Tuple[int, float]] = {}

payment_check_semaphore = Semaphore(MAX_CONCURRENT_PAYMENT_CHECKS)
db_connection = None

# --- СОСТОЯНИЯ ---
class ShopState(StatesGroup):
    waiting_for_quantity = State()
    waiting_for_payment_method = State()
    waiting_for_deposit_provider = State()
    waiting_for_deposit_amount = State()
    waiting_for_promo_code = State()
    waiting_for_preorder_category = State()
    waiting_for_preorder_quantity = State()
    waiting_for_preorder_provider = State()
    waiting_for_withdraw_amount = State()
    waiting_for_withdraw_confirm = State()

class AdminState(StatesGroup):
    broadcast_text = State()
    broadcast_with_image = State()
    broadcast_image = State()
    give_balance_user_id = State()
    give_balance_amount = State()
    add_stock_cat_id = State()
    add_stock_count = State()
    add_stock_data = State()
    add_stock_current = State()
    add_stock_txt_cat_id = State()
    add_stock_txt_file = State()
    create_promo_code = State()
    create_promo_type = State()
    create_promo_value = State()
    create_promo_limit = State()
    change_price_category = State()
    change_price_value = State()
    withdraw_reject_reason = State()

# --- КЛАВИАТУРА ГЛАВНОГО МЕНЮ ---
def main_keyboard() -> ReplyKeyboardMarkup:
    catalog_btn = KeyboardButton(text="Каталог", icon_custom_emoji_id=CustomEmoji.CATALOG)
    profile_btn = KeyboardButton(text="Профиль", icon_custom_emoji_id=CustomEmoji.PROFILE)
    deposit_btn = KeyboardButton(text="Пополнить баланс", icon_custom_emoji_id=CustomEmoji.DEPOSIT)
    help_btn = KeyboardButton(text="Помощь", icon_custom_emoji_id=CustomEmoji.HELP)
    preorder_btn = KeyboardButton(text="Предзаказ", icon_custom_emoji_id=CustomEmoji.PREORDER)
    kb = [[catalog_btn], [profile_btn, deposit_btn], [help_btn, preorder_btn]]
    return ReplyKeyboardMarkup(keyboard=kb, resize_keyboard=True)

# --- УНИВЕРСАЛЬНАЯ ФУНКЦИЯ ДЛЯ ОТПРАВКИ С КАРТИНКОЙ ---
async def send_with_image(message: types.Message, image_name: str, text: str, reply_markup=None):
    try:
        if os.path.exists(f'{image_name}.jpg'):
            photo = FSInputFile(f'{image_name}.jpg')
            await message.answer_photo(photo=photo, caption=text, parse_mode="HTML", reply_markup=reply_markup)
        elif os.path.exists(f'{image_name}.png'):
            photo = FSInputFile(f'{image_name}.png')
            await message.answer_photo(photo=photo, caption=text, parse_mode="HTML", reply_markup=reply_markup)
        else:
            await message.answer(text, parse_mode="HTML", reply_markup=reply_markup)
            logger.warning(f"Картинка {image_name} не найдена")
    except Exception as e:
        logger.error(f"Ошибка при отправке картинки {image_name}: {e}")
        await message.answer(text, parse_mode="HTML", reply_markup=reply_markup)

# --- БАЗА ДАННЫХ ---
async def get_db():
    global db_connection
    if db_connection is None:
        db_connection = await aiosqlite.connect('shop.db')
        await db_connection.execute("PRAGMA foreign_keys = ON")
    return db_connection

async def close_db():
    global db_connection
    if db_connection:
        await db_connection.close()
        db_connection = None

async def execute_query(sql: str, params: tuple = (), commit: bool = False):
    conn = await get_db()
    cursor = await conn.execute(sql, params)
    if commit:
        await conn.commit()
    return cursor

async def fetchone(sql: str, params: tuple = ()):
    cursor = await execute_query(sql, params)
    return await cursor.fetchone()

async def fetchall(sql: str, params: tuple = ()):
    cursor = await execute_query(sql, params)
    return await cursor.fetchall()

async def executemany(sql: str, params: List[tuple], commit: bool = True):
    conn = await get_db()
    await conn.executemany(sql, params)
    if commit:
        await conn.commit()

async def transaction():
    conn = await get_db()
    await conn.execute("BEGIN IMMEDIATE")
    return conn

# --- ИНИЦИАЛИЗАЦИЯ БД ---
async def init_db():
    conn = await get_db()
    await conn.execute('''CREATE TABLE IF NOT EXISTS users (
        id INTEGER PRIMARY KEY, accepted INTEGER DEFAULT 0, total INTEGER DEFAULT 0,
        username TEXT, referrer_id INTEGER DEFAULT NULL
    )''')
    await conn.execute('''CREATE TABLE IF NOT EXISTS categories (
        id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT, desc TEXT, price REAL, cat_group TEXT DEFAULT ''
    )''')
    await conn.execute('''CREATE TABLE IF NOT EXISTS inventory (
        id INTEGER PRIMARY KEY AUTOINCREMENT, cat_id INTEGER, data TEXT
    )''')
    await conn.execute('''CREATE TABLE IF NOT EXISTS preorders (
        id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER, cat_id INTEGER, quantity INTEGER,
        total REAL, status TEXT DEFAULT 'pending', created_at TEXT, paid_at TEXT DEFAULT NULL
    )''')
    await conn.execute('''CREATE TABLE IF NOT EXISTS history (
        id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER, item_data TEXT, date TEXT
    )''')
    await conn.execute('''CREATE TABLE IF NOT EXISTS balances (
        user_id INTEGER PRIMARY KEY, balance REAL DEFAULT 0.0
    )''')
    await conn.execute('''CREATE TABLE IF NOT EXISTS referrals (
        id INTEGER PRIMARY KEY AUTOINCREMENT, referrer_id INTEGER, referral_id INTEGER UNIQUE, date TEXT
    )''')
    await conn.execute('''CREATE TABLE IF NOT EXISTS referral_earnings (
        id INTEGER PRIMARY KEY AUTOINCREMENT, referrer_id INTEGER, amount REAL, from_user_id INTEGER, date TEXT
    )''')
    await conn.execute('''CREATE TABLE IF NOT EXISTS promo_codes (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        code TEXT UNIQUE,
        amount REAL,
        promo_type TEXT DEFAULT 'fixed',
        max_uses INTEGER,
        used INTEGER DEFAULT 0
    )''')
    try:
        await conn.execute("ALTER TABLE promo_codes ADD COLUMN promo_type TEXT DEFAULT 'fixed'")
    except:
        pass
    await conn.execute('''CREATE TABLE IF NOT EXISTS balance_history (
        id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER, amount REAL, operation TEXT, date TEXT, admin_id INTEGER DEFAULT NULL
    )''')
    # --- ТАБЛИЦА ЗАЯВОК НА ВЫВОД ---
    await conn.execute('''CREATE TABLE IF NOT EXISTS withdraw_requests (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER,
        username TEXT,
        amount REAL,
        status TEXT DEFAULT 'pending',
        created_at TEXT,
        processed_at TEXT DEFAULT NULL,
        admin_note TEXT DEFAULT NULL
    )''')
    await conn.commit()
    try:
        await conn.execute("CREATE INDEX IF NOT EXISTS idx_inventory_cat_id ON inventory(cat_id)")
        await conn.execute("CREATE INDEX IF NOT EXISTS idx_history_user_id ON history(user_id)")
        await conn.execute("CREATE INDEX IF NOT EXISTS idx_referrals_referrer_id ON referrals(referrer_id)")
        await conn.execute("CREATE INDEX IF NOT EXISTS idx_preorders_user_id ON preorders(user_id)")
        await conn.execute("CREATE INDEX IF NOT EXISTS idx_withdraw_user_id ON withdraw_requests(user_id)")
        await conn.commit()
    except:
        pass
    logger.info("Database initialized")

async def update_catalog_descriptions():
    descriptions = {
        "MTS 1960+": '<tg-emoji emoji-id="5312126452043363774">📞</tg-emoji> <b>MTS 1960+</b>\n\n<tg-emoji emoji-id="5895440460322706085">📌</tg-emoji> <b>Описание товара:</b>\nMTS - без TOTP, ВП, отчеканный на ФССП',
        "MEGAFON 1960+": '<tg-emoji emoji-id="5229218997521631084">📞</tg-emoji> <b>MEGAFON 1960+</b>\n\n<tg-emoji emoji-id="5895440460322706085">📌</tg-emoji> <b>Описание товара:</b>\nMEGAFON - без TOTP, ВП, отчеканный на ФССП',
        "BEELINE 1960+": '<tg-emoji emoji-id="5280919528908267119">📞</tg-emoji> <b>BEELINE 1960+</b>\n\n<tg-emoji emoji-id="5895440460322706085">📌</tg-emoji> <b>Описание товара:</b>\nBEELINE - без TOTP, ВП, отчеканный на ФССП',
        "YOTA 1960+": '<tg-emoji emoji-id="5280716016177915458">📞</tg-emoji> <b>YOTA 1960+</b>\n\n<tg-emoji emoji-id="5895440460322706085">📌</tg-emoji> <b>Описание товара:</b>\nYOTA - без TOTP, ВП, отчеканный на ФССП',
        "T2 SMENA MIKS 1960+": '<tg-emoji emoji-id="5244453379664534900">📞</tg-emoji> <b>T2 SMENA MIKS 1960+</b>\n\n<tg-emoji emoji-id="5895440460322706085">📌</tg-emoji> <b>Описание товара:</b>\nT2 - без TOTP, ВП, отчеканный на ФССП',
        "Чистые ГУ 1960-1969": '<tg-emoji emoji-id="5343742152985839675">🏦</tg-emoji> <b>Чистые ГУ 1960-1969</b>\n\n<tg-emoji emoji-id="5895440460322706085">📌</tg-emoji> <b>Описание товара:</b>\nНовый, чистый аккаунт ГУ. Официально подтверждён с помощью панели МФЦ.\n\n<b>Что это значит:</b>\n• Вы — первый владелец. История нулевая.\n• Привяжите свой номер автоматически с помощью нашего бота — аккаунт ГУ будет на 100% под вашим контролем.\n• Альтернативный способ если нет номеров под привяз, приобретите ключом TOTP, также бот выдаст вам код входа в ГК (последующие коды можно будет запрашивать через историю покупок)\n• Без блокировок. Сразу готов к использованию.\n\n<b>Всё просто:</b> купили → получили → пользуетесь. Это занимает 2 минуты.',
        "ГУ под ГК 1960-1969": '<tg-emoji emoji-id="5456232070932090258">🔑</tg-emoji> <b>ГУ под ГК 1960-1969</b>\n\n<tg-emoji emoji-id="5895440460322706085">📌</tg-emoji> <b>Описание товара:</b>\nАккаунт ГУ предназначенный только для подписей. Оформить банки/верифы на него не выйдет.\n\n<b>Что это значит:</b>\n• Вы — первый владелец. История нулевая.\n• Привяжите свой номер автоматически с помощью нашего бота — аккаунт ГУ будет на 100% под вашим контролем.\n• Альтернативный способ если нет номеров под привяз, приобретите ключом TOTP, также бот выдаст вам код входа в ГК (последующие коды можно будет запрашивать через историю покупок)\n• Без блокировок. Сразу готов к использованию.\n\n<b>Всё просто:</b> купили → получили → пользуетесь. Это занимает 2 минуты.',
        "Чистые ГУ 1980-2006": '<tg-emoji emoji-id="5343742152985839675">🏦</tg-emoji> <b>Чистые ГУ 1980-2006</b>\n\n<tg-emoji emoji-id="5895440460322706085">📌</tg-emoji> <b>Описание товара:</b>\nНовый, чистый аккаунт ГУ. Официально подтверждён с помощью панели МФЦ.\n\n<b>Что это значит:</b>\n• Вы — первый владелец. История нулевая.\n• Привяжите свой номер автоматически с помощью нашего бота — аккаунт ГУ будет на 100% под вашим контролем.\n• Альтернативный способ если нет номеров под привяз, приобретите ключом TOTP, также бот выдаст вам код входа в ГК (последующие коды можно будет запрашивать через историю покупок)\n• Без блокировок. Сразу готов к использованию.\n\n<b>Всё просто:</b> купили → получили → пользуетесь. Это занимает 2 минуты.',
        "ГУ под ГК 1980-2006": '<tg-emoji emoji-id="5456232070932090258">🔑</tg-emoji> <b>ГУ под ГК 1980-2006</b>\n\n<tg-emoji emoji-id="5895440460322706085">📌</tg-emoji> <b>Описание товара:</b>\nАккаунт ГУ предназначенный только для подписей. Оформить банки/верифы на него не выйдет.\n\n<b>Что это значит:</b>\n• Вы — первый владелец. История нулевая.\n• Привяжите свой номер автоматически с помощью нашего бота — аккаунт ГУ будет на 100% под вашим контролем.\n• Альтернативный способ если нет номеров под привяз, приобретите ключом TOTP, также бот выдаст вам код входа в ГК (последующие коды можно будет запрашивать через историю покупок)\n• Без блокировок. Сразу готов к использованию.\n\n<b>Всё просто:</b> купили → получили → пользуетесь. Это занимает 2 минуты.',
    }
    prices = {
        "MTS 1960+": 4.5, "MEGAFON 1960+": 4.0, "BEELINE 1960+": 3.5,
        "YOTA 1960+": 3.5, "T2 SMENA MIKS 1960+": 4.0,
        "Чистые ГУ 1960-1969": 25.0, "ГУ под ГК 1960-1969": 18.0,
        "Чистые ГУ 1980-2006": 25.0, "ГУ под ГК 1980-2006": 18.0,
    }
    cat_groups = {
        "MTS 1960+": "l0gu_1970", "MEGAFON 1960+": "l0gu_1970",
        "BEELINE 1960+": "l0gu_1970", "YOTA 1960+": "l0gu_1970",
        "T2 SMENA MIKS 1960+": "l0gu_1970",
        "Чистые ГУ 1960-1969": "gy_1970", "ГУ под ГК 1960-1969": "gy_1970",
        "Чистые ГУ 1980-2006": "gy_1970", "ГУ под ГК 1980-2006": "gy_1970",
    }
    for name, desc in descriptions.items():
        existing = await fetchone("SELECT id FROM categories WHERE name = ?", (name,))
        price = prices.get(name, 0)
        cat_group = cat_groups.get(name, "")
        if existing:
            await execute_query(
                "UPDATE categories SET desc = ?, price = ?, cat_group = ? WHERE name = ?",
                (desc, price, cat_group, name), commit=True
            )
        else:
            await execute_query(
                "INSERT INTO categories (name, desc, price, cat_group) VALUES (?, ?, ?, ?)",
                (name, desc, price, cat_group), commit=True
            )
    logger.info("Catalog descriptions updated")

async def setup_catalog():
    await update_catalog_descriptions()

# --- ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ ---
async def get_balance(user_id: int) -> float:
    bal = await fetchone("SELECT balance FROM balances WHERE user_id = ?", (user_id,))
    return bal[0] if bal else 0.0

async def update_balance(user_id: int, amount: float, operation: str = "unknown", admin_id: int = None):
    current_balance = await get_balance(user_id)
    new_balance = current_balance + amount
    if new_balance < 0 and operation not in ["admin_give"]:
        logger.warning(f"Attempt to set negative balance for user {user_id}: {new_balance}")
        return False
    await execute_query("INSERT INTO balances (user_id, balance) VALUES (?, ?) "
                       "ON CONFLICT(user_id) DO UPDATE SET balance = balance + ?",
                       (user_id, amount, amount), commit=True)
    await execute_query("INSERT INTO balance_history (user_id, amount, operation, date, admin_id) VALUES (?, ?, ?, ?, ?)",
                       (user_id, amount, operation, datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S"), admin_id), commit=True)
    return True

async def add_referral_earning(referrer_id: int, amount: float, from_user_id: int):
    await execute_query("INSERT INTO referral_earnings (referrer_id, amount, from_user_id, date) VALUES (?, ?, ?, ?)",
                       (referrer_id, amount, from_user_id, datetime.now(timezone.utc).strftime("%d.%m %H:%M")), commit=True)
    await update_balance(referrer_id, amount, "referral")

async def get_referral_info(user_id: int) -> Tuple[int, float]:
    count = await fetchone("SELECT COUNT(*) FROM referrals WHERE referrer_id = ?", (user_id,))
    earnings = await fetchone("SELECT SUM(amount) FROM referral_earnings WHERE referrer_id = ?", (user_id,))
    return count[0] if count else 0, earnings[0] if earnings and earnings[0] else 0.0

async def save_user(username: str, user_id: int, referrer_id: int = None):
    await execute_query("UPDATE users SET username = ? WHERE id = ?", (username, user_id), commit=True)
    existing = await fetchone("SELECT id FROM users WHERE id = ?", (user_id,))
    if not existing:
        await execute_query("INSERT INTO users (id, username, referrer_id) VALUES (?, ?, ?)",
                           (user_id, username, referrer_id), commit=True)
        await execute_query("INSERT INTO balances (user_id, balance) VALUES (?, ?)", (user_id, 0.0), commit=True)
        if referrer_id:
            await execute_query("INSERT INTO referrals (referrer_id, referral_id, date) VALUES (?, ?, ?)",
                               (referrer_id, user_id, datetime.now(timezone.utc).strftime("%d.%m %H:%M")), commit=True)

# --- ФУНКЦИЯ ПОКУПКИ С ТРАНЗАКЦИЕЙ ---
async def buy_items_with_transaction(cat_id: int, quantity: int, user_id: int, total: float) -> Optional[List[tuple]]:
    stock = await fetchone("SELECT COUNT(*) FROM inventory WHERE cat_id = ?", (cat_id,))
    stock_count = stock[0] if stock else 0
    if stock_count < quantity:
        return None
    if total > 0:
        balance = await get_balance(user_id)
        if balance < total:
            return None
    conn = await transaction()
    try:
        cursor = await conn.execute("SELECT id, data FROM inventory WHERE cat_id = ? LIMIT ?", (cat_id, quantity))
        items = await cursor.fetchall()
        if len(items) < quantity:
            await conn.rollback()
            return None
        ids = [item[0] for item in items]
        placeholders = ','.join('?' * len(ids))
        await conn.execute(f"DELETE FROM inventory WHERE id IN ({placeholders})", ids)
        now = datetime.now(timezone.utc).strftime("%d.%m %H:%M")
        history_data = [(user_id, item[1], now) for item in items]
        await conn.executemany("INSERT INTO history (user_id, item_data, date) VALUES (?, ?, ?)", history_data)
        await conn.execute("UPDATE users SET total = total + ? WHERE id = ?", (quantity, user_id))
        if total > 0:
            await conn.execute("UPDATE balances SET balance = balance - ? WHERE user_id = ? AND balance >= ?",
                             (total, user_id, total))
        await conn.commit()
        return items
    except Exception as e:
        await conn.rollback()
        logger.error(f"Transaction error: {e}")
        raise

# --- CRYPTO PAY API ---
async def crypto_api(method: str, data: dict = None) -> dict:
    if data is None:
        data = {}
    headers = {"Crypto-Pay-API-Token": CRYPTO_PAY_TOKEN}
    url = f"https://pay.crypt.bot/api/{method}"
    timeout = aiohttp.ClientTimeout(total=30)
    for attempt in range(3):
        try:
            async with aiohttp.ClientSession(timeout=timeout) as session:
                async with session.post(url, json=data, headers=headers) as resp:
                    result = await resp.json()
                    if result.get('ok'):
                        return result
                    else:
                        if attempt == 2:
                            return {"ok": False, "description": result.get('description', 'Unknown error')}
        except Exception as e:
            if attempt == 2:
                return {"ok": False, "description": str(e)}
        await asyncio.sleep(2 ** attempt)
    return {"ok": False, "description": "Max retries exceeded"}

# --- XROCKET PAY API ---
XROCKET_API_URL = "https://pay.xrocket.tg"

async def xrocket_request(method: str, path: str, json_data: dict = None, params: dict = None) -> dict:
    headers = {"Rocket-Pay-Key": XROCKET_PAY_TOKEN}
    url = f"{XROCKET_API_URL}/{path}"
    timeout = aiohttp.ClientTimeout(total=30)
    for attempt in range(3):
        try:
            async with aiohttp.ClientSession(timeout=timeout) as session:
                async with session.request(method, url, json=json_data, params=params, headers=headers) as resp:
                    try:
                        result = await resp.json()
                    except Exception:
                        raw_text = await resp.text()
                        logger.error(f"xRocket API: не удалось распарсить JSON, status={resp.status}, body={raw_text[:500]}")
                        if attempt == 2:
                            return {"ok": False, "description": f"Invalid JSON response (status {resp.status})"}
                        await asyncio.sleep(2 ** attempt)
                        continue
                    if resp.status >= 400 or result.get('errors') or result.get('error'):
                        err_msg = result.get('error') or (result.get('errors') or [{}])[0].get('error', 'Unknown error') if isinstance(result, dict) else 'Unknown error'
                        logger.warning(f"xRocket API error on {path}: {err_msg} | raw={result}")
                        if attempt == 2:
                            return {"ok": False, "description": err_msg, "raw": result}
                    else:
                        logger.info(f"xRocket API raw response for {path}: {result}")
                        return {"ok": True, "raw": result}
        except Exception as e:
            if attempt == 2:
                return {"ok": False, "description": str(e)}
        await asyncio.sleep(2 ** attempt)
    return {"ok": False, "description": "Max retries exceeded"}

def _xrocket_extract_invoice(raw: dict) -> dict:
    obj = raw.get('data', raw) if isinstance(raw, dict) else raw
    if not isinstance(obj, dict):
        return {}
    invoice_id = obj.get('id') or obj.get('invoiceId') or obj.get('invoice_id')
    pay_link = (
        obj.get('link') or obj.get('payLink') or obj.get('pay_url')
        or obj.get('url') or obj.get('miniAppInvoiceUrl') or obj.get('webAppInvoiceUrl')
    )
    status = obj.get('status') or obj.get('invoiceStatus')
    paid_amount = obj.get('paidAmount') or obj.get('paid_amount') or 0
    return {
        'id': invoice_id,
        'link': pay_link,
        'status': status,
        'paid_amount': paid_amount,
        'raw': obj,
    }

async def xrocket_create_invoice(amount: float, description: str, expired_in: int = 1800) -> dict:
    res = await xrocket_request("POST", "tg-invoices", json_data={
        "amount": amount,
        "numPayments": 1,
        "currency": "USDT",
        "description": description,
        "expiredIn": expired_in,
    })
    if not res.get('ok'):
        return {"ok": False, "description": res.get('description', 'Unknown error')}
    parsed = _xrocket_extract_invoice(res['raw'])
    if not parsed.get('id') or not parsed.get('link'):
        logger.error(f"xRocket: не удалось извлечь id/link из ответа createInvoice: {res['raw']}")
        return {"ok": False, "description": "Не удалось получить ссылку на оплату от xRocket. Проверьте логи (raw response)."}
    return {"ok": True, **parsed}

async def xrocket_get_invoice(invoice_id: str) -> dict:
    res = await xrocket_request("GET", f"tg-invoices/{invoice_id}")
    if not res.get('ok'):
        return {"ok": False, "description": res.get('description', 'Unknown error')}
    parsed = _xrocket_extract_invoice(res['raw'])
    return {"ok": True, **parsed}

def _xrocket_is_paid(status: Optional[str], paid_amount) -> bool:
    if status and str(status).lower() == 'paid':
        return True
    try:
        return float(paid_amount or 0) > 0
    except (TypeError, ValueError):
        return False

def _xrocket_is_expired(status: Optional[str]) -> bool:
    return bool(status) and str(status).lower() in ('expired', 'cancelled', 'canceled')

# --- ПРОВЕРКА ОПЛАТЫ ---
async def check_deposit_payment(invoice_id, user_id: int, amount: float, msg_to_edit: types.Message, provider: str = "crypto"):
    async with payment_check_semaphore:
        for attempt in range(PAYMENT_CHECK_ATTEMPTS):
            await asyncio.sleep(PAYMENT_CHECK_INTERVAL)
            if invoice_id not in pending_balance_payments:
                return
            if provider == "xrocket":
                inv = await xrocket_get_invoice(str(invoice_id))
                if not inv.get('ok'):
                    continue
                is_paid = _xrocket_is_paid(inv.get('status'), inv.get('paid_amount'))
                is_expired = _xrocket_is_expired(inv.get('status'))
            else:
                res = await crypto_api("getInvoices", {"invoice_ids": str(invoice_id)})
                if not (res.get('ok') and res['result'].get('items')):
                    continue
                cb_inv = res['result']['items'][0]
                is_paid = cb_inv['status'] == 'paid'
                is_expired = cb_inv['status'] == 'expired'

            if is_paid:
                await update_balance(user_id, amount, "deposit")
                del pending_balance_payments[invoice_id]
                await bot.send_message(user_id, f'<tg-emoji emoji-id="{CustomEmoji.PREORDER_CHECK}">✅</tg-emoji> Баланс успешно пополнен на {amount} USDT!', parse_mode="HTML")
                try:
                    await msg_to_edit.delete()
                except:
                    pass
                return
            elif is_expired:
                await msg_to_edit.edit_text(f'<tg-emoji emoji-id="{CustomEmoji.WARNING}">❌</tg-emoji> Счет просрочен. Попробуйте снова.', parse_mode="HTML")
                del pending_balance_payments[invoice_id]
                return
        if invoice_id in pending_balance_payments:
            await msg_to_edit.edit_text(f'<tg-emoji emoji-id="{CustomEmoji.WARNING}">❌</tg-emoji> Время ожидания истекло. Если вы оплатили, обратитесь в поддержку.', parse_mode="HTML")
            del pending_balance_payments[invoice_id]

async def auto_check_payment(invoice_id, user_id: int, cat_id: int, quantity: int,
                            msg_to_edit: types.Message, total_cost: float, provider: str = "crypto"):
    async with payment_check_semaphore:
        for attempt in range(PAYMENT_CHECK_ATTEMPTS):
            await asyncio.sleep(PAYMENT_CHECK_INTERVAL)
            if invoice_id not in pending_payments:
                return
            if provider == "xrocket":
                inv = await xrocket_get_invoice(str(invoice_id))
                if not inv.get('ok'):
                    continue
                is_paid = _xrocket_is_paid(inv.get('status'), inv.get('paid_amount'))
                is_expired = _xrocket_is_expired(inv.get('status'))
            else:
                res = await crypto_api("getInvoices", {"invoice_ids": str(invoice_id)})
                if not (res.get('ok') and res['result'].get('items')):
                    continue
                cb_inv = res['result']['items'][0]
                is_paid = cb_inv['status'] == 'paid'
                is_expired = cb_inv['status'] == 'expired'

            if is_paid:
                items = await buy_items_with_transaction(cat_id, quantity, user_id, total_cost)
                if not items:
                    await bot.send_message(user_id, f'<tg-emoji emoji-id="{CustomEmoji.WARNING}">❌</tg-emoji> Товар закончился во время оплаты. Обратитесь в поддержку.', parse_mode="HTML")
                    del pending_payments[invoice_id]
                    return
                res_text = f'<tg-emoji emoji-id="{CustomEmoji.PREORDER_CHECK}">✅</tg-emoji> Оплата подтверждена!\n\n<tg-emoji emoji-id="{CustomEmoji.PREORDER_BOX}">🎁</tg-emoji> Ваш товар:\n'
                for _, i_data in items:
                    res_text += f"• `{i_data}`\n"
                await bot.send_message(user_id, res_text, parse_mode="Markdown")
                try:
                    await msg_to_edit.delete()
                except:
                    pass
                referrer = await fetchone("SELECT referrer_id FROM users WHERE id = ?", (user_id,))
                if referrer and referrer[0]:
                    ref_bonus = round(total_cost * 0.1, 2)
                    await add_referral_earning(referrer[0], ref_bonus, user_id)
                    await bot.send_message(referrer[0], f'<tg-emoji emoji-id="{CustomEmoji.MONEY}">💰</tg-emoji> Вы получили {ref_bonus} USDT (10%) от покупки!', parse_mode="HTML")
                del pending_payments[invoice_id]
                return
            elif is_expired:
                await msg_to_edit.edit_text(f'<tg-emoji emoji-id="{CustomEmoji.WARNING}">❌</tg-emoji> Счет просрочен. Создайте новый заказ.', parse_mode="HTML")
                del pending_payments[invoice_id]
                return
        if invoice_id in pending_payments:
            await msg_to_edit.edit_text(f'<tg-emoji emoji-id="{CustomEmoji.WARNING}">❌</tg-emoji> Время автоматической проверки истекло. Обратитесь в поддержку.', parse_mode="HTML")
            del pending_payments[invoice_id]

# --- ФОН ЗАДАЧИ ---
async def cleanup_old_payments():
    while True:
        await asyncio.sleep(CLEANUP_INTERVAL)
        now = datetime.now()
        expired = [inv_id for inv_id, data in pending_payments.items()
                   if 'created_at' in data and now - data['created_at'] > timedelta(hours=1)]
        for inv_id in expired:
            del pending_payments[inv_id]
        expired = [inv_id for inv_id, data in pending_balance_payments.items()
                   if 'created_at' in data and now - data['created_at'] > timedelta(hours=1)]
        for inv_id in expired:
            del pending_balance_payments[inv_id]
        current_time = time.time()
        expired_users = [uid for uid, (attempts, last_attempt) in user_promo_attempts.items()
                         if current_time - last_attempt > PROMO_BLOCK_TIME]
        for uid in expired_users:
            del user_promo_attempts[uid]
        logger.info("Cleanup completed")

# --- ФУНКЦИЯ ДЛЯ ПОКАЗА КАТЕГОРИЙ ГРУППЫ ---
async def show_categories_group(call: types.CallbackQuery, group_key: str):
    if group_key == "l0gu":
        cat_group = "l0gu_1970"
        emoji_ids = [CustomEmoji.MTS, CustomEmoji.MEGAFON, CustomEmoji.BEELINE, CustomEmoji.YOTA, CustomEmoji.T2]
    elif group_key == "gy":
        cat_group = "gy_1970"
        emoji_ids = [CustomEmoji.GY, CustomEmoji.GY_EMOJI, CustomEmoji.GY, CustomEmoji.GY_EMOJI]
    else:
        await call.answer("Неизвестная группа")
        return
    cats = await fetchall("SELECT id, name FROM categories WHERE cat_group = ?", (cat_group,))
    if not cats:
        await call.message.answer(f'<tg-emoji emoji-id="{CustomEmoji.WARNING}">❗️</tg-emoji> В этом разделе пока нет товаров.', parse_mode="HTML")
        await call.answer()
        return
    kb = InlineKeyboardBuilder()
    for idx, (cid, name) in enumerate(cats):
        if idx < len(emoji_ids):
            kb.button(text=name, callback_data=f"view_{cid}", icon_custom_emoji_id=emoji_ids[idx])
        else:
            kb.button(text=name, callback_data=f"view_{cid}")
    kb.button(text="Назад к разделам", callback_data="back_to_main_catalog", icon_custom_emoji_id=CustomEmoji.BACK)
    kb.adjust(1)
    text = f'<tg-emoji emoji-id="{CustomEmoji.GUN}">🔫</tg-emoji> Выберите категорию:'
    await call.message.delete()
    await send_with_image(call.message, 'EleghantCatalog', text, kb.as_markup())
    await call.answer()

# --- ОБРАБОТЧИКИ СООБЩЕНИЙ ---
@dp.message(F.text == "Каталог")
async def text_catalog(message: types.Message):
    kb = InlineKeyboardBuilder()
    kb.button(text="GY 1970+", callback_data="group_gy", icon_custom_emoji_id=CustomEmoji.GY)
    kb.button(text="Л0гu 1960+, все операторы", callback_data="group_l0gu", icon_custom_emoji_id=CustomEmoji.MEGAFON)
    kb.adjust(1)
    text = f'<tg-emoji emoji-id="{CustomEmoji.GUN}">☝️</tg-emoji> <b>Каталог товаров</b>\n\nВыберите интересующий вас раздел:'
    await send_with_image(message, 'EleghantCatalog', text, kb.as_markup())

@dp.message(F.text == "Профиль")
async def text_profile(message: types.Message):
    await show_profile_with_image(message.from_user.id, message)

@dp.message(F.text == "Пополнить баланс")
async def text_deposit(message: types.Message, state: FSMContext):
    await state.set_state(ShopState.waiting_for_deposit_provider)
    kb = InlineKeyboardBuilder()
    kb.button(text="Оплатить @CryptoBot", callback_data="deposit_provider_crypto", icon_custom_emoji_id=CustomEmoji.CRYPTO_PAY)
    kb.button(text="Оплатить @xRocket", callback_data="deposit_provider_xrocket", icon_custom_emoji_id=CustomEmoji.XROCKET_PAY)
    kb.adjust(1)
    text = f'<tg-emoji emoji-id="{CustomEmoji.DEPOSIT}">💰</tg-emoji> <b>Пополнение баланса</b>\n\nВыберите способ оплаты:'
    await send_with_image(message, 'EleghantBalance', text, kb.as_markup())

@dp.message(F.text == "Помощь")
async def text_help(message: types.Message):
    kb = InlineKeyboardBuilder()
    kb.button(text="Написать администратору", url=SUPPORT_URL, icon_custom_emoji_id=CustomEmoji.SUPPORT)
    text = (f'<tg-emoji emoji-id="{CustomEmoji.TIME}">⏰</tg-emoji> <b>Помощь и поддержка</b>\n\n'
            f'Если у вас возникли вопросы или проблемы, вы можете связаться с администрацией.\n\n'
            f'Нажмите кнопку ниже, чтобы написать в поддержку.')
    await send_with_image(message, 'EleghantSupport', text, kb.as_markup())

@dp.message(F.text == "Предзаказ")
async def text_preorder(message: types.Message, state: FSMContext):
    text = f'<tg-emoji emoji-id="{CustomEmoji.PREORDER}">🕞</tg-emoji> <b>Предзаказ товаров</b>\n\nВыберите категорию для предзаказа:'
    await send_with_image(message, 'EleghantPreorder', text)
    kb = InlineKeyboardBuilder()
    categories = await fetchall("SELECT id, name FROM categories")
    for cat_id, name in categories:
        kb.button(text=name, callback_data=f"preorder_cat_{cat_id}")
    kb.button(text="❌ Отмена", callback_data="cancel_preorder", icon_custom_emoji_id=CustomEmoji.WARNING)
    kb.adjust(1)
    await message.answer("Выберите категорию:", reply_markup=kb.as_markup())

# --- КАТАЛОГ ---
@dp.callback_query(F.data.startswith("group_"))
async def show_group_categories(call: types.CallbackQuery):
    group_key = call.data.split("_")[1]
    await show_categories_group(call, group_key)

@dp.callback_query(F.data == "back_to_main_catalog")
async def back_to_main_catalog(call: types.CallbackQuery):
    kb = InlineKeyboardBuilder()
    kb.button(text="GY 1970+", callback_data="group_gy", icon_custom_emoji_id=CustomEmoji.GY)
    kb.button(text="Л0гu 1960+, все операторы", callback_data="group_l0gu", icon_custom_emoji_id=CustomEmoji.MEGAFON)
    kb.adjust(1)
    text = f'<tg-emoji emoji-id="{CustomEmoji.GUN}">☝️</tg-emoji> <b>Каталог товаров</b>\n\nВыберите интересующий вас раздел:'
    await call.message.delete()
    await send_with_image(call.message, 'EleghantCatalog', text, kb.as_markup())
    await call.answer()

@dp.callback_query(F.data == "back_to_l0gu")
async def back_to_l0gu(call: types.CallbackQuery):
    await show_categories_group(call, "l0gu")

@dp.callback_query(F.data == "back_to_gy")
async def back_to_gy(call: types.CallbackQuery):
    await show_categories_group(call, "gy")

@dp.callback_query(F.data.startswith("view_"))
async def view_cat_cb(call: types.CallbackQuery):
    try:
        cid = int(call.data.split("_")[1])
    except:
        await call.answer("❌ Ошибка")
        return
    cat = await fetchone("SELECT name, desc, price, cat_group FROM categories WHERE id = ?", (cid,))
    if not cat:
        await call.answer("❌ Категория не найдена")
        return
    cat_name, cat_desc, cat_price, cat_group = cat
    stock = await fetchone("SELECT COUNT(*) FROM inventory WHERE cat_id = ?", (cid,))
    stock_count = stock[0] if stock else 0
    text = f"{cat_desc}\n\n<tg-emoji emoji-id=\"{CustomEmoji.MONEY}\">💵</tg-emoji> Цена: <b>{cat_price} USDT/шт</b>\n<tg-emoji emoji-id=\"{CustomEmoji.WARNING}\">❗️</tg-emoji> Наличие: {stock_count} шт."
    kb = InlineKeyboardBuilder()
    if stock_count > 0:
        kb.button(text="🛒 Купить", callback_data=f"buy_{cid}")
        kb.button(text="⏳ Предзаказ", callback_data=f"preorder_from_cat_{cid}")
    if cat_group == "l0gu_1970":
        kb.button(text="Назад к операторам", callback_data="back_to_l0gu", icon_custom_emoji_id=CustomEmoji.BACK)
    elif cat_group == "gy_1970":
        kb.button(text="Назад к GY", callback_data="back_to_gy", icon_custom_emoji_id=CustomEmoji.BACK)
    else:
        kb.button(text="Назад к разделам", callback_data="back_to_main_catalog", icon_custom_emoji_id=CustomEmoji.BACK)
    kb.adjust(1)
    await call.message.delete()
    await call.message.answer(text, reply_markup=kb.as_markup(), parse_mode="HTML")
    await call.answer()

# --- ПРЕДЗАКАЗ ---
@dp.callback_query(F.data.startswith("preorder_cat_"))
async def preorder_cat_cb(call: types.CallbackQuery, state: FSMContext):
    try:
        cat_id = int(call.data.split("_")[2])
    except (IndexError, ValueError):
        await call.answer("❌ Ошибка", show_alert=True)
        return
    cat = await fetchone("SELECT name, price FROM categories WHERE id = ?", (cat_id,))
    if not cat:
        await call.answer("❌ Категория не найдена", show_alert=True)
        return
    await state.update_data(preorder_cat_id=cat_id, preorder_cat_name=cat[0], preorder_price=cat[1])
    await state.set_state(ShopState.waiting_for_preorder_quantity)
    await call.message.answer(
        f'<tg-emoji emoji-id="{CustomEmoji.PREORDER_BOX}">📦</tg-emoji> <b>Предзаказ: {cat[0]}</b>\n'
        f'<tg-emoji emoji-id="{CustomEmoji.MONEY}">💰</tg-emoji> Цена: {cat[1]} USDT/шт\n\n'
        f'<tg-emoji emoji-id="{CustomEmoji.QUESTION}">❓</tg-emoji> Сколько штук хотите предзаказать? (максимум {MAX_QUANTITY_PER_PURCHASE} шт.)\n'
        f"Отправьте число:", parse_mode="HTML"
    )
    await call.answer()

@dp.message(ShopState.waiting_for_preorder_quantity)
async def preorder_quantity_msg(message: types.Message, state: FSMContext):
    if not message.text.isdigit():
        return await message.answer(f'<tg-emoji emoji-id="{CustomEmoji.WARNING}">❗️</tg-emoji> Введите положительное число.', parse_mode="HTML")
    qty = int(message.text)
    if qty <= 0 or qty > MAX_QUANTITY_PER_PURCHASE:
        return await message.answer(f'<tg-emoji emoji-id="{CustomEmoji.WARNING}">❗️</tg-emoji> Введите число от 1 до {MAX_QUANTITY_PER_PURCHASE}.', parse_mode="HTML")
    data = await state.get_data()
    cat_id = data['preorder_cat_id']
    cat_name = data['preorder_cat_name']
    price = data['preorder_price']
    total = round(price * qty, 2)
    await state.update_data(preorder_qty=qty, preorder_total=total)
    await state.set_state(ShopState.waiting_for_preorder_provider)
    kb = InlineKeyboardBuilder()
    kb.button(text="Оплатить @CryptoBot", callback_data="preorder_pay_crypto", icon_custom_emoji_id=CustomEmoji.CRYPTO_PAY)
    kb.button(text="Оплатить @xRocket", callback_data="preorder_pay_xrocket", icon_custom_emoji_id=CustomEmoji.XROCKET_PAY)
    kb.adjust(1)
    await message.answer(
        f'<tg-emoji emoji-id="{CustomEmoji.PREORDER_BOX}">📦</tg-emoji> {cat_name} x{qty}\n'
        f'<tg-emoji emoji-id="{CustomEmoji.MONEY}">💰</tg-emoji> Сумма: {total} USDT\n\n'
        f'Выберите способ оплаты:',
        reply_markup=kb.as_markup(), parse_mode="HTML"
    )

@dp.callback_query(F.data.in_({"preorder_pay_crypto", "preorder_pay_xrocket"}), ShopState.waiting_for_preorder_provider)
async def preorder_pay_provider_cb(call: types.CallbackQuery, state: FSMContext):
    provider = "xrocket" if call.data == "preorder_pay_xrocket" else "crypto"
    data = await state.get_data()
    cat_id = data['preorder_cat_id']
    cat_name = data['preorder_cat_name']
    qty = data['preorder_qty']
    total = data['preorder_total']
    user_id = call.from_user.id

    await execute_query(
        "INSERT INTO preorders (user_id, cat_id, quantity, total, created_at, status) VALUES (?, ?, ?, ?, ?, ?)",
        (user_id, cat_id, qty, total, datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S"), "pending"),
        commit=True
    )
    preorder = await fetchone("SELECT id FROM preorders WHERE user_id = ? AND cat_id = ? ORDER BY id DESC LIMIT 1",
                              (user_id, cat_id))
    preorder_id = preorder[0] if preorder else None

    if provider == "xrocket":
        inv = await xrocket_create_invoice(
            amount=total, description=f"Предзаказ: {cat_name} x{qty}", expired_in=3600
        )
        if not inv.get('ok'):
            await call.message.answer(f"⚠ Ошибка API xRocket: {inv.get('description', 'Неизвестная ошибка')}")
            await state.clear()
            await call.answer()
            return
        invoice_id = inv['id']
        pay_url = inv['link']
        provider_emoji = CustomEmoji.XROCKET_PAY
    else:
        inv = await crypto_api("createInvoice", {
            "asset": "USDT", "amount": str(total),
            "description": f"Предзаказ: {cat_name} x{qty}", "expires_in": 3600
        })
        if not inv.get('ok'):
            await call.message.answer(f"⚠ Ошибка API: {inv.get('description', 'Неизвестная ошибка')}")
            await state.clear()
            await call.answer()
            return
        invoice_id = inv['result']['invoice_id']
        pay_url = inv['result']['pay_url']
        provider_emoji = CustomEmoji.CRYPTO_PAY

    pending_payments[invoice_id] = {
        'user_id': user_id, 'cat_id': cat_id, 'quantity': qty,
        'total': total, 'created_at': datetime.now(), 'is_preorder': True,
        'preorder_id': preorder_id, 'provider': provider
    }
    kb = InlineKeyboardBuilder()
    kb.button(text="✅ Оплатить предзаказ", url=pay_url, icon_custom_emoji_id=provider_emoji)
    kb.adjust(1)
    msg = await call.message.answer(
        f'<tg-emoji emoji-id="{CustomEmoji.PREORDER_CLOCK}">🕞</tg-emoji> <b>Предзаказ оформлен!</b>\n\n'
        f'<tg-emoji emoji-id="{CustomEmoji.PREORDER_BOX}">📦</tg-emoji> Товар: {cat_name}\n'
        f'<tg-emoji emoji-id="{CustomEmoji.PREORDER_SETTINGS}">🔢</tg-emoji> Количество: {qty} шт.\n'
        f'<tg-emoji emoji-id="{CustomEmoji.MONEY}">💰</tg-emoji> Сумма: {total} USDT\n\n'
        f'Нажмите кнопку ниже для оплаты:',
        reply_markup=kb.as_markup(), parse_mode="HTML"
    )
    pending_payments[invoice_id]['msg'] = msg
    asyncio.create_task(auto_check_preorder_payment(invoice_id, user_id, cat_id, qty, msg, total, cat_name, preorder_id, provider))
    await state.clear()
    await call.answer()

async def auto_check_preorder_payment(invoice_id, user_id: int, cat_id: int, quantity: int,
                                      msg_to_edit: types.Message, total_cost: float, cat_name: str,
                                      preorder_id: int = None, provider: str = "crypto"):
    async with payment_check_semaphore:
        for attempt in range(PAYMENT_CHECK_ATTEMPTS):
            await asyncio.sleep(PAYMENT_CHECK_INTERVAL)
            if invoice_id not in pending_payments:
                return
            if provider == "xrocket":
                inv = await xrocket_get_invoice(str(invoice_id))
                if not inv.get('ok'):
                    continue
                is_paid = _xrocket_is_paid(inv.get('status'), inv.get('paid_amount'))
                is_expired = _xrocket_is_expired(inv.get('status'))
            else:
                res = await crypto_api("getInvoices", {"invoice_ids": str(invoice_id)})
                if not (res.get('ok') and res['result'].get('items')):
                    continue
                cb_inv = res['result']['items'][0]
                is_paid = cb_inv['status'] == 'paid'
                is_expired = cb_inv['status'] == 'expired'

            if is_paid:
                if preorder_id:
                    await execute_query("UPDATE preorders SET status = 'paid', paid_at = ? WHERE id = ?",
                                      (datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S"), preorder_id), commit=True)
                del pending_payments[invoice_id]
                await bot.send_message(user_id,
                    f'<tg-emoji emoji-id="{CustomEmoji.PREORDER_CHECK}">✅</tg-emoji> <b>Предзаказ оплачен!</b>\n\n'
                    f'<tg-emoji emoji-id="{CustomEmoji.PREORDER_BOX}">📦</tg-emoji> Товар: {cat_name}\n'
                    f'<tg-emoji emoji-id="{CustomEmoji.MONEY}">💰</tg-emoji> Сумма: {total_cost} USDT\n\n'
                    f'Как только товар появится, он будет автоматически выдан вам.',
                    parse_mode="HTML"
                )
                try:
                    await msg_to_edit.delete()
                except:
                    pass
                return
            elif is_expired:
                if preorder_id:
                    await execute_query("UPDATE preorders SET status = 'expired' WHERE id = ?", (preorder_id,), commit=True)
                await msg_to_edit.edit_text(f'<tg-emoji emoji-id="{CustomEmoji.WARNING}">❌</tg-emoji> Счет просрочен.', parse_mode="HTML")
                del pending_payments[invoice_id]
                return
        if invoice_id in pending_payments:
            if preorder_id:
                await execute_query("UPDATE preorders SET status = 'expired' WHERE id = ?", (preorder_id,), commit=True)
            await msg_to_edit.edit_text(f'<tg-emoji emoji-id="{CustomEmoji.WARNING}">❌</tg-emoji> Время ожидания истекло.', parse_mode="HTML")
            del pending_payments[invoice_id]

@dp.callback_query(F.data == "cancel_preorder")
async def cancel_preorder_cb(call: types.CallbackQuery, state: FSMContext):
    await state.clear()
    await call.message.edit_text(f'<tg-emoji emoji-id="{CustomEmoji.WARNING}">❌</tg-emoji> Предзаказ отменен', parse_mode="HTML")
    await call.answer()

@dp.callback_query(F.data.startswith("preorder_from_cat_"))
async def preorder_from_cat_cb(call: types.CallbackQuery, state: FSMContext):
    try:
        cid = int(call.data.split("_")[3])
    except (IndexError, ValueError):
        await call.answer("❌ Ошибка", show_alert=True)
        return
    cat = await fetchone("SELECT name, price FROM categories WHERE id = ?", (cid,))
    if not cat:
        await call.answer("❌ Категория не найдена", show_alert=True)
        return
    await state.update_data(preorder_cat_id=cid, preorder_cat_name=cat[0], preorder_price=cat[1])
    await state.set_state(ShopState.waiting_for_preorder_quantity)
    await call.message.answer(
        f'<tg-emoji emoji-id="{CustomEmoji.PREORDER_CLOCK}">🕞</tg-emoji> <b>Предзаказ: {cat[0]}</b>\n'
        f'<tg-emoji emoji-id="{CustomEmoji.MONEY}">💰</tg-emoji> Цена: {cat[1]} USDT/шт\n\n'
        f'<tg-emoji emoji-id="{CustomEmoji.QUESTION}">❓</tg-emoji> Сколько штук хотите предзаказать? (максимум {MAX_QUANTITY_PER_PURCHASE} шт.)\n'
        f"Отправьте число:", parse_mode="HTML"
    )
    await call.answer()

# --- ПОКУПКА ---
@dp.callback_query(F.data.startswith("buy_"))
async def buy_cb(call: types.CallbackQuery, state: FSMContext):
    try:
        cid = int(call.data.split("_")[1])
    except:
        await call.answer("❌ Ошибка")
        return
    await state.update_data(cid=cid)
    await state.set_state(ShopState.waiting_for_quantity)
    await call.message.answer(
        f'<tg-emoji emoji-id="{CustomEmoji.QUESTION}">❓</tg-emoji> Сколько штук хотите купить? (максимум {MAX_QUANTITY_PER_PURCHASE} шт.)\nОтправьте число:',
        parse_mode="HTML"
    )
    await call.answer()

@dp.message(ShopState.waiting_for_quantity)
async def quantity_msg(message: types.Message, state: FSMContext):
    if not message.text.isdigit():
        return await message.answer(f'<tg-emoji emoji-id="{CustomEmoji.WARNING}">❗️</tg-emoji> Введите положительное число.', parse_mode="HTML")
    qty = int(message.text)
    if qty <= 0 or qty > MAX_QUANTITY_PER_PURCHASE:
        return await message.answer(f'<tg-emoji emoji-id="{CustomEmoji.WARNING}">❗️</tg-emoji> Введите число от 1 до {MAX_QUANTITY_PER_PURCHASE}.', parse_mode="HTML")
    data = await state.get_data()
    cid = data['cid']
    stock = await fetchone("SELECT COUNT(*) FROM inventory WHERE cat_id = ?", (cid,))
    stock_count = stock[0] if stock else 0
    if qty > stock_count:
        await state.clear()
        return await message.answer(
            f'<tg-emoji emoji-id="{CustomEmoji.WARNING}">❗️</tg-emoji> В наличии только {stock_count} шт.\n\nВы можете оформить <b>предзаказ</b>!',
            parse_mode="HTML"
        )
    cat = await fetchone("SELECT name, price FROM categories WHERE id = ?", (cid,))
    if not cat:
        await state.clear()
        return await message.answer("❌ Категория не найдена")
    price = float(cat[1])
    total = round(price * qty, 2)
    balance = await get_balance(message.from_user.id)
    discount = 0
    if hasattr(bot, 'user_promos') and message.from_user.id in bot.user_promos:
        promo_data = bot.user_promos[message.from_user.id]
        if promo_data['type'] == 'percent':
            discount = total * promo_data['discount'] / 100
            total = round(total - discount, 2)
            await message.answer(f'<tg-emoji emoji-id="{CustomEmoji.PROMO}">🎫</tg-emoji> Применена скидка {promo_data["discount"]}%! Сумма к оплате: {total} USDT', parse_mode="HTML")
            del bot.user_promos[message.from_user.id]
    await state.update_data(quantity=qty, total=total, cat_name=cat[0], cid=cid)
    await state.set_state(ShopState.waiting_for_payment_method)
    kb = InlineKeyboardBuilder()
    kb.button(text="Оплатить @CryptoBot", callback_data="pay_crypto", icon_custom_emoji_id=CustomEmoji.CRYPTO_PAY)
    kb.button(text="Оплатить @xRocket", callback_data="pay_xrocket", icon_custom_emoji_id=CustomEmoji.XROCKET_PAY)
    kb.button(text="Баланс (Кэшбек 3%)", callback_data="pay_balance", icon_custom_emoji_id=CustomEmoji.BALANCE_PAY)
    kb.adjust(1)
    await message.answer(
        f"Вы выбрали {hbold(cat[0])} x{qty}\n"
        f"Цена за шт: {price} USDT\n"
        f"Итого: {hbold(str(total))} USDT\n"
        f"💰 Ваш баланс: {hbold(str(balance))} USDT\n\n"
        f"Выберите способ оплаты:",
        reply_markup=kb.as_markup(), parse_mode="HTML"
    )

@dp.callback_query(F.data == "pay_crypto")
async def pay_crypto_cb(call: types.CallbackQuery, state: FSMContext):
    data = await state.get_data()
    cid = data['cid']
    quantity = data['quantity']
    total = data['total']
    cat_name = data['cat_name']
    user_id = call.from_user.id
    inv = await crypto_api("createInvoice", {
        "asset": "USDT", "amount": str(total),
        "description": f"{cat_name} x{quantity}", "expires_in": 1800
    })
    if not inv.get('ok'):
        await call.message.answer(f"⚠ Ошибка API: {inv.get('description', 'Неизвестная ошибка')}")
        await state.clear()
        return
    invoice_id = inv['result']['invoice_id']
    pending_payments[invoice_id] = {
        'user_id': user_id, 'cat_id': cid, 'quantity': quantity,
        'total': total, 'created_at': datetime.now(), 'is_preorder': False, 'provider': 'crypto'
    }
    kb = InlineKeyboardBuilder()
    kb.button(text="Оплатить", url=inv['result']['pay_url'], icon_custom_emoji_id=CustomEmoji.CHECKMARK)
    kb.adjust(1)
    msg = await call.message.answer(
        f'<tg-emoji emoji-id="{CustomEmoji.PREORDER_BOX}">📦</tg-emoji> {cat_name} — {quantity} шт.\n'
        f'<tg-emoji emoji-id="{CustomEmoji.MONEY}">💰</tg-emoji> Сумма: {total} USDT\n'
        f'<tg-emoji emoji-id="{CustomEmoji.TIME}">⏳</tg-emoji> Счет действителен 30 минут\n\nНажмите кнопку ниже для оплаты:',
        reply_markup=kb.as_markup(), parse_mode="HTML"
    )
    pending_payments[invoice_id]['msg'] = msg
    asyncio.create_task(auto_check_payment(invoice_id, user_id, cid, quantity, msg, total, 'crypto'))
    await state.clear()
    await call.answer()

@dp.callback_query(F.data == "pay_xrocket")
async def pay_xrocket_cb(call: types.CallbackQuery, state: FSMContext):
    data = await state.get_data()
    cid = data['cid']
    quantity = data['quantity']
    total = data['total']
    cat_name = data['cat_name']
    user_id = call.from_user.id
    inv = await xrocket_create_invoice(
        amount=total,
        description=f"{cat_name} x{quantity}",
        expired_in=1800
    )
    if not inv.get('ok'):
        await call.message.answer(f"⚠ Ошибка API xRocket: {inv.get('description', 'Неизвестная ошибка')}")
        await state.clear()
        return
    invoice_id = inv['id']
    pending_payments[invoice_id] = {
        'user_id': user_id, 'cat_id': cid, 'quantity': quantity,
        'total': total, 'created_at': datetime.now(), 'is_preorder': False, 'provider': 'xrocket'
    }
    kb = InlineKeyboardBuilder()
    kb.button(text="Оплатить", url=inv['link'], icon_custom_emoji_id=CustomEmoji.XROCKET_PAY)
    kb.adjust(1)
    msg = await call.message.answer(
        f'<tg-emoji emoji-id="{CustomEmoji.PREORDER_BOX}">📦</tg-emoji> {cat_name} — {quantity} шт.\n'
        f'<tg-emoji emoji-id="{CustomEmoji.MONEY}">💰</tg-emoji> Сумма: {total} USDT\n'
        f'<tg-emoji emoji-id="{CustomEmoji.TIME}">⏳</tg-emoji> Счет действителен 30 минут\n\nНажмите кнопку ниже для оплаты:',
        reply_markup=kb.as_markup(), parse_mode="HTML"
    )
    pending_payments[invoice_id]['msg'] = msg
    asyncio.create_task(auto_check_payment(invoice_id, user_id, cid, quantity, msg, total, 'xrocket'))
    await state.clear()
    await call.answer()

@dp.callback_query(F.data == "pay_balance")
async def pay_balance_cb(call: types.CallbackQuery, state: FSMContext):
    data = await state.get_data()
    cid = data['cid']
    quantity = data['quantity']
    total = data['total']
    cat_name = data['cat_name']
    user_id = call.from_user.id
    balance = await get_balance(user_id)
    if balance < total:
        await call.message.answer(
            f'<tg-emoji emoji-id="{CustomEmoji.WARNING}">❌</tg-emoji> Недостаточно средств.\nВаш баланс: {balance} USDT\nНеобходимо: {total} USDT',
            parse_mode="HTML"
        )
        await state.clear()
        await call.answer()
        return
    try:
        items = await buy_items_with_transaction(cid, quantity, user_id, total)
        if not items:
            await call.message.answer(f'<tg-emoji emoji-id="{CustomEmoji.WARNING}">❌</tg-emoji> Товар закончился. Деньги не списаны.', parse_mode="HTML")
            await state.clear()
            await call.answer()
            return
        res_text = f'<tg-emoji emoji-id="{CustomEmoji.PREORDER_CHECK}">✅</tg-emoji> Оплачено с баланса!\n\n<tg-emoji emoji-id="{CustomEmoji.PREORDER_BOX}">🎁</tg-emoji> Ваш товар:\n'
        for _, i_data in items:
            res_text += f"• `{i_data}`\n"
        await call.message.answer(res_text, parse_mode="Markdown")
        referrer = await fetchone("SELECT referrer_id FROM users WHERE id = ?", (user_id,))
        if referrer and referrer[0]:
            ref_bonus = round(total * 0.1, 2)
            await add_referral_earning(referrer[0], ref_bonus, user_id)
            await bot.send_message(referrer[0], f'<tg-emoji emoji-id="{CustomEmoji.MONEY}">💰</tg-emoji> Вы получили {ref_bonus} USDT (10%) от покупки!', parse_mode="HTML")
    except Exception as e:
        logger.error(f"Payment error: {e}")
        await call.message.answer(f'<tg-emoji emoji-id="{CustomEmoji.WARNING}">❌</tg-emoji> Ошибка при покупке. Обратитесь в поддержку.', parse_mode="HTML")
    await state.clear()
    await call.answer()

# --- ПРОФИЛЬ ---
async def show_profile_with_image(user_id: int, target_message: types.Message):
    username = (await bot.get_chat(user_id)).username or "не указан"
    total_bought = await fetchone("SELECT total FROM users WHERE id = ?", (user_id,))
    balance = await get_balance(user_id)
    active_preorders = await fetchone("SELECT COUNT(*) FROM preorders WHERE user_id = ? AND status = 'paid'", (user_id,))
    active_preorders_count = active_preorders[0] if active_preorders else 0
    pending_preorders = await fetchone("SELECT COUNT(*) FROM preorders WHERE user_id = ? AND status = 'pending'", (user_id,))
    pending_preorders_count = pending_preorders[0] if pending_preorders else 0
    text = (
        f'<tg-emoji emoji-id="{CustomEmoji.PROFILE_EMOJI}">🎥</tg-emoji> <b>Профиль</b>\n'
        f'<tg-emoji emoji-id="{CustomEmoji.SHIELD}">🛡</tg-emoji> ID: {user_id}\n'
        f'<tg-emoji emoji-id="{CustomEmoji.CHECK}">✅</tg-emoji> Username: @{username}\n'
        f'<tg-emoji emoji-id="{CustomEmoji.LOCK}">🔒</tg-emoji> Баланс: {balance} USDT\n'
        f'<tg-emoji emoji-id="{CustomEmoji.UP}">🔼</tg-emoji> Покупок: {total_bought[0] if total_bought else 0}\n'
        f'<tg-emoji emoji-id="{CustomEmoji.PREORDER_CLOCK}">🕞</tg-emoji> Активных предзаказов: {active_preorders_count}\n'
        f'<tg-emoji emoji-id="{CustomEmoji.TIME}">⏳</tg-emoji> Ожидают оплаты: {pending_preorders_count}'
    )
    kb = InlineKeyboardBuilder()
    kb.button(text="История покупок", callback_data="profile_history", icon_custom_emoji_id=CustomEmoji.TROPHY)
    kb.button(text="Реферальная ссылка", callback_data="profile_referral", icon_custom_emoji_id=CustomEmoji.USER)
    kb.button(text="Промокод", callback_data="profile_promo", icon_custom_emoji_id=CustomEmoji.PROMO)
    kb.button(text="Мои предзаказы", callback_data="profile_preorders", icon_custom_emoji_id=CustomEmoji.PREORDER_CLOCK)
    kb.button(text="Вывод средств", callback_data="profile_withdraw", icon_custom_emoji_id=CustomEmoji.WITHDRAW)
    kb.adjust(1)
    await send_with_image(target_message, 'EleghantProfile', text, kb.as_markup())

# ═══════════════════════════════════════════════════════════════════════════════
# СИСТЕМА ВЫВОДА СРЕДСТВ
# ═══════════════════════════════════════════════════════════════════════════════

@dp.callback_query(F.data == "profile_withdraw")
async def profile_withdraw_cb(call: types.CallbackQuery, state: FSMContext):
    user_id = call.from_user.id
    balance = await get_balance(user_id)

    if balance <= 0:
        await call.answer(
            "❌ На вашем балансе недостаточно средств для вывода.",
            show_alert=True
        )
        return

    await state.set_state(ShopState.waiting_for_withdraw_amount)
    kb = InlineKeyboardBuilder()
    kb.button(text="❌ Отмена", callback_data="cancel_withdraw")
    kb.adjust(1)
    await call.message.answer(
        f'<tg-emoji emoji-id="{CustomEmoji.MONEY}">💸</tg-emoji> <b>Вывод средств</b>\n\n'
        f'<tg-emoji emoji-id="{CustomEmoji.LOCK}">🔒</tg-emoji> Ваш баланс: <b>{balance} USDT</b>\n\n'
        f'Введите сумму для вывода (минимум 1 USDT):',
        parse_mode="HTML",
        reply_markup=kb.as_markup()
    )
    await call.answer()

@dp.message(ShopState.waiting_for_withdraw_amount)
async def withdraw_amount_msg(message: types.Message, state: FSMContext):
    user_id = message.from_user.id
    balance = await get_balance(user_id)

    try:
        amount = float(message.text.replace(',', '.'))
        if amount <= 0:
            raise ValueError
        amount = round(amount, 2)
    except (ValueError, AttributeError):
        await message.answer(
            f'<tg-emoji emoji-id="{CustomEmoji.WARNING}">❗️</tg-emoji> Введите корректную сумму (например: 10 или 5.50)',
            parse_mode="HTML"
        )
        return

    if amount < 1:
        await message.answer(
            f'<tg-emoji emoji-id="{CustomEmoji.WARNING}">❗️</tg-emoji> Минимальная сумма вывода — <b>1 USDT</b>.',
            parse_mode="HTML"
        )
        return

    if amount > balance:
        await message.answer(
            f'<tg-emoji emoji-id="{CustomEmoji.WARNING}">❌</tg-emoji> <b>Недостаточно средств!</b>\n\n'
            f'Ваш баланс: <b>{balance} USDT</b>\n'
            f'Запрошено: <b>{amount} USDT</b>\n\n'
            f'Пожалуйста, введите сумму не превышающую баланс.',
            parse_mode="HTML"
        )
        return

    await state.update_data(withdraw_amount=amount)
    await state.set_state(ShopState.waiting_for_withdraw_confirm)

    kb = InlineKeyboardBuilder()
    kb.button(text="✅ Да, вывести", callback_data="confirm_withdraw")
    kb.button(text="❌ Отмена", callback_data="cancel_withdraw")
    kb.adjust(2)

    await message.answer(
        f'<tg-emoji emoji-id="{CustomEmoji.QUESTION}">❓</tg-emoji> <b>Подтверждение вывода</b>\n\n'
        f'Вы уверены, что хотите вывести <b>{amount} USDT</b>?\n\n'
        f'После подтверждения заявка будет отправлена администратору.',
        parse_mode="HTML",
        reply_markup=kb.as_markup()
    )

@dp.callback_query(F.data == "confirm_withdraw", ShopState.waiting_for_withdraw_confirm)
async def confirm_withdraw_cb(call: types.CallbackQuery, state: FSMContext):
    user_id = call.from_user.id
    data = await state.get_data()
    amount = data.get('withdraw_amount', 0)

    # Повторная проверка баланса перед созданием заявки
    balance = await get_balance(user_id)
    if amount > balance:
        await call.message.edit_text(
            f'<tg-emoji emoji-id="{CustomEmoji.WARNING}">❌</tg-emoji> Недостаточно средств на балансе. '
            f'Текущий баланс: {balance} USDT.',
            parse_mode="HTML"
        )
        await state.clear()
        await call.answer()
        return

    username = call.from_user.username or ""
    now_str = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")

    # Сохраняем заявку в БД
    await execute_query(
        "INSERT INTO withdraw_requests (user_id, username, amount, status, created_at) VALUES (?, ?, ?, 'pending', ?)",
        (user_id, username, amount, now_str),
        commit=True
    )
    request_row = await fetchone(
        "SELECT id FROM withdraw_requests WHERE user_id = ? ORDER BY id DESC LIMIT 1",
        (user_id,)
    )
    request_id = request_row[0] if request_row else "?"

    # Уведомляем пользователя
    await call.message.edit_text(
        f'<tg-emoji emoji-id="{CustomEmoji.PREORDER_CHECK}">✅</tg-emoji> <b>Заявка создана!</b>\n\n'
        f'Администрация рассмотрит её в ближайшее время.\n\n'
        f'<tg-emoji emoji-id="{CustomEmoji.MONEY}">💰</tg-emoji> Сумма вывода: <b>{amount} USDT</b>\n'
        f'<tg-emoji emoji-id="{CustomEmoji.TIME}">⏳</tg-emoji> Номер заявки: <b>#{request_id}</b>',
        parse_mode="HTML"
    )

    # Уведомляем администратора
    user_link = f"@{username}" if username else f"<a href='tg://user?id={user_id}'>ID: {user_id}</a>"
    admin_text = (
        f'💸 <b>Новая заявка на вывод #{request_id}</b>\n\n'
        f'👤 Пользователь: {user_link}\n'
        f'🆔 ID: <code>{user_id}</code>\n'
        f'💰 Сумма: <b>{amount} USDT</b>\n'
        f'📅 Дата: {now_str[:16]}'
    )
    admin_kb = InlineKeyboardBuilder()
    admin_kb.button(text="✅ Одобрить", callback_data=f"withdraw_approve_{request_id}")
    admin_kb.button(text="❌ Отклонить", callback_data=f"withdraw_reject_{request_id}")
    admin_kb.adjust(2)

    try:
        await bot.send_message(
            ADMIN_ID,
            admin_text,
            parse_mode="HTML",
            reply_markup=admin_kb.as_markup()
        )
    except Exception as e:
        logger.error(f"Не удалось уведомить администратора о заявке #{request_id}: {e}")

    await state.clear()
    await call.answer()

@dp.callback_query(F.data == "cancel_withdraw")
async def cancel_withdraw_cb(call: types.CallbackQuery, state: FSMContext):
    await state.clear()
    await call.message.edit_text(
        f'<tg-emoji emoji-id="{CustomEmoji.WARNING}">❌</tg-emoji> Вывод средств отменён.',
        parse_mode="HTML"
    )
    await call.answer()

# --- ОБРАБОТКА ЗАЯВОК НА ВЫВОД АДМИНИСТРАТОРОМ ---

@dp.callback_query(F.data.startswith("withdraw_approve_"))
async def withdraw_approve_cb(call: types.CallbackQuery):
    if call.from_user.id != ADMIN_ID:
        await call.answer("❌ Нет доступа", show_alert=True)
        return

    try:
        request_id = int(call.data.split("_")[2])
    except (IndexError, ValueError):
        await call.answer("❌ Ошибка", show_alert=True)
        return

    request = await fetchone(
        "SELECT user_id, username, amount, status FROM withdraw_requests WHERE id = ?",
        (request_id,)
    )
    if not request:
        await call.message.edit_text(f"❌ Заявка #{request_id} не найдена.")
        await call.answer()
        return

    user_id, username, amount, status = request

    if status != 'pending':
        await call.answer(f"⚠️ Заявка уже обработана (статус: {status})", show_alert=True)
        return

    # Проверяем баланс пользователя
    balance = await get_balance(user_id)
    if balance < amount:
        await call.message.edit_text(
            f"❌ У пользователя недостаточно средств!\n"
            f"Баланс: {balance} USDT, заявка: {amount} USDT\n\n"
            f"Заявка #{request_id} отклонена автоматически."
        )
        await execute_query(
            "UPDATE withdraw_requests SET status = 'rejected', processed_at = ?, admin_note = ? WHERE id = ?",
            (datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S"), "Недостаточно средств", request_id),
            commit=True
        )
        await call.answer()
        return

    # Списываем с баланса
    await update_balance(user_id, -amount, "withdraw", ADMIN_ID)

    # Обновляем статус заявки
    await execute_query(
        "UPDATE withdraw_requests SET status = 'approved', processed_at = ? WHERE id = ?",
        (datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S"), request_id),
        commit=True
    )

    user_link = f"@{username}" if username else f"ID: {user_id}"
    await call.message.edit_text(
        f'✅ <b>Заявка #{request_id} одобрена</b>\n\n'
        f'👤 Пользователь: {user_link}\n'
        f'💰 Сумма: {amount} USDT\n'
        f'💳 Баланс списан.',
        parse_mode="HTML"
    )

    # Уведомляем пользователя
    try:
        await bot.send_message(
            user_id,
            f'<tg-emoji emoji-id="{CustomEmoji.PREORDER_CHECK}">✅</tg-emoji> <b>Ваша заявка на вывод одобрена!</b>\n\n'
            f'<tg-emoji emoji-id="{CustomEmoji.MONEY}">💰</tg-emoji> Сумма: <b>{amount} USDT</b>\n\n'
            f'Средства будут переведены вам в ближайшее время. По вопросам обращайтесь в поддержку.',
            parse_mode="HTML"
        )
    except Exception as e:
        logger.error(f"Не удалось уведомить пользователя {user_id} об одобрении заявки: {e}")

    await call.answer("✅ Заявка одобрена, баланс списан!")
    logger.info(f"Admin {call.from_user.id} approved withdraw #{request_id} for user {user_id}, amount {amount} USDT")

@dp.callback_query(F.data.startswith("withdraw_reject_"))
async def withdraw_reject_cb(call: types.CallbackQuery, state: FSMContext):
    if call.from_user.id != ADMIN_ID:
        await call.answer("❌ Нет доступа", show_alert=True)
        return

    try:
        request_id = int(call.data.split("_")[2])
    except (IndexError, ValueError):
        await call.answer("❌ Ошибка", show_alert=True)
        return

    request = await fetchone(
        "SELECT user_id, username, amount, status FROM withdraw_requests WHERE id = ?",
        (request_id,)
    )
    if not request:
        await call.message.edit_text(f"❌ Заявка #{request_id} не найдена.")
        await call.answer()
        return

    user_id, username, amount, status = request

    if status != 'pending':
        await call.answer(f"⚠️ Заявка уже обработана (статус: {status})", show_alert=True)
        return

    await state.update_data(reject_request_id=request_id, reject_user_id=user_id,
                            reject_username=username, reject_amount=amount)
    await state.set_state(AdminState.withdraw_reject_reason)

    kb = InlineKeyboardBuilder()
    kb.button(text="Пропустить причину", callback_data=f"withdraw_reject_noreason_{request_id}")
    kb.adjust(1)

    await call.message.answer(
        f'❌ <b>Отклонение заявки #{request_id}</b>\n\n'
        f'Введите причину отклонения (или нажмите кнопку, чтобы пропустить):',
        parse_mode="HTML",
        reply_markup=kb.as_markup()
    )
    await call.answer()

@dp.message(AdminState.withdraw_reject_reason)
async def withdraw_reject_reason_msg(message: types.Message, state: FSMContext):
    if message.from_user.id != ADMIN_ID:
        return
    data = await state.get_data()
    request_id = data['reject_request_id']
    user_id = data['reject_user_id']
    username = data['reject_username']
    amount = data['reject_amount']
    reason = message.text.strip()
    await _do_reject_withdraw(request_id, user_id, username, amount, reason, state, message)

@dp.callback_query(F.data.startswith("withdraw_reject_noreason_"))
async def withdraw_reject_noreason_cb(call: types.CallbackQuery, state: FSMContext):
    if call.from_user.id != ADMIN_ID:
        return
    data = await state.get_data()
    request_id = data.get('reject_request_id')
    user_id = data.get('reject_user_id')
    username = data.get('reject_username', '')
    amount = data.get('reject_amount', 0)
    await _do_reject_withdraw(request_id, user_id, username, amount, None, state, call.message)
    await call.answer()

async def _do_reject_withdraw(request_id, user_id, username, amount, reason, state, message_obj):
    note = reason if reason else "Без причины"
    await execute_query(
        "UPDATE withdraw_requests SET status = 'rejected', processed_at = ?, admin_note = ? WHERE id = ?",
        (datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S"), note, request_id),
        commit=True
    )
    user_link = f"@{username}" if username else f"ID: {user_id}"
    await message_obj.answer(
        f'❌ <b>Заявка #{request_id} отклонена</b>\n\n'
        f'👤 Пользователь: {user_link}\n'
        f'💰 Сумма: {amount} USDT\n'
        f'📝 Причина: {note}',
        parse_mode="HTML"
    )
    reason_text = f'\n📝 Причина: {reason}' if reason else ''
    try:
        await bot.send_message(
            user_id,
            f'<tg-emoji emoji-id="{CustomEmoji.WARNING}">❌</tg-emoji> <b>Ваша заявка на вывод отклонена.</b>\n\n'
            f'<tg-emoji emoji-id="{CustomEmoji.MONEY}">💰</tg-emoji> Сумма: <b>{amount} USDT</b>'
            f'{reason_text}\n\n'
            f'Ваш баланс не изменился. По вопросам обращайтесь в поддержку.',
            parse_mode="HTML"
        )
    except Exception as e:
        logger.error(f"Не удалось уведомить пользователя {user_id} об отклонении заявки: {e}")
    logger.info(f"Withdraw #{request_id} rejected for user {user_id}, reason: {note}")
    await state.clear()

# --- КОМАНДА ПРОСМОТРА ЗАЯВОК НА ВЫВОД (АДМИН) ---
@dp.message(Command("withdraws"))
async def cmd_withdraws(message: types.Message):
    if message.from_user.id != ADMIN_ID:
        return
    requests = await fetchall(
        "SELECT id, user_id, username, amount, status, created_at FROM withdraw_requests "
        "WHERE status = 'pending' ORDER BY created_at ASC"
    )
    if not requests:
        await message.answer("📭 Нет активных заявок на вывод.")
        return
    text = f'💸 <b>Активные заявки на вывод ({len(requests)}):</b>\n\n'
    for rid, uid, uname, amount, status, created in requests:
        u = f"@{uname}" if uname else f"ID:{uid}"
        text += f"#{rid} | {u} | {amount} USDT | {created[:16]}\n"
    await message.answer(text, parse_mode="HTML")

# ═══════════════════════════════════════════════════════════════════════════════
# КОНЕЦ СИСТЕМЫ ВЫВОДА
# ═══════════════════════════════════════════════════════════════════════════════

@dp.callback_query(F.data == "profile_preorders")
async def profile_preorders_cb(call: types.CallbackQuery):
    preorders = await fetchall(
        "SELECT id, cat_id, quantity, total, created_at, paid_at, status FROM preorders WHERE user_id = ? ORDER BY created_at DESC",
        (call.from_user.id,)
    )
    if not preorders:
        await call.message.edit_text(f'<tg-emoji emoji-id="{CustomEmoji.PREORDER_BOX}">📦</tg-emoji> У вас нет предзаказов.', parse_mode="HTML")
        return
    text = f'<tg-emoji emoji-id="{CustomEmoji.PREORDER_CLOCK}">🕞</tg-emoji> <b>Ваши предзаказы:</b>\n\n'
    for pid, cat_id, qty, total, created, paid_at, status in preorders:
        cat = await fetchone("SELECT name FROM categories WHERE id = ?", (cat_id,))
        cat_name = cat[0] if cat else "Неизвестно"
        status_map = {
            "pending": (f'<tg-emoji emoji-id="{CustomEmoji.TIME}">⏳</tg-emoji>', "Ожидает оплаты"),
            "paid": (f'<tg-emoji emoji-id="{CustomEmoji.PREORDER_CHECK}">✅</tg-emoji>', "Оплачен, ожидает выдачи"),
            "expired": (f'<tg-emoji emoji-id="{CustomEmoji.WARNING}">❌</tg-emoji>', "Просрочен"),
            "completed": (f'<tg-emoji emoji-id="{CustomEmoji.PREORDER_COMPLETED}">🎁</tg-emoji>', "Выполнен"),
        }
        status_emoji, status_text = status_map.get(status, ("❓", "Неизвестно"))
        text += f"{status_emoji} <b>#{pid}</b> - {cat_name}\n"
        text += f'   📦 {qty} шт. | 💰 {total} USDT\n'
        text += f'   📅 Создан: {created[:10] if created else "Неизвестно"}\n'
        if paid_at:
            text += f'   💳 Оплачен: {paid_at[:10]}\n'
        text += f"   {status_emoji} Статус: {status_text}\n\n"
    kb = InlineKeyboardBuilder()
    kb.button(text="Назад к профилю", callback_data="back_to_profile", icon_custom_emoji_id=CustomEmoji.BACK)
    try:
        await call.message.delete()
    except:
        pass
    await call.message.answer(text, reply_markup=kb.as_markup(), parse_mode="HTML")
    await call.answer()

@dp.callback_query(F.data == "profile_history")
async def profile_history_cb(call: types.CallbackQuery):
    history = await fetchall(
        "SELECT id, item_data, date FROM history WHERE user_id = ? ORDER BY id DESC LIMIT 10",
        (call.from_user.id,)
    )
    history_emoji = f'<tg-emoji emoji-id="{CustomEmoji.HISTORY}">✏️</tg-emoji>'
    if not history:
        text = f"{history_emoji} У вас пока нет покупок."
    else:
        text = f"{history_emoji} <b>Последние 10 покупок:</b>\n\n"
        for hid, item, date in history:
            short_item = item[:30] + "..." if len(item) > 30 else item
            text += f"• {date}: {hcode(short_item)}\n"
    kb = InlineKeyboardBuilder()
    kb.button(text="Назад к профилю", callback_data="back_to_profile", icon_custom_emoji_id=CustomEmoji.BACK)
    try:
        await call.message.delete()
    except:
        pass
    await call.message.answer(text, reply_markup=kb.as_markup(), parse_mode="HTML")
    await call.answer()

@dp.callback_query(F.data == "profile_referral")
async def profile_referral_cb(call: types.CallbackQuery):
    user_id = call.from_user.id
    ref_count, ref_earn = await get_referral_info(user_id)
    bot_info = await bot.get_me()
    link = f"https://t.me/{bot_info.username}?start=ref_{user_id}"
    text = (
        f'<tg-emoji emoji-id="{CustomEmoji.LINK}">🔗</tg-emoji> <b>Ваша реферальная ссылка:</b>\n{link}\n\n'
        f'<tg-emoji emoji-id="{CustomEmoji.USER}">👤</tg-emoji> Рефералов: {ref_count}\n'
        f'<tg-emoji emoji-id="{CustomEmoji.PLUS}">➕</tg-emoji> Заработано: {ref_earn} USDT\n\n'
        "За каждого приглашённого пользователя, совершившего покупку, вы получаете 10% от суммы его покупки."
    )
    kb = InlineKeyboardBuilder()
    kb.button(text="Назад к профилю", callback_data="back_to_profile", icon_custom_emoji_id=CustomEmoji.BACK)
    try:
        await call.message.delete()
    except:
        pass
    await send_with_image(call.message, 'ReferalIcon', text, kb.as_markup())
    await call.answer()

@dp.callback_query(F.data == "profile_promo")
async def profile_promo_cb(call: types.CallbackQuery, state: FSMContext):
    await state.set_state(ShopState.waiting_for_promo_code)
    await call.message.answer(f'<tg-emoji emoji-id="{CustomEmoji.PROMO}">🎫</tg-emoji> Введите промокод:', parse_mode="HTML")
    await call.answer()

@dp.message(ShopState.waiting_for_promo_code)
async def promo_code_activate(message: types.Message, state: FSMContext):
    user_id = message.from_user.id
    code = message.text.strip().upper()
    current_time = time.time()
    if user_id in user_promo_attempts:
        attempts, last_attempt = user_promo_attempts[user_id]
        if attempts >= MAX_PROMO_ATTEMPTS and current_time - last_attempt < PROMO_BLOCK_TIME:
            await message.answer(f'<tg-emoji emoji-id="{CustomEmoji.WARNING}">❌</tg-emoji> Слишком много попыток. Попробуйте через {int(PROMO_BLOCK_TIME - (current_time - last_attempt))} сек.', parse_mode="HTML")
            await state.clear()
            return
    promo = await fetchone("SELECT amount, max_uses, used, promo_type FROM promo_codes WHERE code = ?", (code,))
    if not promo:
        user_promo_attempts[user_id] = (user_promo_attempts.get(user_id, (0, current_time))[0] + 1, current_time)
        await message.answer(f'<tg-emoji emoji-id="{CustomEmoji.WARNING}">❌</tg-emoji> Промокод не найден.', parse_mode="HTML")
        await state.clear()
        return
    amount, max_uses, used, promo_type = promo
    if used >= max_uses:
        await message.answer(f'<tg-emoji emoji-id="{CustomEmoji.WARNING}">❌</tg-emoji> Промокод уже использован максимальное количество раз.', parse_mode="HTML")
        await state.clear()
        return
    if user_id in user_promo_attempts:
        del user_promo_attempts[user_id]
    if promo_type == 'percent':
        await message.answer(
            f'<tg-emoji emoji-id="{CustomEmoji.PREORDER_CHECK}">✅</tg-emoji> Промокод {code} активирован!\n'
            f'Скидка: {amount}% на следующую покупку!',
            parse_mode="HTML"
        )
        if not hasattr(bot, 'user_promos'):
            bot.user_promos = {}
        bot.user_promos[user_id] = {'code': code, 'discount': amount, 'type': 'percent'}
        await execute_query("UPDATE promo_codes SET used = used + 1 WHERE code = ?", (code,), commit=True)
    else:
        await update_balance(message.from_user.id, amount, "promo")
        await execute_query("UPDATE promo_codes SET used = used + 1 WHERE code = ?", (code,), commit=True)
        await message.answer(f'<tg-emoji emoji-id="{CustomEmoji.PREORDER_CHECK}">✅</tg-emoji> Промокод активирован! Зачислено {amount} USDT.', parse_mode="HTML")
    await state.clear()

# --- ПОПОЛНЕНИЕ БАЛАНСА ---
@dp.callback_query(F.data.in_({"deposit_provider_crypto", "deposit_provider_xrocket"}), ShopState.waiting_for_deposit_provider)
async def deposit_provider_cb(call: types.CallbackQuery, state: FSMContext):
    provider = "xrocket" if call.data == "deposit_provider_xrocket" else "crypto"
    provider_name = "@xRocket" if provider == "xrocket" else "@CryptoBot"
    await state.update_data(deposit_provider=provider)
    await state.set_state(ShopState.waiting_for_deposit_amount)
    await call.message.answer(
        f'<tg-emoji emoji-id="{CustomEmoji.DEPOSIT}">💰</tg-emoji> Оплата через {provider_name}\n\n'
        f'Введите сумму пополнения в USDT (минимум 1 USDT):',
        parse_mode="HTML"
    )
    await call.answer()

@dp.message(ShopState.waiting_for_deposit_amount)
async def deposit_amount(message: types.Message, state: FSMContext):
    try:
        amount = float(message.text.replace(',', '.'))
        if amount < 1 or amount > 10000:
            return await message.answer("❌ Сумма должна быть от 1 до 10000 USDT.")
        amount = round(amount, 2)
    except:
        return await message.answer("❌ Введите число.")

    data = await state.get_data()
    provider = data.get('deposit_provider', 'crypto')

    if provider == "xrocket":
        inv = await xrocket_create_invoice(
            amount=amount,
            description=f"Пополнение баланса пользователя {message.from_user.id}",
            expired_in=1800
        )
        if not inv.get('ok'):
            await message.answer(f"⚠ Ошибка API xRocket: {inv.get('description', 'Неизвестная ошибка')}")
            await state.clear()
            return
        invoice_id = inv['id']
        pay_url = inv['link']
        provider_emoji = CustomEmoji.XROCKET_PAY
    else:
        inv = await crypto_api("createInvoice", {
            "asset": "USDT", "amount": str(amount),
            "description": f"Пополнение баланса пользователя {message.from_user.id}", "expires_in": 1800
        })
        if not inv.get('ok'):
            await message.answer(f"⚠ Ошибка API: {inv.get('description', 'Неизвестная ошибка')}")
            await state.clear()
            return
        invoice_id = inv['result']['invoice_id']
        pay_url = inv['result']['pay_url']
        provider_emoji = CustomEmoji.CRYPTO_PAY

    pending_balance_payments[invoice_id] = {
        'user_id': message.from_user.id, 'amount': amount,
        'created_at': datetime.now(), 'provider': provider
    }
    kb = InlineKeyboardBuilder()
    kb.button(text="Оплатить", url=pay_url, icon_custom_emoji_id=provider_emoji)
    kb.adjust(1)
    msg = await message.answer(
        f'<tg-emoji emoji-id="{CustomEmoji.DEPOSIT}">💰</tg-emoji> Пополнение баланса\nСумма: {amount} USDT\n\nНажмите кнопку ниже для оплаты:',
        reply_markup=kb.as_markup(), parse_mode="HTML"
    )
    pending_balance_payments[invoice_id]['msg'] = msg
    asyncio.create_task(check_deposit_payment(invoice_id, message.from_user.id, amount, msg, provider))
    await state.clear()

# --- КОМАНДЫ ---
@dp.message(CommandStart(deep_link=True))
async def cmd_start_deep(message: types.Message):
    args = message.text.split()
    ref_id = None
    if len(args) > 1 and args[1].startswith('ref_'):
        try:
            ref_id = int(args[1].split('_')[1])
        except:
            pass
    await handle_start(message, ref_id)

@dp.message(Command("start"))
async def cmd_start_plain(message: types.Message):
    await handle_start(message, None)

async def handle_start(message: types.Message, referrer_id: int = None):
    user_id = message.from_user.id
    username = message.from_user.username or ""
    existing = await fetchone("SELECT accepted FROM users WHERE id = ?", (user_id,))
    if not existing:
        await save_user(username, user_id, referrer_id)
        accepted = 0
    else:
        await execute_query("UPDATE users SET username = ? WHERE id = ?", (username, user_id), commit=True)
        accepted = existing[0]
    if accepted == 0:
        accept_kb = InlineKeyboardBuilder()
        accept_kb.button(text="Да, я ознакомился", callback_data="accept_agreement", icon_custom_emoji_id=CustomEmoji.ACCEPT)
        await message.answer(
            f"👋 Добро пожаловать в EleghantShop!\n\nЧтобы продолжить, примите {hlink('Условия пользования сервиса', AGREEMENT_URL)}.",
            reply_markup=accept_kb.as_markup(), parse_mode="HTML", disable_web_page_preview=True
        )
    else:
        await show_main_menu(message)

@dp.callback_query(F.data == "accept_agreement")
async def accept_agreement_callback(call: types.CallbackQuery):
    await execute_query("UPDATE users SET accepted = 1 WHERE id = ?", (call.from_user.id,), commit=True)
    await call.answer("✅ Соглашение принято!")
    await call.message.delete()
    await show_main_menu(call.message)

async def show_main_menu(message: types.Message):
    caption_text = (
        "<b>"
        f'<tg-emoji emoji-id="{CustomEmoji.DIAMOND}">💎</tg-emoji> Главное меню EleghantShop. Лучший магазин в своем направлении\n\n'
        f'<tg-emoji emoji-id="{CustomEmoji.PIN}">📌</tg-emoji> Кнопки ниже помогают в навигации по магазину'
        "</b>"
    )
    await send_with_image(message, 'EleghantShopIcon', caption_text, main_keyboard())

# ═══════════════════════════════════════════════════════════════════════════════
# АДМИН ПАНЕЛЬ
# ═══════════════════════════════════════════════════════════════════════════════

def build_admin_keyboard() -> InlineKeyboardMarkup:
    status_btn_text = "🔴 Выключить тех. работы" if MAINTENANCE_MODE else "🟢 Включить тех. работы"
    kb = InlineKeyboardBuilder()
    kb.button(text=status_btn_text, callback_data="admin_toggle_maintenance")
    kb.button(text="📢 Рассылка", callback_data="admin_broadcast")
    kb.button(text="📢 Рассылка с картинкой", callback_data="admin_broadcast_image")
    kb.button(text="💰 Выдать баланс", callback_data="admin_give_balance")
    kb.button(text="📦 Добавить товар", callback_data="admin_add_stock")
    kb.button(text="📄 Загрузить товары из .txt", callback_data="admin_add_stock_txt")
    kb.button(text="🎫 Создать промокод", callback_data="admin_create_promo")
    kb.button(text="💰 Изменить цену категории", callback_data="admin_change_price")
    kb.button(text="🕞 Предзаказы", callback_data="admin_preorders")
    kb.button(text="💸 Заявки на вывод", callback_data="admin_withdraws")
    kb.adjust(1)
    return kb.as_markup()

@dp.message(Command("admintools"))
async def admin_tools(message: types.Message):
    if message.from_user.id != ADMIN_ID:
        return
    status_text = "🔴 Тех. работы ВКЛЮЧЕНЫ" if MAINTENANCE_MODE else "🟢 Бот работает в штатном режиме"
    await message.answer(
        f"🔧 <b>Панель администратора</b>\n\nСтатус: {status_text}\n\nВыберите действие:",
        reply_markup=build_admin_keyboard(),
        parse_mode="HTML"
    )

@dp.callback_query(F.data == "admin_toggle_maintenance")
async def admin_toggle_maintenance(call: types.CallbackQuery):
    if call.from_user.id != ADMIN_ID:
        return
    global MAINTENANCE_MODE
    MAINTENANCE_MODE = not MAINTENANCE_MODE
    if MAINTENANCE_MODE:
        status_text = "🔴 Тех. работы <b>ВКЛЮЧЕНЫ</b>\n\nПользователи видят сообщение о тех. работах."
        logger.info(f"Admin {call.from_user.id} ENABLED maintenance mode")
    else:
        status_text = "🟢 Бот <b>работает в штатном режиме</b>\n\nВсе пользователи имеют доступ."
        logger.info(f"Admin {call.from_user.id} DISABLED maintenance mode")
    try:
        await call.message.edit_text(
            f"🔧 <b>Панель администратора</b>\n\nСтатус: {status_text}\n\nВыберите действие:",
            reply_markup=build_admin_keyboard(),
            parse_mode="HTML"
        )
    except Exception:
        await call.message.answer(
            f"🔧 <b>Панель администратора</b>\n\nСтатус: {status_text}\n\nВыберите действие:",
            reply_markup=build_admin_keyboard(),
            parse_mode="HTML"
        )
    await call.answer("✅ Статус изменён!")

# --- ЗАЯВКИ НА ВЫВОД В АДМИНКЕ ---
@dp.callback_query(F.data == "admin_withdraws")
async def admin_withdraws_cb(call: types.CallbackQuery):
    if call.from_user.id != ADMIN_ID:
        return
    requests = await fetchall(
        "SELECT id, user_id, username, amount, status, created_at FROM withdraw_requests "
        "WHERE status = 'pending' ORDER BY created_at ASC LIMIT 20"
    )
    if not requests:
        kb = InlineKeyboardBuilder()
        kb.button(text="🔙 Назад", callback_data="back_to_admin", icon_custom_emoji_id=CustomEmoji.BACK)
        try:
            await call.message.delete()
        except:
            pass
        await call.message.answer(
            "💸 <b>Заявки на вывод</b>\n\n📭 Активных заявок нет.",
            parse_mode="HTML",
            reply_markup=kb.as_markup()
        )
        await call.answer()
        return

    text = f'💸 <b>Активные заявки на вывод ({len(requests)}):</b>\n\n'
    for rid, uid, uname, amount, status, created in requests:
        u = f"@{uname}" if uname else f"ID:{uid}"
        text += f"<b>#{rid}</b> | {u} | <b>{amount} USDT</b> | {created[:16]}\n"

    kb = InlineKeyboardBuilder()
    for rid, uid, uname, amount, status, created in requests:
        kb.button(text=f"#{rid} — {amount} USDT", callback_data=f"admin_withdraw_detail_{rid}")
    kb.button(text="🔙 Назад", callback_data="back_to_admin", icon_custom_emoji_id=CustomEmoji.BACK)
    kb.adjust(1)

    try:
        await call.message.delete()
    except:
        pass
    await call.message.answer(text, parse_mode="HTML", reply_markup=kb.as_markup())
    await call.answer()

@dp.callback_query(F.data.startswith("admin_withdraw_detail_"))
async def admin_withdraw_detail_cb(call: types.CallbackQuery):
    if call.from_user.id != ADMIN_ID:
        return
    try:
        request_id = int(call.data.split("_")[3])
    except (IndexError, ValueError):
        await call.answer("❌ Ошибка")
        return
    request = await fetchone(
        "SELECT id, user_id, username, amount, status, created_at FROM withdraw_requests WHERE id = ?",
        (request_id,)
    )
    if not request:
        await call.answer("❌ Заявка не найдена", show_alert=True)
        return
    rid, uid, uname, amount, status, created = request
    u = f"@{uname}" if uname else f"ID:{uid}"
    text = (
        f'💸 <b>Заявка #{rid}</b>\n\n'
        f'👤 Пользователь: {u}\n'
        f'🆔 ID: <code>{uid}</code>\n'
        f'💰 Сумма: <b>{amount} USDT</b>\n'
        f'📅 Дата: {created[:16]}\n'
        f'📊 Статус: {status}'
    )
    kb = InlineKeyboardBuilder()
    kb.button(text="✅ Одобрить", callback_data=f"withdraw_approve_{rid}")
    kb.button(text="❌ Отклонить", callback_data=f"withdraw_reject_{rid}")
    kb.button(text="🔙 К списку заявок", callback_data="admin_withdraws")
    kb.adjust(2)
    await call.message.answer(text, parse_mode="HTML", reply_markup=kb.as_markup())
    await call.answer()

# ───────────────────────────────────────────────────────────────────────────────
# РАССЫЛКА
# ───────────────────────────────────────────────────────────────────────────────

BROADCAST_HELP = (
    "📢 <b>Рассылка</b>\n\n"
    "Напишите текст рассылки. Поддерживается <b>HTML-форматирование</b>:\n\n"
    "<b>Теги форматирования:</b>\n"
    "• <code>&lt;b&gt;жирный&lt;/b&gt;</code>\n"
    "• <code>&lt;i&gt;курсив&lt;/i&gt;</code>\n"
    "• <code>&lt;u&gt;подчёркнутый&lt;/u&gt;</code>\n"
    "• <code>&lt;s&gt;зачёркнутый&lt;/s&gt;</code>\n"
    "• <code>&lt;code&gt;моноширный&lt;/code&gt;</code>\n"
    "• <code>&lt;pre&gt;блок кода&lt;/pre&gt;</code>\n"
    "• <code>&lt;blockquote&gt;цитата&lt;/blockquote&gt;</code>\n\n"
    "<b>Премиум-эмодзи:</b>\n"
    "<code>&lt;tg-emoji emoji-id=\"ID\"&gt;🔥&lt;/tg-emoji&gt;</code>\n\n"
    "<b>Ссылки:</b>\n"
    "<code>&lt;a href=\"https://...\"&gt;текст&lt;/a&gt;</code>\n\n"
    "Просто отправьте текст с нужным оформлением:"
)

@dp.callback_query(F.data == "admin_broadcast")
async def admin_broadcast_start(call: types.CallbackQuery, state: FSMContext):
    if call.from_user.id != ADMIN_ID:
        return
    await state.update_data(broadcast_photo=None)
    await state.set_state(AdminState.broadcast_text)
    await call.message.edit_text(BROADCAST_HELP, parse_mode="HTML")
    await call.answer()

@dp.callback_query(F.data == "admin_broadcast_image")
async def admin_broadcast_image_start(call: types.CallbackQuery, state: FSMContext):
    if call.from_user.id != ADMIN_ID:
        return
    await state.set_state(AdminState.broadcast_with_image)
    await call.message.edit_text(
        "📢 <b>Рассылка с картинкой</b>\n\nСначала отправьте <b>фото</b> (как фото, не файл):",
        parse_mode="HTML"
    )
    await call.answer()

@dp.message(AdminState.broadcast_with_image)
async def admin_broadcast_image_get(message: types.Message, state: FSMContext):
    if message.from_user.id != ADMIN_ID:
        return
    if not message.photo:
        await message.answer("❌ Пожалуйста, отправьте фото (не файл).")
        return
    photo = message.photo[-1]
    await state.update_data(broadcast_photo=photo.file_id)
    await state.set_state(AdminState.broadcast_text)
    await message.answer(BROADCAST_HELP, parse_mode="HTML")

@dp.message(AdminState.broadcast_text)
async def admin_broadcast_send(message: types.Message, state: FSMContext):
    if message.from_user.id != ADMIN_ID:
        return
    text = message.html_text
    data = await state.get_data()
    photo_id = data.get('broadcast_photo')
    preview_kb = InlineKeyboardBuilder()
    preview_kb.button(text="✅ Отправить всем", callback_data="confirm_broadcast")
    preview_kb.button(text="❌ Отменить", callback_data="cancel_broadcast")
    preview_kb.adjust(2)
    await state.update_data(broadcast_text=text)
    preview_msg = "👁 <b>Предпросмотр рассылки:</b>\n\n"
    if photo_id:
        await message.answer_photo(
            photo=photo_id,
            caption=f"{preview_msg}{text}" if len(preview_msg + text) <= 1024 else text,
            parse_mode="HTML",
            reply_markup=preview_kb.as_markup()
        )
    else:
        await message.answer(
            f"{preview_msg}{text}",
            parse_mode="HTML",
            reply_markup=preview_kb.as_markup()
        )

@dp.callback_query(F.data == "confirm_broadcast")
async def confirm_broadcast_cb(call: types.CallbackQuery, state: FSMContext):
    if call.from_user.id != ADMIN_ID:
        return
    data = await state.get_data()
    text = data.get('broadcast_text', '')
    photo_id = data.get('broadcast_photo')
    users = await fetchall("SELECT id FROM users WHERE accepted = 1")
    if not users:
        await call.message.edit_text("❌ Нет пользователей для рассылки.")
        await state.clear()
        return
    status_msg = await call.message.answer(f"⏳ Начинаю рассылку {len(users)} пользователям...")
    sent = 0
    failed = 0
    for idx, (user_id,) in enumerate(users):
        try:
            if photo_id:
                await bot.send_photo(user_id, photo=photo_id, caption=text, parse_mode="HTML")
            else:
                await bot.send_message(user_id, text, parse_mode="HTML")
            sent += 1
            if idx > 0 and idx % 100 == 0:
                await status_msg.edit_text(f"📊 Прогресс: {idx}/{len(users)}\n✅ Отправлено: {sent}\n❌ Ошибок: {failed}")
            await asyncio.sleep(0.05)
        except Exception as e:
            failed += 1
            logger.error(f"Ошибка отправки пользователю {user_id}: {e}")
    await status_msg.edit_text(f"✅ Рассылка завершена.\nОтправлено: {sent}\nОшибок: {failed}")
    await state.clear()
    await call.answer()

@dp.callback_query(F.data == "cancel_broadcast")
async def cancel_broadcast_cb(call: types.CallbackQuery, state: FSMContext):
    if call.from_user.id != ADMIN_ID:
        return
    await state.clear()
    await call.message.edit_text("❌ Рассылка отменена.")
    await call.answer()

# ───────────────────────────────────────────────────────────────────────────────
# ЗАГРУЗКА ТОВАРОВ ЧЕРЕЗ .TXT
# ───────────────────────────────────────────────────────────────────────────────

@dp.callback_query(F.data == "admin_add_stock_txt")
async def admin_add_stock_txt_start(call: types.CallbackQuery, state: FSMContext):
    if call.from_user.id != ADMIN_ID:
        return
    categories = await fetchall("SELECT id, name FROM categories")
    if not categories:
        await call.message.edit_text("❌ Нет категорий.")
        return
    kb = InlineKeyboardBuilder()
    for cat_id, name in categories:
        kb.button(text=f"[{cat_id}] {name}", callback_data=f"txt_cat_{cat_id}")
    kb.adjust(1)
    await call.message.edit_text(
        "📄 <b>Загрузка товаров из .txt</b>\n\nВыберите категорию:",
        reply_markup=kb.as_markup(), parse_mode="HTML"
    )
    await state.set_state(AdminState.add_stock_txt_cat_id)
    await call.answer()

@dp.callback_query(F.data.startswith("txt_cat_"), AdminState.add_stock_txt_cat_id)
async def admin_add_stock_txt_cat(call: types.CallbackQuery, state: FSMContext):
    if call.from_user.id != ADMIN_ID:
        return
    try:
        cat_id = int(call.data.split("_")[2])
    except:
        await call.answer("❌ Ошибка")
        return
    cat = await fetchone("SELECT id, name FROM categories WHERE id = ?", (cat_id,))
    if not cat:
        await call.answer("❌ Категория не найдена")
        return
    await state.update_data(txt_cat_id=cat_id, txt_cat_name=cat[1])
    await state.set_state(AdminState.add_stock_txt_file)
    await call.message.edit_text(
        f"📄 <b>Категория: {cat[1]}</b>\n\n"
        f"Отправьте .txt файл, где <b>каждая строка — один товар</b>.\n\n"
        f"<i>Пустые строки будут пропущены автоматически.</i>",
        parse_mode="HTML"
    )
    await call.answer()

@dp.message(AdminState.add_stock_txt_file)
async def admin_add_stock_txt_file(message: types.Message, state: FSMContext):
    if message.from_user.id != ADMIN_ID:
        return
    if not message.document:
        await message.answer("❌ Пожалуйста, отправьте .txt файл документом.")
        return
    doc = message.document
    if not doc.file_name or not doc.file_name.lower().endswith('.txt'):
        await message.answer("❌ Файл должен быть в формате .txt")
        return
    if doc.file_size and doc.file_size > 5 * 1024 * 1024:
        await message.answer("❌ Файл слишком большой (максимум 5 МБ).")
        return
    data = await state.get_data()
    cat_id = data['txt_cat_id']
    cat_name = data['txt_cat_name']
    status_msg = await message.answer("⏳ Читаю файл...")
    try:
        file = await bot.get_file(doc.file_id)
        file_path = file.file_path
        file_url = f"https://api.telegram.org/file/bot{BOT_TOKEN}/{file_path}"
        async with aiohttp.ClientSession() as session:
            async with session.get(file_url) as resp:
                raw_bytes = await resp.read()
        try:
            raw_text = raw_bytes.decode('utf-8')
        except UnicodeDecodeError:
            raw_text = raw_bytes.decode('cp1251', errors='replace')
        lines = raw_text.splitlines()
        items = [line.strip() for line in lines if line.strip()]
        if not items:
            await status_msg.edit_text("❌ Файл пустой или не содержит валидных строк.")
            await state.clear()
            return
        if len(items) > MAX_BULK_ADD:
            await status_msg.edit_text(
                f"❌ В файле {len(items)} строк, максимум {MAX_BULK_ADD}.\n"
                f"Разбейте файл на части."
            )
            await state.clear()
            return
        await status_msg.edit_text(f"⏳ Найдено {len(items)} товаров. Сохраняю в базу данных...")
        items_to_insert = [(cat_id, item) for item in items]
        await executemany("INSERT INTO inventory (cat_id, data) VALUES (?, ?)", items_to_insert)
        await status_msg.edit_text(
            f"✅ <b>Готово!</b>\n\n"
            f"📦 Категория: <b>{cat_name}</b>\n"
            f"➕ Добавлено товаров: <b>{len(items)} шт.</b>\n\n"
            f"<i>Первый товар: <code>{items[0][:60]}</code></i>",
            parse_mode="HTML"
        )
        logger.info(f"Admin {message.from_user.id} uploaded {len(items)} items to category {cat_id} via txt")
    except Exception as e:
        logger.error(f"Ошибка при загрузке txt файла: {e}")
        await status_msg.edit_text(f"❌ Ошибка при обработке файла: {e}")
    await state.clear()

# ───────────────────────────────────────────────────────────────────────────────
# ПРОМОКОДЫ
# ───────────────────────────────────────────────────────────────────────────────

@dp.callback_query(F.data == "admin_create_promo")
async def admin_create_promo_start(call: types.CallbackQuery, state: FSMContext):
    if call.from_user.id != ADMIN_ID:
        return
    kb = InlineKeyboardBuilder()
    kb.button(text="💰 Фиксированная сумма (USDT)", callback_data="promo_type_fixed")
    kb.button(text="📊 Процентная скидка (%)", callback_data="promo_type_percent")
    kb.adjust(1)
    await call.message.edit_text(
        "🎫 <b>Создание промокода</b>\n\nВыберите тип промокода:",
        reply_markup=kb.as_markup(), parse_mode="HTML"
    )
    await state.set_state(AdminState.create_promo_type)
    await call.answer()

@dp.callback_query(F.data.startswith("promo_type_"))
async def admin_create_promo_type(call: types.CallbackQuery, state: FSMContext):
    if call.from_user.id != ADMIN_ID:
        return
    promo_type = call.data.split("_")[2]
    await state.update_data(promo_type=promo_type)
    await state.set_state(AdminState.create_promo_code)
    type_text = "фиксированную сумму в USDT" if promo_type == "fixed" else "процент скидки (1–100)"
    await call.message.edit_text(f"🎫 Введите код промокода (буквы и цифры):\n\nТип: {type_text}")
    await call.answer()

@dp.message(AdminState.create_promo_code)
async def admin_create_promo_code(message: types.Message, state: FSMContext):
    if message.from_user.id != ADMIN_ID:
        return
    code = message.text.strip().upper()
    if not code.replace('_', '').replace('-', '').isalnum():
        await message.answer("❌ Код может содержать только буквы, цифры, _ и -")
        return
    existing = await fetchone("SELECT code FROM promo_codes WHERE code = ?", (code,))
    if existing:
        await message.answer("❌ Промокод с таким кодом уже существует.")
        return
    await state.update_data(code=code)
    data = await state.get_data()
    promo_type = data.get('promo_type', 'fixed')
    await state.set_state(AdminState.create_promo_value)
    if promo_type == 'fixed':
        await message.answer("🎫 Введите сумму начисления (USDT):\nПример: 10.5")
    else:
        await message.answer("🎫 Введите процент скидки (1–100):\nПример: 15")

@dp.message(AdminState.create_promo_value)
async def admin_create_promo_value(message: types.Message, state: FSMContext):
    if message.from_user.id != ADMIN_ID:
        return
    data = await state.get_data()
    promo_type = data.get('promo_type', 'fixed')
    try:
        if promo_type == 'fixed':
            value = round(float(message.text.replace(',', '.')), 2)
            if value <= 0:
                raise ValueError
            value_text = f"{value} USDT"
        else:
            value = round(float(message.text.replace(',', '.')), 1)
            if value <= 0 or value > 100:
                await message.answer("❌ Процент должен быть от 1 до 100.")
                return
            value_text = f"{value}%"
    except:
        await message.answer("❌ Введите корректное число.")
        return
    await state.update_data(promo_value=value)
    await state.set_state(AdminState.create_promo_limit)
    await message.answer(f"🎫 Введите максимальное количество использований:\n\nЗначение: {value_text}")

@dp.message(AdminState.create_promo_limit)
async def admin_create_promo_limit(message: types.Message, state: FSMContext):
    if message.from_user.id != ADMIN_ID:
        return
    try:
        limit = int(message.text)
        if limit <= 0:
            raise ValueError
    except:
        await message.answer("❌ Введите положительное целое число.")
        return
    data = await state.get_data()
    code = data['code']
    promo_type = data['promo_type']
    value = data['promo_value']
    await execute_query(
        "INSERT INTO promo_codes (code, amount, promo_type, max_uses) VALUES (?, ?, ?, ?)",
        (code, value, promo_type, limit), commit=True
    )
    type_text = "сумму" if promo_type == 'fixed' else "скидку"
    value_text = f"{value} USDT" if promo_type == 'fixed' else f"{value}%"
    await message.answer(
        f"✅ <b>Промокод создан!</b>\n\n"
        f"📝 Код: <code>{code}</code>\n"
        f"🎯 Тип: {type_text}\n"
        f"💰 Значение: {value_text}\n"
        f"📊 Лимит: {limit}",
        parse_mode="HTML"
    )
    await state.clear()

# ───────────────────────────────────────────────────────────────────────────────
# ВЫДАЧА БАЛАНСА
# ───────────────────────────────────────────────────────────────────────────────

@dp.callback_query(F.data == "admin_give_balance")
async def admin_give_balance_start(call: types.CallbackQuery, state: FSMContext):
    if call.from_user.id != ADMIN_ID:
        return
    await state.set_state(AdminState.give_balance_user_id)
    await call.message.edit_text("💰 Введите ID пользователя:")
    await call.answer()

@dp.message(AdminState.give_balance_user_id)
async def admin_give_balance_user(message: types.Message, state: FSMContext):
    if message.from_user.id != ADMIN_ID:
        return
    try:
        user_id = int(message.text)
    except:
        await message.answer("❌ Введите число.")
        return
    user_exists = await fetchone("SELECT id FROM users WHERE id = ?", (user_id,))
    if not user_exists:
        await message.answer("❌ Пользователь не найден.")
        await state.clear()
        return
    await state.update_data(target_user_id=user_id)
    await state.set_state(AdminState.give_balance_amount)
    await message.answer("💰 Введите сумму (может быть отрицательной для списания):")

@dp.message(AdminState.give_balance_amount)
async def admin_give_balance_amount(message: types.Message, state: FSMContext):
    if message.from_user.id != ADMIN_ID:
        return
    try:
        amount = round(float(message.text.replace(',', '.')), 2)
    except:
        await message.answer("❌ Введите число.")
        return
    data = await state.get_data()
    user_id = data['target_user_id']
    await update_balance(user_id, amount, "admin_give", ADMIN_ID)
    await message.answer(f"✅ Баланс пользователя {user_id} изменён на {amount} USDT.")
    await state.clear()

# ───────────────────────────────────────────────────────────────────────────────
# ДОБАВЛЕНИЕ ТОВАРА (поштучно)
# ───────────────────────────────────────────────────────────────────────────────

@dp.callback_query(F.data == "admin_add_stock")
async def admin_add_stock_start(call: types.CallbackQuery, state: FSMContext):
    if call.from_user.id != ADMIN_ID:
        return
    await state.set_state(AdminState.add_stock_cat_id)
    await call.message.edit_text("📦 Введите ID категории:")
    await call.answer()

@dp.message(AdminState.add_stock_cat_id)
async def admin_add_stock_cat(message: types.Message, state: FSMContext):
    if message.from_user.id != ADMIN_ID:
        return
    try:
        cat_id = int(message.text)
    except:
        await message.answer("❌ Введите число.")
        return
    cat = await fetchone("SELECT id, name FROM categories WHERE id = ?", (cat_id,))
    if not cat:
        await message.answer("❌ Категория не найдена.")
        await state.clear()
        return
    await state.update_data(cat_id=cat_id, cat_name=cat[1])
    await state.set_state(AdminState.add_stock_count)
    await message.answer(
        f"📦 <b>Категория: {cat[1]}</b>\n\nСколько товаров хотите добавить? (1–{MAX_BULK_ADD})",
        parse_mode="HTML"
    )

@dp.message(AdminState.add_stock_count)
async def admin_add_stock_count(message: types.Message, state: FSMContext):
    if message.from_user.id != ADMIN_ID:
        return
    try:
        count = int(message.text)
        if count < 1 or count > MAX_BULK_ADD:
            await message.answer(f"❌ Введите число от 1 до {MAX_BULK_ADD}.")
            return
    except:
        await message.answer("❌ Введите число.")
        return
    await state.update_data(total_count=count, current_index=0, items=[])
    await state.set_state(AdminState.add_stock_data)
    await message.answer(
        f"📦 Товар #1 из {count}\n\nВведите данные товара:",
        parse_mode="HTML"
    )

@dp.message(AdminState.add_stock_data)
async def admin_add_stock_data(message: types.Message, state: FSMContext):
    if message.from_user.id != ADMIN_ID:
        return
    data = await state.get_data()
    cat_id = data['cat_id']
    total_count = data['total_count']
    current_index = data.get('current_index', 0)
    items = data.get('items', [])
    items.append(message.text)
    current_index += 1
    if current_index < total_count:
        await state.update_data(current_index=current_index, items=items)
        await message.answer(f"✅ Товар #{current_index} добавлен!\n\nТовар #{current_index + 1} из {total_count}\nВведите данные:")
    else:
        await message.answer(f"⏳ Сохраняю {total_count} товаров...")
        items_to_insert = [(cat_id, item) for item in items]
        await executemany("INSERT INTO inventory (cat_id, data) VALUES (?, ?)", items_to_insert)
        await message.answer(
            f"✅ <b>Готово!</b>\n\nДобавлено: {total_count} шт.\nКатегория: {data.get('cat_name', str(cat_id))}",
            parse_mode="HTML"
        )
        logger.info(f"Admin added {total_count} items to category {cat_id}")
        await state.clear()

# ───────────────────────────────────────────────────────────────────────────────
# ИЗМЕНЕНИЕ ЦЕНЫ
# ───────────────────────────────────────────────────────────────────────────────

@dp.callback_query(F.data == "admin_change_price")
async def admin_change_price_start(call: types.CallbackQuery, state: FSMContext):
    if call.from_user.id != ADMIN_ID:
        return
    categories = await fetchall("SELECT id, name FROM categories")
    if not categories:
        await call.message.edit_text("❌ Нет категорий.")
        return
    kb = InlineKeyboardBuilder()
    for cat_id, name in categories:
        kb.button(text=name, callback_data=f"change_price_cat_{cat_id}")
    kb.adjust(1)
    await call.message.edit_text("💰 Выберите категорию:", reply_markup=kb.as_markup())
    await call.answer()

@dp.callback_query(F.data.startswith("change_price_cat_"))
async def admin_change_price_cat(call: types.CallbackQuery, state: FSMContext):
    if call.from_user.id != ADMIN_ID:
        return
    try:
        cat_id = int(call.data.split("_")[3])
    except:
        await call.answer("❌ Ошибка")
        return
    await state.update_data(change_cat_id=cat_id)
    await state.set_state(AdminState.change_price_value)
    await call.message.answer("💰 Введите новую цену в USDT:")
    await call.answer()

@dp.message(AdminState.change_price_value)
async def admin_change_price_value(message: types.Message, state: FSMContext):
    if message.from_user.id != ADMIN_ID:
        return
    try:
        new_price = float(message.text.replace(',', '.'))
        if new_price <= 0:
            raise ValueError
    except:
        await message.answer("❌ Введите положительное число.")
        return
    data = await state.get_data()
    cat_id = data['change_cat_id']
    await execute_query("UPDATE categories SET price = ? WHERE id = ?", (new_price, cat_id), commit=True)
    await message.answer(f"✅ Цена обновлена на {new_price} USDT.")
    await state.clear()

# ───────────────────────────────────────────────────────────────────────────────
# ПРЕДЗАКАЗЫ (АДМИН)
# ───────────────────────────────────────────────────────────────────────────────

@dp.callback_query(F.data == "admin_preorders")
async def admin_preorders_cb(call: types.CallbackQuery):
    if call.from_user.id != ADMIN_ID:
        return
    preorders = await fetchall("""
        SELECT p.id, p.user_id, u.username, c.name, p.quantity, p.total, p.created_at, p.paid_at, p.status
        FROM preorders p
        JOIN categories c ON p.cat_id = c.id
        LEFT JOIN users u ON p.user_id = u.id
        ORDER BY CASE p.status WHEN 'paid' THEN 1 WHEN 'pending' THEN 2 ELSE 3 END, p.created_at DESC
        LIMIT 50
    """)
    if not preorders:
        await call.message.edit_text("📦 Нет предзаказов.")
        return
    paid = [p for p in preorders if p[8] == 'paid']
    pending = [p for p in preorders if p[8] == 'pending']
    other = [p for p in preorders if p[8] not in ('paid', 'pending')]
    text = f'<tg-emoji emoji-id="{CustomEmoji.PREORDER_CLOCK}">🕞</tg-emoji> <b>Управление предзаказами</b>\n\n'
    if paid:
        text += f'✅ <b>Оплаченные (ожидают выдачи):</b>\n'
        for pid, uid, username, cat_name, qty, total, created, paid_at, status in paid[:10]:
            u = f"@{username}" if username else f"ID:{uid}"
            text += f"   #{pid} | {u} | {cat_name} x{qty} | {total} USDT\n"
        if len(paid) > 10:
            text += f"   ... и еще {len(paid) - 10}\n"
        text += "\n"
    if pending:
        text += f'⏳ <b>Ожидают оплаты:</b>\n'
        for pid, uid, username, cat_name, qty, total, created, paid_at, status in pending[:5]:
            u = f"@{username}" if username else f"ID:{uid}"
            text += f"   #{pid} | {u} | {cat_name} x{qty} | {total} USDT\n"
        if len(pending) > 5:
            text += f"   ... и еще {len(pending) - 5}\n"
        text += "\n"
    if other:
        text += f'❌ <b>Просроченные/Завершенные:</b> {len(other)}\n\n'
    text += f'📊 <b>Итого:</b> всего {len(preorders)}, ждут выдачи: {len(paid)}, ждут оплаты: {len(pending)}'
    kb = InlineKeyboardBuilder()
    if paid:
        kb.button(text="✅ Выдать предзаказы", callback_data="admin_complete_preorders", icon_custom_emoji_id=CustomEmoji.CHECKMARK)
    kb.button(text="🔄 Обновить", callback_data="admin_preorders")
    kb.button(text="🔙 Назад", callback_data="back_to_admin", icon_custom_emoji_id=CustomEmoji.BACK)
    kb.adjust(1)
    try:
        await call.message.delete()
    except:
        pass
    await call.message.answer(text, reply_markup=kb.as_markup(), parse_mode="HTML")
    await call.answer()

@dp.callback_query(F.data == "admin_complete_preorders")
async def admin_complete_preorders_cb(call: types.CallbackQuery):
    if call.from_user.id != ADMIN_ID:
        return
    preorders = await fetchall("""
        SELECT p.id, p.user_id, p.cat_id, p.quantity, p.total, c.name, u.username
        FROM preorders p
        JOIN categories c ON p.cat_id = c.id
        LEFT JOIN users u ON p.user_id = u.id
        WHERE p.status = 'paid'
        ORDER BY p.created_at ASC
    """)
    if not preorders:
        await call.answer("📦 Нет оплаченных предзаказов", show_alert=True)
        return
    text = '✅ <b>Оплаченные предзаказы:</b>\n\n'
    for pid, uid, cat_id, qty, total, cat_name, username in preorders[:20]:
        u = f"@{username}" if username else f"ID:{uid}"
        text += f"<b>#{pid}</b> - {cat_name} x{qty} ({total} USDT) | {u}\n"
    if len(preorders) > 20:
        text += f"\n... и еще {len(preorders) - 20}\n"
    text += "\nИспользуйте <code>/complete_preorder &lt;id&gt;</code> для выдачи."
    kb = InlineKeyboardBuilder()
    kb.button(text="🔙 Назад", callback_data="admin_preorders", icon_custom_emoji_id=CustomEmoji.BACK)
    try:
        await call.message.delete()
    except:
        pass
    await call.message.answer(text, reply_markup=kb.as_markup(), parse_mode="HTML")
    await call.answer()

@dp.message(Command("complete_preorder"))
async def cmd_complete_preorder(message: types.Message):
    if message.from_user.id != ADMIN_ID:
        return
    args = message.text.split()
    if len(args) < 2:
        await message.answer("❌ Использование: /complete_preorder <preorder_id>")
        return
    try:
        preorder_id = int(args[1])
    except ValueError:
        await message.answer("❌ Введите число.")
        return
    preorder = await fetchone("""
        SELECT p.user_id, p.cat_id, p.quantity, p.total, c.name, p.status
        FROM preorders p JOIN categories c ON p.cat_id = c.id WHERE p.id = ?
    """, (preorder_id,))
    if not preorder:
        await message.answer(f"❌ Предзаказ #{preorder_id} не найден.")
        return
    user_id, cat_id, quantity, total, cat_name, status = preorder
    if status != 'paid':
        await message.answer(f"❌ Статус предзаказа: '{status}'. Выдать можно только оплаченные.")
        return
    stock = await fetchone("SELECT COUNT(*) FROM inventory WHERE cat_id = ?", (cat_id,))
    stock_count = stock[0] if stock else 0
    if stock_count < quantity:
        await message.answer(f"❌ Товара не хватает! В наличии: {stock_count}, нужно: {quantity}")
        return
    items = await buy_items_with_transaction(cat_id, quantity, user_id, 0)
    if not items:
        await message.answer("❌ Ошибка при выдаче товара")
        return
    await execute_query("UPDATE preorders SET status = 'completed' WHERE id = ?", (preorder_id,), commit=True)
    res_text = (
        f'✅ <b>Ваш предзаказ выполнен!</b>\n\n'
        f'📦 Товар: {cat_name}\n'
        f'🔢 Количество: {quantity} шт.\n\n'
        f'🎁 Данные товара:\n'
    )
    for _, i_data in items:
        res_text += f"• {hcode(i_data)}\n"
    try:
        await bot.send_message(user_id, res_text, parse_mode="HTML")
        await message.answer(f"✅ Предзаказ #{preorder_id} выдан!")
    except Exception as e:
        await message.answer(f"⚠️ Выдан, но не удалось отправить сообщение: {e}")
    logger.info(f"Admin {message.from_user.id} completed preorder #{preorder_id} for user {user_id}")

# --- КОМАНДЫ СТАТИСТИКИ ---
@dp.message(Command("userstats"))
async def show_user_stats(message: types.Message):
    if message.from_user.id != ADMIN_ID:
        return
    try:
        total_users = await fetchone("SELECT COUNT(*) FROM users WHERE accepted = 1")
        total_purchases = await fetchone("SELECT SUM(total) FROM users")
        total_balance = await fetchone("SELECT SUM(balance) FROM balances")
        total_preorders = await fetchone("SELECT COUNT(*) FROM preorders")
        paid_preorders = await fetchone("SELECT COUNT(*) FROM preorders WHERE status = 'paid'")
        completed_preorders = await fetchone("SELECT COUNT(*) FROM preorders WHERE status = 'completed'")
        pending_withdraws = await fetchone("SELECT COUNT(*) FROM withdraw_requests WHERE status = 'pending'")
        total_withdrawn = await fetchone("SELECT SUM(amount) FROM withdraw_requests WHERE status = 'approved'")
        text = (
            f'📊 <b>Статистика бота</b>\n\n'
            f"👥 Пользователей: {total_users[0] if total_users else 0}\n"
            f"🛒 Всего покупок: {total_purchases[0] if total_purchases else 0}\n"
            f"💰 Баланс пользователей: {total_balance[0] if total_balance else 0} USDT\n\n"
            f"🕞 Всего предзаказов: {total_preorders[0] if total_preorders else 0}\n"
            f"✅ Оплаченных: {paid_preorders[0] if paid_preorders else 0}\n"
            f"🎁 Выполненных: {completed_preorders[0] if completed_preorders else 0}\n\n"
            f"💸 Заявок на вывод (pending): {pending_withdraws[0] if pending_withdraws else 0}\n"
            f"💸 Выведено всего: {total_withdrawn[0] if total_withdrawn and total_withdrawn[0] else 0} USDT"
        )
        await message.answer(text, parse_mode="HTML")
    except Exception as e:
        await message.answer(f"❌ Ошибка: {e}")

@dp.message(Command("userinfo"))
async def show_user_info(message: types.Message):
    if message.from_user.id != ADMIN_ID:
        return
    args = message.text.split()
    if len(args) < 2:
        await message.answer("❌ Использование: /userinfo <user_id>")
        return
    try:
        target_user_id = int(args[1])
    except ValueError:
        await message.answer("❌ Введите число.")
        return
    try:
        user_data = await fetchone("SELECT id, username, total, referrer_id FROM users WHERE id = ?", (target_user_id,))
        balance = await get_balance(target_user_id)
        preorders = await fetchall(
            "SELECT id, cat_id, quantity, total, status FROM preorders WHERE user_id = ? ORDER BY id DESC",
            (target_user_id,)
        )
        withdraws = await fetchall(
            "SELECT id, amount, status, created_at FROM withdraw_requests WHERE user_id = ? ORDER BY id DESC LIMIT 5",
            (target_user_id,)
        )
        try:
            user = await bot.get_chat(target_user_id)
            tg_info = (
                f"🆔 ID: {user.id}\n"
                f"📛 Имя: {user.first_name or '—'}\n"
                f"🏷 Фамилия: {user.last_name or '—'}\n"
                f"🔗 Username: @{user.username if user.username else '—'}\n"
                f"⭐ Премиум: {'Да' if getattr(user, 'is_premium', False) else 'Нет'}\n\n"
            )
        except Exception as e:
            tg_info = f"⚠️ Не удалось получить данные Telegram: {e}\n\n"
        bot_info = (
            f"💰 Баланс: {balance} USDT\n"
            f"🛒 Покупок: {user_data[2] if user_data else 0}\n"
            f"🔗 Реферер: {user_data[3] if user_data and user_data[3] else 'Нет'}\n\n"
            f"🕞 <b>Предзаказы:</b>\n"
        )
        if preorders:
            for pid, cat_id, qty, total, status in preorders[:10]:
                cat = await fetchone("SELECT name FROM categories WHERE id = ?", (cat_id,))
                cat_name = cat[0] if cat else "Неизвестно"
                emoji = {"pending": "⏳", "paid": "✅", "expired": "❌", "completed": "🎁"}.get(status, "❓")
                bot_info += f"   {emoji} #{pid} - {cat_name} x{qty} ({total} USDT)\n"
        else:
            bot_info += "   Нет предзаказов\n"
        if withdraws:
            bot_info += "\n💸 <b>Заявки на вывод:</b>\n"
            for wid, wamount, wstatus, wcreated in withdraws:
                emoji = {"pending": "⏳", "approved": "✅", "rejected": "❌"}.get(wstatus, "❓")
                bot_info += f"   {emoji} #{wid} — {wamount} USDT ({wcreated[:10]})\n"
        await message.answer(f"<b>Информация о пользователе</b>\n\n{tg_info}{bot_info}", parse_mode="HTML")
    except Exception as e:
        await message.answer(f"❌ Ошибка: {e}")

@dp.message(Command("cancel"))
async def cmd_cancel(message: types.Message, state: FSMContext):
    current_state = await state.get_state()
    if current_state:
        await state.clear()
        await message.answer("✅ Действие отменено.")
    else:
        await message.answer("❌ Нет активных действий.")

@dp.message(Command("mypreorders"))
async def cmd_my_preorders(message: types.Message):
    preorders = await fetchall(
        "SELECT p.id, c.name, p.quantity, p.total, p.created_at, p.paid_at, p.status "
        "FROM preorders p JOIN categories c ON p.cat_id = c.id "
        "WHERE p.user_id = ? ORDER BY p.created_at DESC",
        (message.from_user.id,)
    )
    if not preorders:
        await message.answer(f'📦 У вас нет предзаказов.')
        return
    text = '🕞 <b>Ваши предзаказы:</b>\n\n'
    for pid, cat_name, qty, total, created, paid_at, status in preorders:
        status_map = {
            "pending": ("⏳", "Ожидает оплаты"),
            "paid": ("✅", "Оплачен, ожидает выдачи"),
            "expired": ("❌", "Просрочен"),
            "completed": ("🎁", "Выполнен"),
        }
        se, st = status_map.get(status, ("❓", "Неизвестно"))
        text += f"{se} <b>#{pid}</b> - {cat_name}\n"
        text += f"   📦 {qty} шт. | 💰 {total} USDT\n"
        text += f"   📅 {created[:10] if created else '—'}\n"
        if paid_at:
            text += f"   💳 Оплачен: {paid_at[:10]}\n"
        text += f"   {se} {st}\n\n"
    await message.answer(text, parse_mode="HTML")

@dp.callback_query(F.data == "back_to_profile")
async def back_to_profile_cb(call: types.CallbackQuery):
    await show_profile_with_image(call.from_user.id, call.message)
    await call.answer()

@dp.callback_query(F.data == "back_to_admin")
async def back_to_admin_cb(call: types.CallbackQuery):
    if call.from_user.id != ADMIN_ID:
        return
    status_text = "🔴 Тех. работы ВКЛЮЧЕНЫ" if MAINTENANCE_MODE else "🟢 Бот работает в штатном режиме"
    try:
        await call.message.delete()
    except:
        pass
    await call.message.answer(
        f"🔧 <b>Панель администратора</b>\n\nСтатус: {status_text}\n\nВыберите действие:",
        reply_markup=build_admin_keyboard(),
        parse_mode="HTML"
    )
    await call.answer()

# --- ОБРАБОТЧИК ДЛЯ /addstock И /done (командная строка) ---
@dp.message(Command("addstock"))
async def cmd_add_stock(message: types.Message):
    if message.from_user.id != ADMIN_ID:
        return
    args = message.text.split()
    if len(args) < 3:
        await message.answer("❌ Использование: /addstock <cat_id> <количество>")
        return
    try:
        cat_id = int(args[1])
        count = int(args[2])
        if count < 1 or count > MAX_BULK_ADD:
            await message.answer(f"❌ Количество от 1 до {MAX_BULK_ADD}.")
            return
    except ValueError:
        await message.answer("❌ Неверный формат.")
        return
    cat = await fetchone("SELECT id, name FROM categories WHERE id = ?", (cat_id,))
    if not cat:
        await message.answer(f"❌ Категория {cat_id} не найдена.")
        return
    await message.answer(f"📦 <b>Категория: {cat[1]}</b>\n\nОтправляйте товары по одному.\nВведите /done для завершения.", parse_mode="HTML")
    if not hasattr(bot, 'pending_stock_add'):
        bot.pending_stock_add = {}
    bot.pending_stock_add[message.from_user.id] = {
        'cat_id': cat_id, 'cat_name': cat[1], 'total_count': count, 'items': [], 'current_index': 0
    }

@dp.message(Command("done"))
async def cmd_done_add_stock(message: types.Message):
    if message.from_user.id != ADMIN_ID:
        return
    if not hasattr(bot, 'pending_stock_add') or message.from_user.id not in bot.pending_stock_add:
        await message.answer("❌ Нет активного процесса. Используйте /addstock")
        return
    data = bot.pending_stock_add[message.from_user.id]
    cat_id = data['cat_id']
    items = data['items']
    if not items:
        await message.answer("❌ Не добавлено ни одного товара.")
        del bot.pending_stock_add[message.from_user.id]
        return
    await message.answer(f"⏳ Сохраняю {len(items)} товаров...")
    items_to_insert = [(cat_id, item) for item in items]
    await executemany("INSERT INTO inventory (cat_id, data) VALUES (?, ?)", items_to_insert)
    await message.answer(f"✅ Добавлено: {len(items)} шт. в категорию {data['cat_name']}", parse_mode="HTML")
    logger.info(f"Admin added {len(items)} items to category {cat_id}")
    del bot.pending_stock_add[message.from_user.id]

@dp.message()
async def handle_add_stock_items(message: types.Message):
    if message.from_user.id != ADMIN_ID:
        return
    if not hasattr(bot, 'pending_stock_add') or message.from_user.id not in bot.pending_stock_add:
        return
    if message.text and message.text.startswith('/'):
        return
    data = bot.pending_stock_add[message.from_user.id]
    items = data['items']
    total_count = data['total_count']
    items.append(message.text)
    bot.pending_stock_add[message.from_user.id]['items'] = items
    if len(items) < total_count:
        await message.answer(f"✅ #{len(items)} добавлен! Осталось: {total_count - len(items)}. Или /done для завершения.")
    else:
        await message.answer(f"✅ Все {len(items)} товаров получены. Введите /done для сохранения.")

# --- ЗАПУСК ---
async def main():
    logger.info("Starting bot...")
    try:
        await init_db()
        await setup_catalog()
        asyncio.create_task(cleanup_old_payments())
        if not hasattr(bot, 'user_promos'):
            bot.user_promos = {}
        await bot.set_my_commands([
            BotCommand(command="start", description="Запустить бота"),
            BotCommand(command="help", description="Помощь"),
            BotCommand(command="profile", description="Мой профиль"),
            BotCommand(command="deposit", description="Пополнить баланс"),
            BotCommand(command="cancel", description="Отменить действие"),
            BotCommand(command="admintools", description="Панель администратора"),
            BotCommand(command="userstats", description="Статистика бота (админ)"),
            BotCommand(command="userinfo", description="Информация о пользователе (админ)"),
            BotCommand(command="addstock", description="Добавить товар (админ)"),
            BotCommand(command="complete_preorder", description="Выдать предзаказ (админ)"),
            BotCommand(command="mypreorders", description="Мои предзаказы"),
            BotCommand(command="withdraws", description="Заявки на вывод (админ)"),
        ])
        await bot.delete_webhook(drop_pending_updates=True)
        logger.info("Bot started successfully!")
        await dp.start_polling(bot)
    except Exception as e:
        logger.error(f"Error in main: {e}")
        raise
    finally:
        logger.info("Shutting down...")
        await bot.session.close()
        await close_db()
        tasks = [t for t in asyncio.all_tasks() if t is not asyncio.current_task()]
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
        logger.info("Bot stopped")

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Bot stopped by user")
    except Exception as e:
        logger.error(f"Fatal error: {e}")