import aiosqlite
from aiogram import Bot, Dispatcher, types
from aiogram.filters import Command
from aiogram.types import Message
from aiogram import F

# Токен бота (замени на свой)
BOT_TOKEN = "YOUR_BOT_TOKEN"

# Путь к базе данных
DB_PATH = 'hockey.db'

# Инициализация БД
async def init_db():
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute('''
            CREATE TABLE IF NOT EXISTS players (
                user_id INTEGER PRIMARY KEY,
                first_name TEXT NOT NULL,
                last_name TEXT NOT NULL,
                jersey_number INTEGER NOT NULL
            )
        ''')
        await db.commit()

# Сохранение профиля
async def save_player(user_id, first_name, last_name, jersey_number):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute('''
            INSERT OR REPLACE INTO players (user_id, first_name, last_name, jersey_number)
            VALUES (?, ?, ?, ?)
        ''', (user_id, first_name, last_name, jersey_number))
        await db.commit()

# Проверка, существует ли игрок
async def player_exists(user_id):
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute('SELECT 1 FROM players WHERE user_id = ?', (user_id,))
        row = await cursor.fetchone()
        return row is not None

# Команда /start
async def start_command(message: Message):
    user_id = message.from_user.id
    if await player_exists(user_id):
        await message.answer("✅ Твой профиль уже создан!")
    else:
        await message.answer(
            "👋 Привет! Давай создадим твой профиль.\n\n"
            "Напиши в одном сообщении:\n"
            "**Имя Фамилия Номер**\n\n"
            "Пример: `Вячеслав Федоров 19`"
        )

# Обработка сообщения с профилем
async def handle_profile(message: Message):
    user_id = message.from_user.id

    # Если профиль уже есть — игнорируем
    if await player_exists(user_id):
        return

    text = message.text.strip()

    # Разбиваем текст
    parts = text.split()
    if len(parts) < 3:
        await message.answer("❌ Неверный формат. Нужно: Имя Фамилия Номер")
        return

    try:
        # Последнее слово — номер
        jersey_number = int(parts[-1])
        first_name = parts[0]
        last_name = ' '.join(parts[1:-1])  # На случай, если фамилия состоит из двух слов
    except ValueError:
        await message.answer("❌ Номер должен быть числом!")
        return

    # Сохраняем
    await save_player(user_id, first_name, last_name, jersey_number)
    await message.answer(
        f"🎉 Профиль создан!\n"
        f"Имя: {first_name}\n"
        f"Фамилия: {last_name}\n"
        f"Номер: {jersey_number}"
    )

# Основная функция
async def main():
    await init_db()

    bot = Bot(token=BOT_TOKEN)
    dp = Dispatcher()

    dp.message.register(start_command, Command("start"))
    dp.message.register(handle_profile, F.text & ~F.text.startswith('/'))

    print("✅ Бот запущен. Ждём сообщений...")
    await dp.start_polling(bot)

if __name__ == '__main__':
    import asyncio
    asyncio.run(main())