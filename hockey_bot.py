import asyncio
import aiosqlite
from aiogram import Bot, Dispatcher, types
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.context import FSMContext
from aiogram.filters import Command
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton

# === ТОКЕН БОТА ===
BOT_TOKEN = "8194198392:AAFjEcdDbJw8ev8NKRYM5lOqyKwg-dN4eCs"
COACH_PASSWORD = "1234"

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher(storage=MemoryStorage())

# === СОСТОЯНИЯ ===
class PlayerRegistration(StatesGroup):
    full_name_and_number = State()

class CoachRegistration(StatesGroup):
    password = State()
    full_name = State()  # Имя и фамилия в одном сообщении

class NewTraining(StatesGroup):
    datetime = State()
    location = State()
    max_players = State()
    description = State()

# === ИНИЦИАЛИЗАЦИЯ БД ===
async def init_db():
    async with aiosqlite.connect("hockey.db") as db:
        await db.execute("""
            CREATE TABLE IF NOT EXISTS players (
                user_id INTEGER PRIMARY KEY,
                first_name TEXT NOT NULL,
                last_name TEXT NOT NULL,
                jersey_number TEXT NOT NULL
            )
        """)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS coaches (
                user_id INTEGER PRIMARY KEY,
                first_name TEXT NOT NULL,
                last_name TEXT NOT NULL
            )
        """)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS trainings (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                datetime TEXT NOT NULL,
                location TEXT,
                max_players INTEGER DEFAULT 20,
                description TEXT
            )
        """)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS registrations (
                user_id INTEGER,
                training_id INTEGER,
                FOREIGN KEY(training_id) REFERENCES trainings(id),
                UNIQUE(user_id, training_id)
            )
        """)
        await db.commit()

# === УТИЛИТА: безопасное удаление ===
async def safe_delete(chat_id: int, message_id: int):
    try:
        await bot.delete_message(chat_id=chat_id, message_id=message_id)
    except Exception:
        pass

# === КНОПКИ ВЫБОРА РОЛИ ===
def get_role_keyboard():
    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="👤 Я игрок", callback_data="role_player"),
                InlineKeyboardButton(text="👨‍🏫 Я тренер", callback_data="role_coach")
            ]
        ]
    )
    return keyboard

# === ГЛАВНОЕ МЕНЮ ===
def get_main_menu(is_coach: bool):
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📅 Тренировки", callback_data="trainings")],
        [InlineKeyboardButton(text="👥 Состав", callback_data="squad")],
        [InlineKeyboardButton(text="👤 Профиль", callback_data="profile")]
    ])

    if is_coach:
        keyboard.inline_keyboard.insert(0, [InlineKeyboardButton(text="➕ Создать тренировку", callback_data="create_training")])

    return keyboard

# === /start ===
@dp.message(Command("start"))
async def cmd_start(message: types.Message, state: FSMContext):
    user_id = message.from_user.id
    async with aiosqlite.connect("hockey.db") as db:
        cursor = await db.execute("SELECT 1 FROM players WHERE user_id = ?", (user_id,))
        player = await cursor.fetchone()
        cursor = await db.execute("SELECT 1 FROM coaches WHERE user_id = ?", (user_id,))
        coach = await cursor.fetchone()

        if player or coach:
            is_coach = bool(coach)
            sent = await message.answer(
                "Привет! Выбери действие:",
                reply_markup=get_main_menu(is_coach)
            )
            await state.update_data(prev_bot_msg_id=sent.message_id)
        else:
            sent = await message.answer(
                "Привет! Кто ты?",
                reply_markup=get_role_keyboard()
            )
            await state.update_data(prev_bot_msg_id=sent.message_id)

# === Обработка главного меню ===
@dp.callback_query(lambda c: c.data in ["trainings", "squad", "profile", "create_training"])
async def handle_main_menu(callback: types.CallbackQuery, state: FSMContext):
    data = await state.get_data()
    prev_id = data.get("prev_bot_msg_id")

    # Удаляем предыдущее сообщение
    if prev_id:
        await safe_delete(callback.message.chat.id, prev_id)

    if callback.data == "trainings":
        await cmd_trainings(callback.message)
    elif callback.data == "squad":
        await show_squad(callback.message)
    elif callback.data == "profile":
        await show_profile(callback.message)
    elif callback.data == "create_training":
        await cmd_new_training(callback.message, state)

    await callback.answer()

# === Обработка нажатия кнопок выбора роли ===
@dp.callback_query(lambda c: c.data in ["role_player", "role_coach"])
async def handle_role_choice(callback: types.CallbackQuery, state: FSMContext):
    data = await state.get_data()
    prev_id = data.get("prev_bot_msg_id")

    # Удаляем предыдущее сообщение
    await safe_delete(callback.message.chat.id, prev_id)

    if callback.data == "role_player":
        sent = await callback.message.answer(
            "📝 Введи своё имя, фамилию и хоккейный номер через пробел:\n\n"
            "<code>Слава Федоров 19</code>",
            parse_mode="HTML"
        )
        await state.update_data(prev_bot_msg_id=sent.message_id)
        await state.set_state(PlayerRegistration.full_name_and_number)
    else:
        sent = await callback.message.answer("🔐 Введи пароль тренера:")
        await state.update_data(prev_bot_msg_id=sent.message_id)
        await state.set_state(CoachRegistration.password)

    await callback.answer()

# === РЕГИСТРАЦИЯ ИГРОКА ===
@dp.message(PlayerRegistration.full_name_and_number)
async def process_full_name_and_number(message: types.Message, state: FSMContext):
    data = await state.get_data()
    prev_id = data.get("prev_bot_msg_id")

    await safe_delete(message.chat.id, message.message_id)
    if prev_id:
        await safe_delete(message.chat.id, prev_id)

    text = message.text.strip().split()
    if len(text) < 2:
        sent = await message.answer(
            "❌ Неверный формат.\n\n"
            "Напиши: <code>Имя Фамилия Номер</code>\n"
            "Пример: <code>Слава Федоров 19</code>",
            parse_mode="HTML"
        )
        await state.update_data(prev_bot_msg_id=sent.message_id)
        return

    number = text[-1]
    if not number.isdigit():
        sent = await message.answer("❌ Номер должен быть числом (например: 19).")
        await state.update_data(prev_bot_msg_id=sent.message_id)
        return

    full_name = " ".join(text[:-1])
    parts = full_name.split(" ", 1)
    first_name = parts[0]
    last_name = parts[1] if len(parts) > 1 else "Не указано"

    user_id = message.from_user.id

    async with aiosqlite.connect("hockey.db") as db:
        await db.execute(
            "INSERT OR REPLACE INTO players (user_id, first_name, last_name, jersey_number) VALUES (?, ?, ?, ?)",
            (user_id, first_name, last_name, number)
        )
        await db.commit()

    sent = await message.answer(
        f"✅ Добро пожаловать, {first_name} {last_name}!\nТеперь ты в команде.",
        reply_markup=get_main_menu(is_coach=False)
    )
    await state.update_data(prev_bot_msg_id=sent.message_id)
    await state.clear()

# === РЕГИСТРАЦИЯ ТРЕНЕРА ===
@dp.message(CoachRegistration.password)
async def process_coach_password(message: types.Message, state: FSMContext):
    data = await state.get_data()
    prev_id = data.get("prev_bot_msg_id")

    await safe_delete(message.chat.id, message.message_id)
    if prev_id:
        await safe_delete(message.chat.id, prev_id)

    if message.text.strip() != COACH_PASSWORD:
        sent = await message.answer("❌ Неверный пароль. Попробуй снова или напиши /iamcoach.")
        await state.update_data(prev_bot_msg_id=sent.message_id)
        return

    sent = await message.answer("✅ Пароль верный!\nВведи своё имя и фамилию через пробел:\n\n<code>Иван Петров</code>")
    await state.update_data(prev_bot_msg_id=sent.message_id)
    await state.set_state(CoachRegistration.full_name)

@dp.message(CoachRegistration.full_name)
async def process_coach_full_name(message: types.Message, state: FSMContext):
    data = await state.get_data()
    prev_id = data.get("prev_bot_msg_id")

    await safe_delete(message.chat.id, message.message_id)
    if prev_id:
        await safe_delete(message.chat.id, prev_id)

    text = message.text.strip().split()
    if len(text) < 2:
        sent = await message.answer(
            "❌ Неверный формат.\n\n"
            "Напиши: <code>Имя Фамилия</code>\n"
            "Пример: <code>Иван Петров</code>",
            parse_mode="HTML"
        )
        await state.update_data(prev_bot_msg_id=sent.message_id)
        return

    first_name = text[0]
    last_name = " ".join(text[1:])  # Фамилия может состоять из нескольких слов

    user_id = message.from_user.id

    async with aiosqlite.connect("hockey.db") as db:
        await db.execute(
            "INSERT INTO coaches (user_id, first_name, last_name) VALUES (?, ?, ?)",
            (user_id, first_name, last_name)
        )
        await db.commit()

    sent = await message.answer(
        f"✅ Добро пожаловать, тренер {first_name} {last_name}!",
        reply_markup=get_main_menu(is_coach=True)
    )
    await state.update_data(prev_bot_msg_id=sent.message_id)
    await state.clear()

# === /new_training ===
@dp.message(Command("new_training"))
async def cmd_new_training(message: types.Message, state: FSMContext):
    if not await is_coach(message.from_user.id):
        await message.answer("❌ Эта команда только для тренеров.")
        return

    sent = await message.answer(
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

    await state.update_data(datetime=text)
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

    async with aiosqlite.connect("hockey.db") as db:
        cursor = await db.execute(
            "INSERT INTO trainings (datetime, location, max_players, description) VALUES (?, ?, ?, ?)",
            (data["datetime"], data["location"], data["max_players"], desc)
        )
        await db.commit()
        training_id = cursor.lastrowid

    sent = await message.answer(
        f"✅ Тренировка создана!\n\n"
        f"📅 {data['datetime']}\n"
        f"📍 {data['location']}\n"
        f"👥 Мест: {data['max_players']}\n"
        f"ID: <b>{training_id}</b>",
        parse_mode="HTML"
    )
    await state.update_data(prev_bot_msg_id=sent.message_id)
    await state.clear()

# === /trainings ===
@dp.message(Command("trainings"))
async def cmd_trainings(message: types.Message):
    async with aiosqlite.connect("hockey.db") as db:
        cursor = await db.execute("""
            SELECT id, datetime, location, max_players FROM trainings ORDER BY datetime
        """)
        rows = await cursor.fetchall()

        if not rows:
            await message.answer("Нет запланированных тренировок.")
            return

        text = "🏒 <b>Ближайшие тренировки:</b>\n\n"
        for row in rows:
            training_id, dt, loc, max_p = row
            reg_cursor = await db.execute("SELECT COUNT(*) FROM registrations WHERE training_id = ?", (training_id,))
            count = (await reg_cursor.fetchone())[0]
            text += f"ID {training_id} | {dt} | {loc} | {count}/{max_p} игроков\n"

        await message.answer(text, parse_mode="HTML")

# === КНОПКА «Тренировки» ===
@dp.callback_query(lambda c: c.data == "trainings")
async def handle_trainings_callback(callback: types.CallbackQuery, state: FSMContext):
    data = await state.get_data()
    prev_id = data.get("prev_bot_msg_id")

    if prev_id:
        await safe_delete(callback.message.chat.id, prev_id)

    async with aiosqlite.connect("hockey.db") as db:
        cursor = await db.execute("""
            SELECT id, datetime, location, max_players FROM trainings ORDER BY datetime
        """)
        rows = await cursor.fetchall()

        if not rows:
            sent = await callback.message.answer("Нет запланированных тренировок.")
        else:
            text = "🏒 <b>Ближайшие тренировки:</b>\n\n"
            for row in rows:
                training_id, dt, loc, max_p = row
                reg_cursor = await db.execute("SELECT COUNT(*) FROM registrations WHERE training_id = ?", (training_id,))
                count = (await reg_cursor.fetchone())[0]
                text += f"ID {training_id} | {dt} | {loc} | {count}/{max_p} игроков\n"

            sent = await callback.message.answer(text, parse_mode="HTML")

        await state.update_data(prev_bot_msg_id=sent.message_id)
    await callback.answer()

# === /squad ===
@dp.message(Command("squad"))
async def show_squad(message: types.Message):
    async with aiosqlite.connect("hockey.db") as db:
        cursor = await db.execute("""
            SELECT first_name, last_name, jersey_number FROM players ORDER BY last_name
        """)
        players = await cursor.fetchall()

        if not players:
            await message.answer("В составе пока никого нет.")
            return

        text = "👥 <b>Состав команды:</b>\n\n"
        for i, (first, last, num) in enumerate(players, 1):
            text += f"{i}. {first} {last} (#{num})\n"

        await message.answer(text, parse_mode="HTML")

# === КНОПКА «Состав» ===
@dp.callback_query(lambda c: c.data == "squad")
async def handle_squad_callback(callback: types.CallbackQuery, state: FSMContext):
    data = await state.get_data()
    prev_id = data.get("prev_bot_msg_id")

    if prev_id:
        await safe_delete(callback.message.chat.id, prev_id)

    async with aiosqlite.connect("hockey.db") as db:
        cursor = await db.execute("""
            SELECT first_name, last_name, jersey_number FROM players ORDER BY last_name
        """)
        players = await cursor.fetchall()

        if not players:
            sent = await callback.message.answer("В составе пока никого нет.")
        else:
            text = "👥 <b>Состав команды:</b>\n\n"
            for i, (first, last, num) in enumerate(players, 1):
                text += f"{i}. {first} {last} (#{num})\n"

            sent = await callback.message.answer(text, parse_mode="HTML")

        await state.update_data(prev_bot_msg_id=sent.message_id)
    await callback.answer()

# === /profile ===
@dp.message(Command("profile"))
async def show_profile(message: types.Message):
    user_id = message.from_user.id
    async with aiosqlite.connect("hockey.db") as db:
        cursor = await db.execute(
            "SELECT first_name, last_name, jersey_number FROM players WHERE user_id = ?", (user_id,)
        )
        player = await cursor.fetchone()
        if player:
            f, l, n = player
            await message.answer(f"👤 <b>Игрок</b>\nИмя: {f}\nФамилия: {l}\nНомер: #{n}", parse_mode="HTML")
            return

        cursor = await db.execute(
            "SELECT first_name, last_name FROM coaches WHERE user_id = ?", (user_id,)
        )
        coach = await cursor.fetchone()
        if coach:
            f, l = coach
            await message.answer(f"👨‍🏫 <b>Тренер</b>\nИмя: {f}\nФамилия: {l}", parse_mode="HTML")
            return

    await message.answer("Ты не зарегистрирован. Напиши /start")

# === КНОПКА «Профиль» ===
@dp.callback_query(lambda c: c.data == "profile")
async def handle_profile_callback(callback: types.CallbackQuery, state: FSMContext):
    data = await state.get_data()
    prev_id = data.get("prev_bot_msg_id")

    if prev_id:
        await safe_delete(callback.message.chat.id, prev_id)

    user_id = callback.from_user.id
    async with aiosqlite.connect("hockey.db") as db:
        cursor = await db.execute(
            "SELECT first_name, last_name, jersey_number FROM players WHERE user_id = ?", (user_id,)
        )
        player = await cursor.fetchone()
        if player:
            f, l, n = player
            sent = await callback.message.answer(f"👤 <b>Игрок</b>\nИмя: {f}\nФамилия: {l}\nНомер: #{n}", parse_mode="HTML")
        else:
            cursor = await db.execute(
                "SELECT first_name, last_name FROM coaches WHERE user_id = ?", (user_id,)
            )
            coach = await cursor.fetchone()
            if coach:
                f, l = coach
                sent = await callback.message.answer(f"👨‍🏫 <b>Тренер</b>\nИмя: {f}\nФамилия: {l}", parse_mode="HTML")
            else:
                sent = await callback.message.answer("Ты не зарегистрирован. Напиши /start")

        await state.update_data(prev_bot_msg_id=sent.message_id)
    await callback.answer()

# === /restart ===
@dp.message(Command("restart"))
async def cmd_restart(message: types.Message, state: FSMContext):
    user_id = message.from_user.id
    async with aiosqlite.connect("hockey.db") as db:
        await db.execute("DELETE FROM players WHERE user_id = ?", (user_id,))
        await db.execute("DELETE FROM coaches WHERE user_id = ?", (user_id,))
        await db.commit()

    await state.clear()
    await safe_delete(message.chat.id, message.message_id)

    sent = await message.answer(
        "🔄 Твой профиль удалён.\n\nПривет! Кто ты?",
        reply_markup=get_role_keyboard()
    )
    await state.update_data(prev_bot_msg_id=sent.message_id)

# === ВСПОМОГАТЕЛЬНАЯ ФУНКЦИЯ ===
async def is_coach(user_id: int) -> bool:
    async with aiosqlite.connect("hockey.db") as db:
        cursor = await db.execute("SELECT 1 FROM coaches WHERE user_id = ?", (user_id,))
        row = await cursor.fetchone()
        return row is not None

# === УНИВЕРСАЛЬНЫЙ ОБРАБОТЧИК ===
@dp.message()
async def fallback_handler(message: types.Message, state: FSMContext):
    current_state = await state.get_state()
    if current_state is not None:
        await state.clear()
        await safe_delete(message.chat.id, message.message_id)

        sent = await message.answer(
            "⚠️ Произошла ошибка. Давай начнём заново.\n\n"
            "Напиши /start или выбери роль:",
            reply_markup=get_role_keyboard()
        )
        await state.update_data(prev_bot_msg_id=sent.message_id)
    else:
        await message.answer(
            "Пожалуйста, используй команды:\n/start — начать\n/restart — сбросить профиль"
        )

# === MAIN ===
async def main():
    await init_db()
    print("✅ Бот запущен!")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())