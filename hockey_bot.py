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
    first_name = State()
    last_name = State()

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

# === /start ===
@dp.message(Command("start"))
async def cmd_start(message: types.Message, state: FSMContext):
    user_id = message.from_user.id
    async with aiosqlite.connect("hockey.db") as db:
        cursor = await db.execute("SELECT 1 FROM players WHERE user_id = ?", (user_id,))
        player = await cursor.fetchone()
        cursor = await db.execute("SELECT 1 FROM coaches WHERE user_id = ?", (user_id,))
        coach = await cursor.fetchone()

        if player:
            await show_profile(message)
        elif coach:
            await message.answer("Ты тренер! Используй /new_training чтобы создать тренировку.")
        else:
            # Отправляем кнопки
            sent = await message.answer(
                "Привет! Кто ты?",
                reply_markup=get_role_keyboard()
            )
            await state.update_data(prev_bot_msg_id=sent.message_id)

# === Обработка нажатия кнопок ===
@dp.callback_query(lambda c: c.data in ["role_player", "role_coach"])
async def handle_role_choice(callback: types.CallbackQuery, state: FSMContext):
    data = await state.get_data()
    prev_id = data.get("prev_bot_msg_id")

    if callback.data == "role_player":
        sent = await callback.message.answer(
            "📝 Введи своё имя, фамилию и хоккейный номер через пробел:\n\n"
            "<code>Слава Федоров 19</code>",
            parse_mode="HTML"
        )
        await state.update_data(prev_bot_msg_id=sent.message_id)
        await state.set_state(PlayerRegistration.full_name_and_number)
    else:  # role_coach
        sent = await callback.message.answer("🔐 Введи пароль тренера:")
        await state.update_data(prev_bot_msg_id=sent.message_id)
        await state.set_state(CoachRegistration.password)

    await callback.answer()

# === Обработка текста до выбора роли ===
@dp.message(~Command("start"), ~Command("restart"), ~Command("profile"), ~Command("trainings"), ~Command("join"), ~Command("new_training"))
async def handle_text_before_role_selection(message: types.Message, state: FSMContext):
    current_state = await state.get_state()
    if current_state is None:
        sent = await message.answer(
            "Пожалуйста, выбери свою роль с помощью кнопок 👇",
            reply_markup=get_role_keyboard()
        )
        await state.update_data(prev_bot_msg_id=sent.message_id)

# === РЕГИСТРАЦИЯ ИГРОКА ===
@dp.message(PlayerRegistration.full_name_and_number)
async def process_full_name_and_number(message: types.Message, state: FSMContext):
    data = await state.get_data()
    prev_id = data.get("prev_bot_msg_id")

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

    await show_profile(message)
    await state.clear()

# === РЕГИСТРАЦИЯ ТРЕНЕРА ===
@dp.message(CoachRegistration.password)
async def process_coach_password(message: types.Message, state: FSMContext):
    data = await state.get_data()
    prev_id = data.get("prev_bot_msg_id")

    if message.text.strip() != COACH_PASSWORD:
        sent = await message.answer("❌ Неверный пароль. Попробуй снова или напиши /iamcoach.")
        await state.update_data(prev_bot_msg_id=sent.message_id)
        return

    sent = await message.answer("✅ Пароль верный!\nКак тебя зовут? (имя)")
    await state.update_data(prev_bot_msg_id=sent.message_id)
    await state.set_state(CoachRegistration.first_name)

@dp.message(CoachRegistration.first_name)
async def process_coach_first_name(message: types.Message, state: FSMContext):
    data = await state.get_data()
    prev_id = data.get("prev_bot_msg_id")
    await state.update_data(first_name=message.text.strip())
    sent = await message.answer("А фамилия?")
    await state.update_data(prev_bot_msg_id=sent.message_id)
    await state.set_state(CoachRegistration.last_name)

@dp.message(CoachRegistration.last_name)
async def process_coach_last_name(message: types.Message, state: FSMContext):
    data = await state.get_data()
    prev_id = data.get("prev_bot_msg_id")

    user_id = message.from_user.id
    first = data["first_name"]
    last = message.text.strip()

    async with aiosqlite.connect("hockey.db") as db:
        await db.execute(
            "INSERT INTO coaches (user_id, first_name, last_name) VALUES (?, ?, ?)",
            (user_id, first, last)
        )
        await db.commit()

    await message.answer(f"✅ Добро пожаловать, тренер {first} {last}!\nТеперь ты можешь создавать тренировки через /new_training.")
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
    await state.update_data(location=message.text.strip())
    sent = await message.answer("👥 Максимальное число игроков (например: 20)")
    await state.update_data(prev_bot_msg_id=sent.message_id)
    await state.set_state(NewTraining.max_players)

@dp.message(NewTraining.max_players)
async def process_training_max_players(message: types.Message, state: FSMContext):
    data = await state.get_data()
    prev_id = data.get("prev_bot_msg_id")
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

    await message.answer(
        f"✅ Тренировка создана!\n\n"
        f"📅 {data['datetime']}\n"
        f"📍 {data['location']}\n"
        f"👥 Мест: {data['max_players']}\n"
        f"ID: <b>{training_id}</b>",
        parse_mode="HTML"
    )
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
            text += f"ID: {training_id} | {dt} | {loc} | {count}/{max_p} игроков\n"

        await message.answer(text, parse_mode="HTML")

# === /join ===
@dp.message(Command("join"))
async def cmd_join(message: types.Message):
    args = message.text.split()
    if len(args) != 2 or not args[1].isdigit():
        await message.answer("Используй: /join <ID_тренировки>")
        return

    training_id = int(args[1])
    user_id = message.from_user.id

    async with aiosqlite.connect("hockey.db") as db:
        cursor = await db.execute("SELECT 1 FROM players WHERE user_id = ?", (user_id,))
        player = await cursor.fetchone()
        if not player:
            await message.answer("Ты должен быть зарегистрирован как игрок. Напиши /start")
            return

        cursor = await db.execute("SELECT max_players FROM trainings WHERE id = ?", (training_id,))
        tr = await cursor.fetchone()
        if not tr:
            await message.answer("Тренировка с таким ID не найдена.")
            return

        max_players = tr[0]
        cursor = await db.execute("SELECT COUNT(*) FROM registrations WHERE training_id = ?", (training_id,))
        current_count = (await cursor.fetchone())[0]

        if current_count >= max_players:
            await message.answer("❌ На этой тренировке уже нет мест.")
            return

        try:
            await db.execute("INSERT INTO registrations (user_id, training_id) VALUES (?, ?)", (user_id, training_id))
            await db.commit()
            await message.answer(f"✅ Ты записан на тренировку ID {training_id}!")
        except aiosqlite.IntegrityError:
            await message.answer("Ты уже записан на эту тренировку.")

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

# === /restart ===
@dp.message(Command("restart"))
async def cmd_restart(message: types.Message, state: FSMContext):
    user_id = message.from_user.id
    async with aiosqlite.connect("hockey.db") as db:
        await db.execute("DELETE FROM players WHERE user_id = ?", (user_id,))
        await db.execute("DELETE FROM coaches WHERE user_id = ?", (user_id,))
        await db.commit()
    await state.clear()
    sent = await message.answer(
        "Привет! Кто ты?",
        reply_markup=get_role_keyboard()
    )
    await state.update_data(prev_bot_msg_id=sent.message_id)

# === MAIN ===
async def main():
    await init_db()
    print("✅ Бот запущен!")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())