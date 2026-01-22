import aiosqlite
from aiogram import Bot, Dispatcher, types
from aiogram.filters import Command
from aiogram.types import Message, CallbackQuery
from aiogram import F
import asyncio

# Токен бота
BOT_TOKEN = "8194198392:AAFjEcdDbJw8ev8NKRYM5lOqyKwg-dN4eCs"

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

# Получить всех игроков
async def get_all_players():
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute('''
            SELECT first_name, last_name, jersey_number
            FROM players
            ORDER BY jersey_number ASC
        ''')
        rows = await cursor.fetchall()
        return rows

# Клавиатура главного меню
def main_menu_keyboard():
    keyboard = [
        [types.InlineKeyboardButton(text="👤 Мой профиль", callback_data="profile")],
        [types.InlineKeyboardButton(text="🏒 Тренировки", callback_data="trainings")],
        [types.InlineKeyboardButton(text="🎮 Игры", callback_data="games")],
        [types.InlineKeyboardButton(text="📋 Состав", callback_data="team")],
    ]
    return types.InlineKeyboardMarkup(inline_keyboard=keyboard)

# Клавиатура "Назад"
def back_keyboard():
    keyboard = [[types.InlineKeyboardButton(text="◀️ Назад", callback_data="back_to_main")]]
    return types.InlineKeyboardMarkup(inline_keyboard=keyboard)

# Глобальный словарь для хранения последних сообщений бота
# {user_id: message_id}
last_bot_messages = {}

# Функция для удаления старых сообщений бота
async def delete_old_messages(bot, chat_id, user_id):
    if user_id in last_bot_messages:
        try:
            await bot.delete_message(chat_id, last_bot_messages[user_id])
        except Exception as e:
            print(f"Не удалось удалить сообщение {last_bot_messages[user_id]}: {e}")
        del last_bot_messages[user_id]

# Команда /start
async def start_command(message: Message):
    user_id = message.from_user.id
    chat_id = message.chat.id

    # Удаляем предыдущие сообщения бота (если есть)
    await delete_old_messages(message.bot, chat_id, user_id)

    if await player_exists(user_id):
        profile = await get_player(user_id)
        msg = await message.answer(
            f"👋 Привет, {profile['first_name']}!\n"
            f"Ты в системе хоккейной команды.\n\n"
            "Выбери действие:",
            reply_markup=main_menu_keyboard()
        )
        last_bot_messages[user_id] = msg.message_id
    else:
        msg = await message.answer(
            "👋 Привет! Давай создадим твой профиль.\n\n"
            "Напиши в одном сообщении:\n"
            "**Имя Фамилия Номер**\n\n"
            "Пример: `Вячеслав Федоров 19`"
        )
        last_bot_messages[user_id] = msg.message_id

# Обработка сообщения с профилем
async def handle_profile(message: Message):
    user_id = message.from_user.id
    chat_id = message.chat.id

    if await player_exists(user_id):
        return

    text = message.text.strip()

    parts = text.split()
    if len(parts) < 3:
        await message.answer("❌ Неверный формат. Нужно: Имя Фамилия Номер")
        return

    try:
        jersey_number = int(parts[-1])
        first_name = parts[0]
        last_name = ' '.join(parts[1:-1])
    except ValueError:
        await message.answer("❌ Номер должен быть числом!")
        return

    await save_player(user_id, first_name, last_name, jersey_number)

    # Удаляем сообщение пользователя (с профилем)
    try:
        await message.delete()
    except:
        pass

    # Удаляем все предыдущие сообщения бота
    await delete_old_messages(message.bot, chat_id, user_id)

    # Отправляем главное меню
    profile = await get_player(user_id)
    msg = await message.answer(
        f"🎉 Профиль создан!\n"
        f"Имя: {first_name}\n"
        f"Фамилия: {last_name}\n"
        f"Номер: {jersey_number}\n\n"
        "Выбери действие:",
        reply_markup=main_menu_keyboard()
    )
    last_bot_messages[user_id] = msg.message_id

# Обработка нажатий на кнопки
async def button_callback(callback_query: CallbackQuery):
    user_id = callback_query.from_user.id
    data = callback_query.data

    # Удаляем старое сообщение (если оно было сохранено)
    if user_id in last_bot_messages:
        try:
            await callback_query.bot.delete_message(callback_query.message.chat.id, last_bot_messages[user_id])
        except:
            pass
        del last_bot_messages[user_id]

    if data == "profile":
        profile = await get_player(user_id)
        if profile:
            msg = await callback_query.message.edit_text(
                f"👤 Твой профиль:\n"
                f"Имя: {profile['first_name']}\n"
                f"Фамилия: {profile['last_name']}\n"
                f"Номер: {profile['jersey_number']}",
                reply_markup=back_keyboard()
            )
        else:
            msg = await callback_query.message.edit_text(
                "❌ Профиль не найден.",
                reply_markup=back_keyboard()
            )
        last_bot_messages[user_id] = msg.message_id

    elif data == "trainings":
        msg = await callback_query.message.edit_text(
            "🏒 Здесь будет расписание тренировок.",
            reply_markup=back_keyboard()
        )
        last_bot_messages[user_id] = msg.message_id

    elif data == "games":
        msg = await callback_query.message.edit_text(
            "🎮 Здесь будет расписание игр.",
            reply_markup=back_keyboard()
        )
        last_bot_messages[user_id] = msg.message_id

    elif data == "team":
        players = await get_all_players()
        if not players:
            text = "📋 Состав пока пуст."
        else:
            text = "📋 <b>Состав команды:</b>\n\n"
            for idx, (first, last, num) in enumerate(players, 1):
                text += f"{idx}. {first} {last} (#{num})\n"
        msg = await callback_query.message.edit_text(
            text,
            parse_mode="HTML",
            reply_markup=back_keyboard()
        )
        last_bot_messages[user_id] = msg.message_id

    elif data == "back_to_main":
        profile = await get_player(user_id)
        msg = await callback_query.message.edit_text(
            f"👋 Привет, {profile['first_name']}!\n"
            f"Ты в системе хоккейной команды.\n\n"
            "Выбери действие:",
            reply_markup=main_menu_keyboard()
        )
        last_bot_messages[user_id] = msg.message_id

# Основная функция
async def main():
    await init_db()

    bot = Bot(token=BOT_TOKEN)
    dp = Dispatcher()

    dp.message.register(start_command, Command("start"))
    dp.message.register(handle_profile, F.text & ~F.text.startswith('/'))
    dp.callback_query.register(button_callback, lambda c: c.data in ["profile", "trainings", "games", "team", "back_to_main"])

    print("✅ Бот запущен. Ждём сообщений...")
    await dp.start_polling(bot)

if __name__ == '__main__':
    import asyncio
    asyncio.run(main())