import aiosqlite
from aiogram import Bot, Dispatcher, types
from aiogram.filters import Command
from aiogram.types import Message, CallbackQuery
from aiogram import F
from aiogram.fsm.state import StatesGroup, State
from aiogram.fsm.context import FSMContext
import asyncio
from datetime import datetime, timedelta

# Токен бота
BOT_TOKEN = "8194198392:AAFjEcdDbJw8ev8NKRYM5lOqyKwg-dN4eCs"

# Путь к базе данных
DB_PATH = 'hockey.db'

# Пароль для тренера
COACH_PASSWORD = "1234"

# Функция безопасного удаления сообщений
async def safe_delete(chat_id, message_id):
    try:
        await bot.delete_message(chat_id, message_id)
    except Exception as e:
        pass  # Не удалось удалить — игнорируем

# Класс состояний для тренировки
class NewTraining(StatesGroup):
    datetime = State()
    location = State()
    max_players = State()
    description = State()

# Класс состояний для игры
class NewGame(StatesGroup):
    datetime = State()
    location = State()
    opponent = State()
    description = State()

# Инициализация БД
async def init_db():
    async with aiosqlite.connect(DB_PATH) as db:
        # Таблица игроков
        await db.execute('''
            CREATE TABLE IF NOT EXISTS players (
                user_id INTEGER PRIMARY KEY,
                first_name TEXT NOT NULL,
                last_name TEXT NOT NULL,
                jersey_number INTEGER NOT NULL,
                is_coach INTEGER DEFAULT 0
            )
        ''')
        # Таблица тренировок
        await db.execute('''
            CREATE TABLE IF NOT EXISTS trainings (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                date TEXT NOT NULL,
                time TEXT NOT NULL,
                place TEXT NOT NULL,
                description TEXT,
                max_participants INTEGER DEFAULT 20
            )
        ''')
        # Таблица игр
        await db.execute('''
            CREATE TABLE IF NOT EXISTS games (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                date TEXT NOT NULL,
                time TEXT NOT NULL,
                place TEXT NOT NULL,
                opponent TEXT NOT NULL,
                description TEXT
            )
        ''')
        # Таблица записей на тренировки
        await db.execute('''
            CREATE TABLE IF NOT EXISTS training_signups (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                training_id INTEGER NOT NULL,
                FOREIGN KEY (user_id) REFERENCES players (user_id),
                FOREIGN KEY (training_id) REFERENCES trainings (id),
                UNIQUE(user_id, training_id)
            )
        ''')
        await db.commit()

# Сохранение профиля
async def save_player(user_id, first_name, last_name, jersey_number, is_coach=0):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute('''
            INSERT OR REPLACE INTO players (user_id, first_name, last_name, jersey_number, is_coach)
            VALUES (?, ?, ?, ?, ?)
        ''', (user_id, first_name, last_name, jersey_number, is_coach))
        await db.commit()

# Проверка, существует ли игрок
async def player_exists(user_id):
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute('SELECT 1 FROM players WHERE user_id = ?', (user_id,))
        row = await cursor.fetchone()
        return row is not None

# Проверка, является ли пользователь тренером
async def is_coach(user_id):
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute('SELECT is_coach FROM players WHERE user_id = ?', (user_id,))
        row = await cursor.fetchone()
        return row[0] == 1 if row else False

# Получить профиль игрока
async def get_player(user_id):
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute('SELECT first_name, last_name, jersey_number, is_coach FROM players WHERE user_id = ?', (user_id,))
        row = await cursor.fetchone()
        if row:
            return {
                'first_name': row[0],
                'last_name': row[1],
                'jersey_number': row[2],
                'is_coach': row[3] == 1
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

# Создать тренировку
async def create_training(date, time, place, description="", max_participants=20):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute('''
            INSERT INTO trainings (date, time, place, description, max_participants)
            VALUES (?, ?, ?, ?, ?)
        ''', (date, time, place, description, max_participants))
        await db.commit()

# Создать игру
async def create_game(date, time, place, opponent, description=""):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute('''
            INSERT INTO games (date, time, place, opponent, description)
            VALUES (?, ?, ?, ?, ?)
        ''', (date, time, place, opponent, description))
        await db.commit()

# Получить все тренировки
async def get_trainings():
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute('''
            SELECT id, date, time, place, description, max_participants
            FROM trainings
            ORDER BY date, time
        ''')
        rows = await cursor.fetchall()
        return rows

# Получить все игры
async def get_games():
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute('''
            SELECT id, date, time, place, opponent, description
            FROM games
            ORDER BY date, time
        ''')
        rows = await cursor.fetchall()
        return rows

# Записаться на тренировку
async def signup_for_training(user_id, training_id):
    try:
        async with aiosqlite.connect(DB_PATH) as db:
            await db.execute('''
                INSERT INTO training_signups (user_id, training_id)
                VALUES (?, ?)
            ''', (user_id, training_id))
            await db.commit()
            return True
    except aiosqlite.IntegrityError:
        return False  # Уже записан

# Отписаться от тренировки
async def unsubscribe_from_training(user_id, training_id):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute('''
            DELETE FROM training_signups
            WHERE user_id = ? AND training_id = ?
        ''', (user_id, training_id))
        await db.commit()

# Получить количество записавшихся на тренировку
async def get_signup_count(training_id):
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute('''
            SELECT COUNT(*) FROM training_signups WHERE training_id = ?
        ''', (training_id,))
        row = await cursor.fetchone()
        return row[0]

# Получить участников тренировки
async def get_training_participants(training_id):
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute('''
            SELECT p.first_name, p.last_name, p.jersey_number
            FROM training_signups ts
            JOIN players p ON ts.user_id = p.user_id
            WHERE ts.training_id = ?
            ORDER BY p.jersey_number
        ''', (training_id,))
        rows = await cursor.fetchall()
        return rows

# Клавиатура выбора роли
def role_selection_keyboard():
    keyboard = [
        [types.InlineKeyboardButton(text="👤 Я игрок", callback_data="role_player")],
        [types.InlineKeyboardButton(text="🎯 Я тренер", callback_data="role_coach")]
    ]
    return types.InlineKeyboardMarkup(inline_keyboard=keyboard)

# Клавиатура главного меню
def main_menu_keyboard(is_coach=False):
    keyboard = [
        [types.InlineKeyboardButton(text="👤 Мой профиль", callback_data="profile")],
        [types.InlineKeyboardButton(text="🏒 Тренировки", callback_data="trainings_list")],
        [types.InlineKeyboardButton(text="🎮 Игры", callback_data="games_list")],
        [types.InlineKeyboardButton(text="📋 Состав", callback_data="team")],
    ]
    if is_coach:
        keyboard.append([types.InlineKeyboardButton(text="🎯 Тренер", callback_data="coach_menu")])
    return types.InlineKeyboardMarkup(inline_keyboard=keyboard)

# Клавиатура "Назад"
def back_keyboard():
    keyboard = [[types.InlineKeyboardButton(text="◀️ Назад", callback_data="back_to_main")]]
    return types.InlineKeyboardMarkup(inline_keyboard=keyboard)

# Команда /start
async def start_command(message: Message):
    user_id = message.from_user.id

    if await player_exists(user_id):
        profile = await get_player(user_id)
        await message.answer(
            f"👋 Привет, {profile['first_name']}!\n"
            f"Ты в системе хоккейной команды.\n\n"
            "Выбери действие:",
            reply_markup=main_menu_keyboard(profile['is_coach'])
        )
    else:
        await message.answer(
            "👋 Привет! Кто ты?",
            reply_markup=role_selection_keyboard()
        )

# Команда /restart
async def restart_command(message: Message):
    user_id = message.from_user.id

    # Удаляем профиль
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute('DELETE FROM players WHERE user_id = ?', (user_id,))
        await db.commit()

    await message.answer(
        "🔄 Профиль удалён.\n"
        "Создай его заново.\n\n"
        "Кто ты?",
        reply_markup=role_selection_keyboard()
    )

# Обработка выбора роли
async def handle_role_selection(callback_query: CallbackQuery):
    data = callback_query.data
    user_id = callback_query.from_user.id

    if data == "role_player":
        await callback_query.message.edit_text(
            "📝 Введи своё имя, фамилию и хоккейный номер через пробел:\n\n"
            "<code>Имя Фамилия Номер</code>\n\n"
            "Пример: <code>Вячеслав Федоров 19</code>",
            parse_mode="HTML"
        )
    elif data == "role_coach":
        await callback_query.message.edit_text(
            "🔐 Введи пароль тренера:"
        )

# Обработка сообщения с профилем (для игрока или тренера)
async def handle_profile(message: Message):
    user_id = message.from_user.id
    text = message.text.strip()

    # Если ждём пароль тренера
    if text == COACH_PASSWORD:
        # Проверим, есть ли уже профиль
        if await player_exists(user_id):
            await message.answer("❌ У тебя уже есть профиль.")
            return

        await message.answer("✅ Пароль верен!\n\nВведите имя и фамилию тренера:")
        # Здесь можно добавить логику сохранения тренера — пока просто пропускаем
        return

    # Если не ждём ничего — значит, это игрок
    if await player_exists(user_id):
        return

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

    await save_player(user_id, first_name, last_name, jersey_number, is_coach=0)

    # Удаляем сообщение пользователя (с профилем)
    try:
        await message.delete()
    except:
        pass

    # Отправляем главное меню
    await message.answer(
        f"🎉 Профиль игрока создан!\n"
        f"Имя: {first_name}\n"
        f"Фамилия: {last_name}\n"
        f"Номер: {jersey_number}\n\n"
        "Выбери действие:",
        reply_markup=main_menu_keyboard()
    )

# === Кнопка "Создать тренировку" ===
@dp.callback_query(lambda c: c.data == "create_training")
async def cmd_create_training(callback_query: CallbackQuery, state: FSMContext):
    user_id = callback_query.from_user.id
    if not await is_coach(user_id):
        await callback_query.message.edit_text("❌ Эта функция только для тренеров.")
        return

    sent = await callback_query.message.edit_text(
        "📅 Введи дату и время тренировки в формате:\n"
        "<code>ДД.ММ.ГГГГ ЧЧ:ММ</code>\n\n"
        "Пример: <code>05.02.2026 19:00</code>",
        parse_mode="HTML"
    )
    await state.update_data(prev_bot_msg_id=sent.message_id)
    await state.set_state(NewTraining.datetime)

@dp.message(NewTraining.datetime)
async def process_training_datetime(message: types.Message, state: FSMContext):
    data = await state.get_data()
    prev_id = data.get("prev_bot_msg_id")
    await safe_delete(message.chat.id, message.message_id)
    if prev_id:
        await safe_delete(message.chat.id, prev_id)

    text = message.text.strip()
    if len(text) != 16 or text[2] != '.' or text[5] != '.' or text[10] != ' ' or text[13] != ':':
        sent = await message.answer("❌ Неверный формат. Попробуй ещё раз:\n<code>05.02.2026 19:00</code>", parse_mode="HTML")
        await state.update_data(prev_bot_msg_id=sent.message_id)
        return

    # Преобразуем в ГГГГ-ММ-ДД ЧЧ:ММ
    day, month, year = text[:2], text[3:5], text[6:10]
    time = text[11:]
    date_str = f"{year}-{month}-{day}"

    await state.update_data(datetime=date_str, time=time)
    sent = await message.answer("📍 Где тренировка?")
    await state.update_data(prev_bot_msg_id=sent.message_id)
    await state.set_state(NewTraining.location)

@dp.message(NewTraining.location)
async def process_training_location(message: types.Message, state: FSMContext):
    data = await state.get_data()
    prev_id = data.get("prev_bot_msg_id")
    await safe_delete(message.chat.id, message.message_id)
    if prev_id:
        await safe_delete(message.chat.id, prev_id)
    await state.update_data(location=message.text.strip())
    sent = await message.answer("👥 Максимальное число игроков (например: 20)")
    await state.update_data(prev_bot_msg_id=sent.message_id)
    await state.set_state(NewTraining.max_players)

@dp.message(NewTraining.max_players)
async def process_training_max_players(message: types.Message, state: FSMContext):
    data = await state.get_data()
    prev_id = data.get("prev_bot_msg_id")
    await safe_delete(message.chat.id, message.message_id)
    if prev_id:
        await safe_delete(message.chat.id, prev_id)
    if not message.text.strip().isdigit():
        sent = await message.answer("❌ Введи число (например: 20)")
        await state.update_data(prev_bot_msg_id=sent.message_id)
        return
    await state.update_data(max_players=int(message.text.strip()))
    sent = await message.answer("📝 Описание (или «-» если не нужно)")
    await state.update_data(prev_bot_msg_id=sent.message_id)
    await state.set_state(NewTraining.description)

@dp.message(NewTraining.description)
async def process_training_description(message: types.Message, state: FSMContext):
    data = await state.get_data()
    prev_id = data.get("prev_bot_msg_id")
    await safe_delete(message.chat.id, message.message_id)
    if prev_id:
        await safe_delete(message.chat.id, prev_id)

    desc = message.text.strip()
    if desc == "-":
        desc = ""

    # Создаём тренировку
    date = data["datetime"]
    time = data["time"]
    place = data["location"]
    max_players = data["max_players"]

    await create_training(date, time, place, desc, max_players)

    # Получаем ID тренировки
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute('SELECT id FROM trainings WHERE date = ? AND time = ? AND place = ?', (date, time, place))
        row = await cursor.fetchone()
        training_id = row[0] if row else 0

    await message.answer(
        f"✅ Тренировка создана!\n\n"
        f"📅 {date} | {time}\n"
        f"📍 {place}\n"
        f"👥 Мест: {max_players}\n"
        f"ID: <b>{training_id}</b>",
        parse_mode="HTML"
    )
    await state.clear()

# === Кнопка "Создать игру" ===
@dp.callback_query(lambda c: c.data == "create_game")
async def cmd_create_game(callback_query: CallbackQuery, state: FSMContext):
    user_id = callback_query.from_user.id
    if not await is_coach(user_id):
        await callback_query.message.edit_text("❌ Эта функция только для тренеров.")
        return

    sent = await callback_query.message.edit_text(
        "📅 Введи дату и время игры в формате:\n"
        "<code>ДД.ММ.ГГГГ ЧЧ:ММ</code>\n\n"
        "Пример: <code>05.02.2026 19:00</code>",
        parse_mode="HTML"
    )
    await state.update_data(prev_bot_msg_id=sent.message_id)
    await state.set_state(NewGame.datetime)

@dp.message(NewGame.datetime)
async def process_game_datetime(message: types.Message, state: FSMContext):
    data = await state.get_data()
    prev_id = data.get("prev_bot_msg_id")
    await safe_delete(message.chat.id, message.message_id)
    if prev_id:
        await safe_delete(message.chat.id, prev_id)

    text = message.text.strip()
    if len(text) != 16 or text[2] != '.' or text[5] != '.' or text[10] != ' ' or text[13] != ':':
        sent = await message.answer("❌ Неверный формат. Попробуй ещё раз:\n<code>05.02.2026 19:00</code>", parse_mode="HTML")
        await state.update_data(prev_bot_msg_id=sent.message_id)
        return

    # Преобразуем в ГГГГ-ММ-ДД ЧЧ:ММ
    day, month, year = text[:2], text[3:5], text[6:10]
    time = text[11:]
    date_str = f"{year}-{month}-{day}"

    await state.update_data(datetime=date_str, time=time)
    sent = await message.answer("📍 Где игра?")
    await state.update_data(prev_bot_msg_id=sent.message_id)
    await state.set_state(NewGame.location)

@dp.message(NewGame.location)
async def process_game_location(message: types.Message, state: FSMContext):
    data = await state.get_data()
    prev_id = data.get("prev_bot_msg_id")
    await safe_delete(message.chat.id, message.message_id)
    if prev_id:
        await safe_delete(message.chat.id, prev_id)
    await state.update_data(location=message.text.strip())
    sent = await message.answer("🆚 Соперник (например: Авангард)")
    await state.update_data(prev_bot_msg_id=sent.message_id)
    await state.set_state(NewGame.opponent)

@dp.message(NewGame.opponent)
async def process_game_opponent(message: types.Message, state: FSMContext):
    data = await state.get_data()
    prev_id = data.get("prev_bot_msg_id")
    await safe_delete(message.chat.id, message.message_id)
    if prev_id:
        await safe_delete(message.chat.id, prev_id)
    await state.update_data(opponent=message.text.strip())
    sent = await message.answer("📝 Описание (или «-» если не нужно)")
    await state.update_data(prev_bot_msg_id=sent.message_id)
    await state.set_state(NewGame.description)

@dp.message(NewGame.description)
async def process_game_description(message: types.Message, state: FSMContext):
    data = await state.get_data()
    prev_id = data.get("prev_bot_msg_id")
    await safe_delete(message.chat.id, message.message_id)
    if prev_id:
        await safe_delete(message.chat.id, prev_id)

    desc = message.text.strip()
    if desc == "-":
        desc = ""

    # Создаём игру
    date = data["datetime"]
    time = data["time"]
    place = data["location"]
    opponent = data["opponent"]

    await create_game(date, time, place, opponent, desc)

    # Получаем ID игры
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute('SELECT id FROM games WHERE date = ? AND time = ? AND place = ?', (date, time, place))
        row = await cursor.fetchone()
        game_id = row[0] if row else 0

    await message.answer(
        f"✅ Игра создана!\n\n"
        f"📅 {date} | {time}\n"
        f"📍 {place}\n"
        f"🆚 {opponent}\n"
        f"ID: <b>{game_id}</b>",
        parse_mode="HTML"
    )
    await state.clear()

# Обработка нажатий на кнопки
async def button_callback(callback_query: CallbackQuery):
    user_id = callback_query.from_user.id
    data = callback_query.data

    if data == "profile":
        profile = await get_player(user_id)
        if profile:
            await callback_query.message.edit_text(
                f"👤 Твой профиль:\n"
                f"Имя: {profile['first_name']}\n"
                f"Фамилия: {profile['last_name']}\n"
                f"Номер: {profile['jersey_number']}\n"
                f"Тренер: {'✅ Да' if profile['is_coach'] else '❌ Нет'}",
                reply_markup=back_keyboard()
            )
        else:
            await callback_query.message.edit_text(
                "❌ Профиль не найден.",
                reply_markup=back_keyboard()
            )

    elif data == "trainings_list":
        trainings = await get_trainings()
        if not trainings:
            await callback_query.message.edit_text(
                "🏒 Тренировки пока не созданы.",
                reply_markup=back_keyboard()
            )
        else:
            text = "🏒 <b>Ближайшие тренировки:</b>\n\n"
            for t in trainings:
                training_id, date, time, place, desc, max_p = t
                count = await get_signup_count(training_id)
                text += f"📅 <b>{date}</b> | ⏰ {time}\n"
                text += f"📍 {place}\n"
                if desc:
                    text += f"📝 {desc}\n"
                text += f"👥 Участники: {count}/{max_p}\n"
                text += f"/signup_{training_id} — записаться\n\n"
            await callback_query.message.edit_text(
                text,
                parse_mode="HTML",
                reply_markup=back_keyboard()
            )

    elif data.startswith("signup_"):
        training_id = int(data.split("_")[1])

        success = await signup_for_training(user_id, training_id)
        if success:
            await callback_query.message.edit_text(
                "✅ Ты записался на тренировку!",
                reply_markup=back_keyboard()
            )
        else:
            await callback_query.message.edit_text(
                "❌ Ты уже записан на эту тренировку.",
                reply_markup=back_keyboard()
            )

    elif data == "games_list":
        games = await get_games()
        if not games:
            await callback_query.message.edit_text(
                "🎮 Игры пока не созданы.",
                reply_markup=back_keyboard()
            )
        else:
            text = "🎮 <b>Ближайшие игры:</b>\n\n"
            for g in games:
                game_id, date, time, place, opponent, desc = g
                text += f"📅 <b>{date}</b> | ⏰ {time}\n"
                text += f"📍 {place}\n"
                text += f"🆚 {opponent}\n"
                if desc:
                    text += f"📝 {desc}\n"
                text += "\n"
            await callback_query.message.edit_text(
                text,
                parse_mode="HTML",
                reply_markup=back_keyboard()
            )

    elif data == "team":
        players = await get_all_players()
        if not players:
            text = "📋 Состав пока пуст."
        else:
            text = "📋 <b>Состав команды:</b>\n\n"
            for idx, (first, last, num) in enumerate(players, 1):
                text += f"{idx}. {first} {last} (#{num})\n"
        await callback_query.message.edit_text(
            text,
            parse_mode="HTML",
            reply_markup=back_keyboard()
        )

    elif data == "coach_menu":
        if await is_coach(user_id):
            keyboard = [
                [types.InlineKeyboardButton(text="➕ Создать тренировку", callback_data="create_training")],
                [types.InlineKeyboardButton(text="➕ Создать игру", callback_data="create_game")],
                [types.InlineKeyboardButton(text="👥 Участники тренировки", callback_data="list_participants")],
                [types.InlineKeyboardButton(text="◀️ Назад", callback_data="back_to_main")]
            ]
            await callback_query.message.edit_text(
                "🎯 Меню тренера:",
                reply_markup=types.InlineKeyboardMarkup(inline_keyboard=keyboard)
            )
        else:
            await callback_query.message.edit_text(
                "❌ У тебя нет прав тренера.",
                reply_markup=back_keyboard()
            )

    elif data == "list_participants":
        if await is_coach(user_id):
            trainings = await get_trainings()
            if not trainings:
                await callback_query.message.edit_text(
                    "❌ Нет тренировок для просмотра.",
                    reply_markup=back_keyboard()
                )
            else:
                text = "👥 Участники тренировок:\n\n"
                for t in trainings:
                    training_id, date, time, place, desc, _ = t
                    participants = await get_training_participants(training_id)
                    text += f"📅 {date} | ⏰ {time}\n"
                    text += f"📍 {place}\n"
                    if desc:
                        text += f"📝 {desc}\n"
                    if participants:
                        text += "Участники:\n"
                        for p in participants:
                            text += f"- {p[0]} {p[1]} (#{p[2]})\n"
                    else:
                        text += "❌ Нет записавшихся\n"
                    text += "\n"
                await callback_query.message.edit_text(
                    text,
                    reply_markup=back_keyboard()
                )
        else:
            await callback_query.message.edit_text(
                "❌ У тебя нет прав тренера.",
                reply_markup=back_keyboard()
            )

    elif data == "back_to_main":
        profile = await get_player(user_id)
        await callback_query.message.edit_text(
            f"👋 Привет, {profile['first_name']}!\n"
            f"Ты в системе хоккейной команды.\n\n"
            "Выбери действие:",
            reply_markup=main_menu_keyboard(profile['is_coach'] if profile else False)
        )

# Функция для отправки уведомлений (в фоне)
async def send_reminders(bot):
    while True:
        await asyncio.sleep(60)  # Проверяем каждую минуту

        now = datetime.now()
        reminder_time = now + timedelta(hours=1)  # За 1 час до начала
        reminder_str = reminder_time.strftime("%Y-%m-%d %H:%M")

        async with aiosqlite.connect(DB_PATH) as db:
            cursor = await db.execute('''
                SELECT t.id, t.date, t.time, t.place, t.description
                FROM trainings t
                WHERE t.date || ' ' || t.time = ?
            ''', (reminder_str,))
            trainings = await cursor.fetchall()

        for t in trainings:
            training_id, date, time, place, desc = t

            # Получаем участников
            participants = await get_training_participants(training_id)

            for p in participants:
                first, last, num = p
                # Найдём user_id участника
                cursor = await db.execute('SELECT user_id FROM players WHERE first_name = ? AND last_name = ? AND jersey_number = ?', (first, last, num))
                row = await cursor.fetchone()
                if row:
                    user_id = row[0]
                    try:
                        msg = f"⏰ Напоминание!\nТренировка:\n{date} | {time} | {place}"
                        if desc:
                            msg += f"\n{desc}"
                        await bot.send_message(user_id, msg)
                    except:
                        pass  # Не смогли отправить — пропускаем

# Основная функция
async def main():
    global bot
    await init_db()

    bot = Bot(token=BOT_TOKEN)
    dp = Dispatcher()

    # Регистрируем FSM-хендлеры
    dp.callback_query.register(cmd_create_training, lambda c: c.data == "create_training")
    dp.message.register(process_training_datetime, NewTraining.datetime)
    dp.message.register(process_training_location, NewTraining.location)
    dp.message.register(process_training_max_players, NewTraining.max_players)
    dp.message.register(process_training_description, NewTraining.description)

    dp.callback_query.register(cmd_create_game, lambda c: c.data == "create_game")
    dp.message.register(process_game_datetime, NewGame.datetime)
    dp.message.register(process_game_location, NewGame.location)
    dp.message.register(process_game_opponent, NewGame.opponent)
    dp.message.register(process_game_description, NewGame.description)

    # Регистрируем остальные хендлеры
    dp.message.register(start_command, Command("start"))
    dp.message.register(restart_command, Command("restart"))
    dp.message.register(handle_profile, F.text & ~F.command)
    dp.callback_query.register(handle_role_selection, lambda c: c.data in ["role_player", "role_coach"])
    dp.callback_query.register(button_callback, lambda c: c.data in ["profile", "trainings_list", "games_list", "team", "coach_menu", "create_training", "create_game", "list_participants", "back_to_main"] or c.data.startswith("signup_"))

    # Запускаем задачу для напоминаний
    asyncio.create_task(send_reminders(bot))

    print("✅ Бот запущен. Ждём сообщений...")
    await dp.start_polling(bot)

if __name__ == '__main__':
    import asyncio
    asyncio.run(main())