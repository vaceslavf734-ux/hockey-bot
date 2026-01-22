import aiosqlite
from aiogram import Bot, Dispatcher, types
from aiogram.filters import Command
from aiogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram import F
import asyncio

# Токен бота (замени на свой)
BOT_TOKEN = "8194198392:AAFjEcdDbJw8ev8NKRYM5lOqyKwg-dN4eCs"  # ← ЗАМЕНИ НА РЕАЛЬНЫЙ ТОКЕН!

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

# Получить профиль игрока
async def get_player(user_id):
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute('SELECT first_name, last_name, jersey_number FROM players WHERE user_id = ?', (user_id,))
        row = await cursor.fetchone()
        if row:
            return {
                'first_name': row[0],
                'last_name': row[1],
                'jersey_number': row[2]
            }
        return None

# Клавиатура главного меню
def main_menu_keyboard():
    keyboard = [
        [InlineKeyboardButton(text="👤 Мой профиль", callback_data="profile")],
        [InlineKeyboardButton(text="🏒 Тренировки", callback_data="trainings")],
        [InlineKeyboardButton(text="🎮 Игры", callback_data="games")],
        [InlineKeyboardButton(text="📋 Состав", callback_data="team")],
    ]
    return InlineKeyboardMarkup(inline_keyboard=keyboard)

# Команда /start
async def start_command(message: Message):
    user_id = message.from_user.id
    if await player_exists(user_id):
        # Удаляем предыдущее сообщение (если есть)
        try:
            await message.delete()
        except:
            pass  # Если не удалось удалить — игнорируем

        # Отправляем главное меню
        profile = await get_player(user_id)
        await message.answer(
            f"👋 Привет, {profile['first_name']}!\n"
            f"Ты в системе хоккейной команды.\n\n"
            "Выбери действие:",
            reply_markup=main_menu_keyboard()
        )
    else:
        # Удаляем предыдущее сообщение (если есть)
        try:
            await message.delete()
        except:
            pass

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

    # Удаляем сообщение с профилем (чтобы не мешало)
    try:
        await message.delete()
    except:
        pass

    # Отправляем главное меню
    await message.answer(
        f"🎉 Профиль создан!\n"
        f"Имя: {first_name}\n"
        f"Фамилия: {last_name}\n"
        f"Номер: {jersey_number}\n\n"
        "Выбери действие:",
        reply_markup=main_menu_keyboard()
    )

# Обработка нажатий на кнопки
async def button_callback(callback_query: types.CallbackQuery):
    user_id = callback_query.from_user.id
    data = callback_query.data

    # Удаляем сообщение с кнопками (чтобы не захламлять чат)
    try:
        await callback_query.message.delete()
    except:
        pass

    if data == "profile":
        profile = await get_player(user_id)
        if profile:
            await callback_query.message.answer(
                f"👤 Твой профиль:\n"
                f"Имя: {profile['first_name']}\n"
                f"Фамилия: {profile['last_name']}\n"
                f"Номер: {profile['jersey_number']}"
            )
        else:
            await callback_query.message.answer("❌ Профиль не найден.")

    elif data == "trainings":
        await callback_query.message.answer("🏒 Здесь будет расписание тренировок.")

    elif data == "games":
        await callback_query.message.answer("🎮 Здесь будет расписание игр.")

    elif data == "team":
        await callback_query.message.answer("📋 Здесь будет состав команды.")

    # Отправляем новое меню
    await callback_query.message.answer(
        "Выбери действие:",
        reply_markup=main_menu_keyboard()
    )

# Основная функция
async def main():
    await init_db()

    bot = Bot(token=BOT_TOKEN)
    dp = Dispatcher()

    dp.message.register(start_command, Command("start"))
    dp.message.register(handle_profile, F.text & ~F.text.startswith('/'))
    dp.callback_query.register(button_callback, lambda c: c.data in ["profile", "trainings", "games", "team"])

    print("✅ Бот запущен. Ждём сообщений...")
    await dp.start_polling(bot)

if __name__ == '__main__':
    import asyncio
    asyncio.run(main())