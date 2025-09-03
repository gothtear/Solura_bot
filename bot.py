import os
import asyncio
import random
from datetime import datetime, timedelta
from aiogram import Bot, Dispatcher, types
from aiogram.filters import Command
import asyncpg
import sys
import subprocess

# 📦 Автоматическая установка deepseek-sdk
try:
    from deepseek_sdk import DeepSeekClient
except ModuleNotFoundError:
    subprocess.check_call([sys.executable, "-m", "pip", "install", "deepseek-sdk"])
    from deepseek_sdk import DeepSeekClient

# 🔑 Загружаем секретные ключи из переменных окружения
BOT_TOKEN = os.getenv("BOT_TOKEN")
DB_URL = os.getenv("DB_URL") 
DEEPSEEK_API_KEY = os.getenv("DEEPSEEK_API_KEY")

# Инициализация бота и Dispatcher
bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()

# Инициализация DeepSeek
deepseek_client = DeepSeekClient(api_key=DEEPSEEK_API_KEY)

# Константы
FREE_MESSAGE_LIMIT = 10
TRIAL_DAYS = 1

# Глобальный пул базы
db_pool = None

async def create_db_pool():
    global db_pool
    if db_pool is None:
        try:
            db_pool = await asyncpg.create_pool(DB_URL)
            print("✅ Подключение к базе данных установлено")
        except Exception as e:
            print(f"❌ Ошибка подключения к базе: {e}")
            db_pool = None
    return db_pool

# -------------------- Команды --------------------

@dp.message(Command("start"))
async def cmd_start(message: types.Message):
    user_id = message.from_user.id
    user_name = message.from_user.first_name
    ref_code = message.text.split()[1] if len(message.text.split()) > 1 else None
    
    pool = await create_db_pool()
    if not pool:
        await message.answer("⚠️ Сервис временно недоступен. Попробуйте позже.")
        return
    
    try:
        async with pool.acquire() as conn:
            user = await conn.fetchrow("SELECT * FROM users WHERE user_id = $1", user_id)
            is_new_user = False
            if not user:
                pro_until = datetime.now() + timedelta(days=TRIAL_DAYS)
                await conn.execute(
                    "INSERT INTO users (user_id, is_pro, message_count, pro_until, ref_code) VALUES ($1, $2, $3, $4, $5)",
                    user_id, True, 0, pro_until, f"REF{user_id}{random.randint(100,999)}"
                )
                is_new_user = True
                print(f"✅ Новый пользователь: {user_id}")
            
            # Обработка рефералов
            if ref_code and ref_code.startswith('REF'):
                referrer = await conn.fetchrow("SELECT user_id FROM users WHERE ref_code = $1", ref_code)
                if referrer and referrer['user_id'] != user_id:
                    await conn.execute(
                        "UPDATE users SET message_count = message_count + 5 WHERE user_id = $1",
                        referrer['user_id']
                    )
                    await conn.execute(
                        "UPDATE users SET message_count = message_count + 3 WHERE user_id = $1",
                        user_id
                    )
            
            user_data = await conn.fetchrow("SELECT is_pro, message_count, pro_until FROM users WHERE user_id = $1", user_id)
        
        welcome_text = (
            f"Привет, {user_name}! 👋\n\n"
            "Я твой AI-психолог. Со мной можно говорить о чем угодно — я всегда выслушаю и поддержу.\n\n"
        )
        
        if is_new_user:
            welcome_text += f"🎁 <b>Тебе доступен пробный PRO-период на {TRIAL_DAYS} день!</b>\nПиши без ограничений!\n\n"
        else:
            messages_left = FREE_MESSAGE_LIMIT - user_data['message_count']
            if user_data['is_pro']:
                welcome_text += "💎 <b>У тебя PRO-аккаунт! Безлимитное общение!</b>\n\n"
            else:
                welcome_text += f"• Бесплатно: {messages_left}/{FREE_MESSAGE_LIMIT} сообщений сегодня\n"
        
        welcome_text += "• /ref - пригласить друга и получить бонус\n• /buy - оформить подписку PRO\n• /help - помощь\n\nПросто напиши мне о том, что тебя беспокоит..."
        await message.answer(welcome_text, parse_mode="HTML")
        
    except Exception as e:
        await message.answer("⚠️ Произошла ошибка. Попробуйте позже.")
        print(f"❌ Ошибка /start: {e}")

# -------------------- /ref --------------------
@dp.message(Command("ref"))
async def cmd_ref(message: types.Message):
    user_id = message.from_user.id
    pool = await create_db_pool()
    if not pool:
        await message.answer("⚠️ Сервис временно недоступен. Попробуйте позже.")
        return
    
    try:
        async with pool.acquire() as conn:
            user = await conn.fetchrow("SELECT ref_code FROM users WHERE user_id = $1", user_id)
            if user:
                ref_link = f"https://t.me/{(await bot.get_me()).username}?start={user['ref_code']}"
                ref_text = (
                    "🎯 <b>Пригласи друзей и получи бонусы!</b>\n\n"
                    f"Твоя реферальная ссылка:\n<code>{ref_link}</code>\n\n"
                    "За каждого друга:\n• Ты получаешь +5 сообщений\n• Друг получает +3 сообщения"
                )
                await message.answer(ref_text, parse_mode="HTML")
            else:
                await message.answer("⚠️ Сначала напишите /start")
    except Exception as e:
        await message.answer("⚠️ Произошла ошибка. Попробуйте позже.")
        print(f"❌ Ошибка /ref: {e}")

# -------------------- /help --------------------
@dp.message(Command("help"))
async def cmd_help(message: types.Message):
    help_text = (
        "🤖 <b>Помощь по боту</b>\n\n"
        f"• Бесплатно: {FREE_MESSAGE_LIMIT} сообщений в день\n"
        "• PRO: безлимитное общение\n\n"
        "Команды:\n• /start\n• /ref\n• /buy\n• /help\n\n"
        "<i>⚠️ Не заменяет терапию. Обратитесь к специалисту при необходимости.</i>"
    )
    await message.answer(help_text, parse_mode="HTML")

# -------------------- /buy --------------------
@dp.message(Command("buy"))
async def cmd_buy(message: types.Message):
    buy_text = (
        "🚀 <b>PRO-подписка</b>\n\n"
        "• Безлимитные сообщения\n• Приоритетная поддержка\n• Доступ к новым функциям\n\n"
        "💵 <b>Стоимость: 299₽/месяц</b>\n\n"
        "Для оплаты напиши @assistantai_gpt\nили перейди по ссылке: https://example.com/buy\n\n"
        "<i>Доступ активируется в течение 5-15 минут</i>"
    )
    await message.answer(buy_text, parse_mode="HTML")

# -------------------- Обработка всех сообщений --------------------
@dp.message()
async def handle_message(message: types.Message):
    user_id = message.from_user.id
    user_text = message.text
    if not user_text:
        return
    
    pool = await create_db_pool()
    if not pool:
        await message.answer("⚠️ Сервис временно недоступен. Попробуйте позже.")
        return
    
    try:
        async with pool.acquire() as conn:
            user = await conn.fetchrow("SELECT is_pro, message_count, pro_until FROM users WHERE user_id = $1", user_id)
            if not user:
                await message.answer("⚠️ Пожалуйста, сначала напишите /start")
                return
            
            # Проверка PRO-периода
            is_pro = user['is_pro']
            pro_until = user['pro_until']
            if pro_until and datetime.now() > pro_until:
                is_pro = False
                await conn.execute("UPDATE users SET is_pro = FALSE WHERE user_id = $1", user_id)
            
            # Проверка опасных тем
            danger_keywords = [
                'суицид', 'самоубийство', 'покончить с собой', 'убить себя',
                'suicide', 'harm myself', 'hurt myself', 'end my life',
                'не хочу жить', 'жить не хочется', 'свести счеты', 'повеситься',
                'порезы', 'резать себя'
            ]
            if any(k in user_text.lower() for k in danger_keywords):
                safety_response = (
                    "Я ценю, что делишься переживаниями. Твоя безопасность важна.\n\n"
                    "К сожалению, я не могу обсуждать такие темы — обратись к специалисту:\n"
                    "• <b>8-800-2000-122</b>\n• <b>112</b>\n• @qlindrovalobot"
                )
                await conn.execute(
                    "INSERT INTO messages (user_id, user_message, bot_response) VALUES ($1, $2, $3)",
                    user_id, user_text, "БЛОК: опасная тема"
                )
                await message.answer(safety_response, parse_mode="HTML")
                return
            
            # Проверка лимита
            if not is_pro and user['message_count'] >= FREE_MESSAGE_LIMIT:
                await message.answer(
                    f"❌ Лимит сообщений исчерпан ({FREE_MESSAGE_LIMIT})\nПерейдите на PRO или пригласите друга (/ref)",
                    parse_mode="HTML"
                )
                return
            
            # Обновляем счетчик
            if not is_pro:
                await conn.execute("UPDATE users SET message_count = message_count + 1 WHERE user_id = $1", user_id)
            
            await bot.send_chat_action(chat_id=user_id, action="typing")
            
            # Запрос к DeepSeek с таймаутом
            try:
                response = await asyncio.wait_for(
                    deepseek_client.chat.completions.create(
                        model="deepseek-chat",
                        messages=[{"role": "user", "content": user_text}],
                        max_tokens=500,
                        temperature=0.7
                    ),
                    timeout=10  # 10 секунд
                )
                ai_response = response.choices[0].message.content
            except Exception as e:
                print(f"❌ DeepSeek ошибка: {e}")
                ai_response = "Извините, произошла ошибка обработки. Попробуйте позже."
            
            await conn.execute(
                "INSERT INTO messages (user_id, user_message, bot_response) VALUES ($1, $2, $3)",
                user_id, user_text, ai_response
            )
            await message.answer(ai_response)
    
    except Exception as e:
        await message.answer("⚠️ Произошла непредвиденная ошибка. Попробуйте позже.")
        print(f"❌ Критическая ошибка: {e}")

# -------------------- Меню --------------------
async def set_bot_commands():
    await bot.set_my_commands([
        types.BotCommand(command="start", description="Начать общение"),
        types.BotCommand(command="ref", description="Пригласить друга (+5)"),
        types.BotCommand(command="buy", description="Купить PRO"),
        types.BotCommand(command="help", description="Помощь"),
    ])
    print("✅ Команды бота установлены")

# -------------------- Запуск --------------------
async def main():
    await create_db_pool()
    await set_bot_commands()
    print("✅ Бот запущен! Ожидаем сообщения...")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
