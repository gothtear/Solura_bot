import os
import asyncio
import random
from datetime import datetime, timedelta
from aiogram import Bot, Dispatcher, types
from aiogram.filters import Command
import asyncpg
from deepseek_sdk import DeepSeekClient


# Загружаем секретные ключи из переменных окружения
BOT_TOKEN = os.getenv("BOT_TOKEN")
DB_URL = os.getenv("DB_URL") 
DEEPSEEK_API_KEY = os.getenv("DEEPSEEK_API_KEY")

# Инициализируем бота и клиента DeepSeek
bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()
deepseek_client = DeepSeekClient(api_key=DEEPSEEK_API_KEY)

# Константы
FREE_MESSAGE_LIMIT = 10  # Увеличили до 10 сообщений
TRIAL_DAYS = 1  # Бесплатный пробный период PRO на 1 день

# Подключение к базе данных
async def create_db_pool():
    try:
        pool = await asyncpg.create_pool(DB_URL)
        print("✅ Подключение к базе данных установлено")
        return pool
    except Exception as e:
        print(f"❌ Ошибка подключения к базе: {e}")
        return None

# Команда /start
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
        async with pool.acquire() as connection:
            # Проверяем, есть ли пользователь в базе
            user = await connection.fetchrow(
                "SELECT * FROM users WHERE user_id = $1", user_id
            )
            
            is_new_user = False
            if not user:
                # Добавляем нового пользователя с пробным периодом
                pro_until = datetime.now() + timedelta(days=TRIAL_DAYS)
                await connection.execute(
                    "INSERT INTO users (user_id, is_pro, message_count, pro_until, ref_code) VALUES ($1, $2, $3, $4, $5)",
                    user_id, True, 0, pro_until, f"REF{user_id}{random.randint(100,999)}"
                )
                is_new_user = True
                print(f"✅ Новый пользователь добавлен: {user_id}")
            
            # Обработка реферального кода
            if ref_code and ref_code.startswith('REF'):
                referrer = await connection.fetchrow(
                    "SELECT user_id FROM users WHERE ref_code = $1", ref_code
                )
                if referrer and referrer['user_id'] != user_id:
                    # Даем бонус тому, кто пригласил
                    await connection.execute(
                        "UPDATE users SET message_count = GREATEST(0, message_count + 5) WHERE user_id = $1",
                        referrer['user_id']
                    )
                    # И новичку тоже бонус
                    await connection.execute(
                        "UPDATE users SET message_count = GREATEST(0, message_count + 3) WHERE user_id = $1",
                        user_id
                    )
            
            # Получаем актуальные данные пользователя
            user_data = await connection.fetchrow(
                "SELECT is_pro, message_count, pro_until FROM users WHERE user_id = $1", user_id
            )
            
        welcome_text = (
            f"Привет, {user_name}! 👋\n\n"
            "Я твой AI-психолог. Со мной можно говорить о чем угодно — я всегда выслушаю и поддержу.\n\n"
        )
        
        if is_new_user:
            welcome_text += (
                f"🎁 <b>Тебе доступен пробный PRO-период на {TRIAL_DAYS} день!</b>\n"
                "Пиши без ограничений!\n\n"
            )
        else:
            messages_left = FREE_MESSAGE_LIMIT - user_data['message_count']
            if user_data['is_pro']:
                welcome_text += "💎 <b>У тебя PRO-аккаунт! Безлимитное общение!</b>\n\n"
            else:
                welcome_text += f"• Бесплатно: {messages_left}/{FREE_MESSAGE_LIMIT} сообщений сегодня\n"
        
        welcome_text += (
            "• /ref - пригласить друга и получить бонус\n"
            "• /buy - оформить подписку PRO\n"
            "• /help - помощь\n\n"
            "Просто напиши мне о том, что тебя беспокоит..."
        )
        
        await message.answer(welcome_text, parse_mode="HTML")
        
    except Exception as e:
        await message.answer("⚠️ Произошла ошибка. Попробуйте позже.")
        print(f"❌ Ошибка в /start: {e}")

# Команда /ref - реферальная система
@dp.message(Command("ref"))
async def cmd_ref(message: types.Message):
    user_id = message.from_user.id
    
    pool = await create_db_pool()
    if not pool:
        await message.answer("⚠️ Сервис временно недоступен. Попробуйте позже.")
        return
    
    try:
        async with pool.acquire() as connection:
            user = await connection.fetchrow(
                "SELECT ref_code FROM users WHERE user_id = $1", user_id
            )
            
            if user:
                ref_link = f"https://t.me/{(await bot.get_me()).username}?start={user['ref_code']}"
                ref_text = (
                    "🎯 <b>Пригласи друзей и получи бонусы!</b>\n\n"
                    f"Твоя реферальная ссылка:\n<code>{ref_link}</code>\n\n"
                    "За каждого друга:\n"
                    "• Ты получаешь +5 бесплатных сообщений\n"
                    "• Друг получает +3 сообщения\n\n"
                    "Просто отправь эту ссылку друзьям!"
                )
                await message.answer(ref_text, parse_mode="HTML")
            else:
                await message.answer("⚠️ Сначала напишите /start")
                
    except Exception as e:
        await message.answer("⚠️ Произошла ошибка. Попробуйте позже.")
        print(f"❌ Ошибка в /ref: {e}")

# Команда /help
@dp.message(Command("help"))
async def cmd_help(message: types.Message):
    help_text = (
        "🤖 <b>Помощь по боту</b>\n\n"
        "• Просто напиши мне о том, что беспокоит\n"
        f"• Бесплатно: {FREE_MESSAGE_LIMIT} сообщений в день\n"
        "• PRO: безлимитное общение\n\n"
        "<b>Команды:</b>\n"
        "• /start - начать общение\n"
        "• /ref - пригласить друга (+3 сообщения)\n"
        "• /buy - оформить PRO\n"
        "• /help - эта справка\n\n"
        "<i>⚠️ Это не замена терапии. Если нужна профессиональная помощь — обратись к специалисту.</i>"
    )
    await message.answer(help_text, parse_mode="HTML")

# Команда /buy
@dp.message(Command("buy"))
async def cmd_buy(message: types.Message):
    buy_text = (
        "🚀 <b>PRO-подписка</b>\n\n"
        "• Безлимитные сообщения\n"
        "• Приоритетная поддержка\n"
        "• Доступ к новым функциям\n\n"
        "💵 <b>Стоимость: 299₽/месяц</b>\n\n"
        "Для оплаты напиши @assistantai_gpt\n"
        "или перейди по ссылке: https://example.com/buy\n\n"
        "<i>После оплаты доступ активируется в течение 5-15 минут</i>"
    )
    await message.answer(buy_text, parse_mode="HTML")

# Обработка всех текстовых сообщений
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
        async with pool.acquire() as connection:
            # Проверяем статус пользователя
            user = await connection.fetchrow(
                "SELECT is_pro, message_count, pro_until FROM users WHERE user_id = $1", user_id
            )
            
            if not user:
                await message.answer("⚠️ Пожалуйста, сначала напишите /start")
                return
            
            # Проверяем не истек ли пробный период
            is_pro = user['is_pro']
            pro_until = user['pro_until']
            if pro_until and datetime.now() > pro_until:
                is_pro = False
                await connection.execute(
                    "UPDATE users SET is_pro = FALSE WHERE user_id = $1", user_id
                )
                
            message_count = user['message_count']
            
            # Проверка на опасные темы
            danger_keywords = [
                'суицид', 'самоубийство', 'покончить с собой', 'убить себя', 
                'суицид', 'suicide', 'harm myself', 'hurt myself', 'end my life',
                'причинить вред', 'навредить себе', 'не хочу жить', 'жить не хочется',
                'свести счеты', 'повеситься', 'броситься', 'порезы', 'резать себя'
            ]

            user_text_lower = user_text.lower()
            if any(keyword in user_text_lower for keyword in danger_keywords):
                safety_response = (
                    "Я очень ценю, что ты делишься со мной своими переживаниями. "
                    "Твоя безопасность и благополучие очень важны.\n\n"
                    "К сожалению, я не могу обсуждать такие темы — это может быть опасно. "
                    "Пожалуйста, немедленно обратись к специалисту:\n\n"
                    "• <b>8-800-2000-122</b> - Кризисная линия доверия\n"
                    "• <b>112</b> - Экстренная служба\n"
                    "• @qlindrovalobot - Профессиональная помощь\n\n"
                    "Ты не одинок, и есть люди, которые готовы помочь 💙"
                )
                
                await connection.execute(
                    "INSERT INTO messages (user_id, user_message, bot_response) VALUES ($1, $2, $3)",
                    user_id, user_text, "БЛОК: опасная тема - перенаправление к специалисту"
                )
                
                await message.answer(safety_response, parse_mode="HTML")
                return
            
            # Проверяем лимиты для бесплатных пользователей
            if not is_pro and message_count >= FREE_MESSAGE_LIMIT:
                await message.answer(
                    f"❌ <b>Лимит сообщений исчерпан</b> ({FREE_MESSAGE_LIMIT} в день)\n\n"
                    "Перейдите на PRO-версию чтобы снять ограничения:\n"
                    "/buy - получить подписку\n\n"
                    "Или пригласи друга по /ref и получи +3 сообщения!",
                    parse_mode="HTML"
                )
                return
                
            # Обновляем счетчик сообщений
            if not is_pro:
                await connection.execute(
                    "UPDATE users SET message_count = message_count + 1 WHERE user_id = $1",
                    user_id
                )
                print(f"📊 Сообщение от пользователя {user_id}. Всего: {message_count + 1}/{FREE_MESSAGE_LIMIT}")
            
            # Показываем что бот печатает
            await bot.send_chat_action(chat_id=user_id, action="typing")
            
            # Отправляем запрос к DeepSeek
            try:
                response = await deepseek_client.chat.completions.create(
                    model="deepseek-chat",
                    messages=[{
                        "role": "user", 
                        "content": (
                            "Ты - эмпатичный психолог-помощник. Поддержи пользователя, прояви участие. "
                            "Будь внимательным слушателем. Задавай уточняющие вопросы. "
                            "Избегай медицинских диагнозов. Ответь на: " + user_text
                        )
                    }],
                    max_tokens=500,
                    temperature=0.7
                )
                
                ai_response = response.choices[0].message.content
                
            except Exception as e:
                print(f"❌ Ошибка DeepSeek API: {e}")
                ai_response = "Извините, произошла ошибка обработки. Попробуйте позже."
            
            # Сохраняем сообщение в историю
            await connection.execute(
                "INSERT INTO messages (user_id, user_message, bot_response) VALUES ($1, $2, $3)",
                user_id, user_text, ai_response
            )
            
            # Отправляем ответ пользователю
            await message.answer(ai_response)
            
    except Exception as e:
        await message.answer("⚠️ Произошла непредвиденная ошибка. Попробуйте позже.")
        print(f"❌ Критическая ошибка: {e}")

# Установка команд меню
async def set_bot_commands():
    await bot.set_my_commands([
        types.BotCommand(command="start", description="Начать общение"),
        types.BotCommand(command="ref", description="Пригласить друга (+5)"),
        types.BotCommand(command="buy", description="Купить PRO"),
        types.BotCommand(command="help", description="Помощь"),
    ])
    print("✅ Команды бота установлены")

# Запуск бота
async def main():
    await set_bot_commands()
    print("✅ Бот запущен! Ожидаем сообщения...")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
