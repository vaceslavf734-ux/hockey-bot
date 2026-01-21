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
            await message.answer(
                "Привет! Кто ты?",
                reply_markup=get_role_keyboard()
            )

# === Обработка нажатия кнопок ===
@dp.callback_query(lambda c: c.data in ["role_player", "role_coach"])
async def handle_role_choice(callback: types.CallbackQuery, state: FSMContext):
    if callback.data == "role_player":
        await callback.message.answer(
            "📝 Введи своё имя, фамилию и хоккейный номер через пробел:\n\n"
            "<code>Слава Федоров 19</code>",
            parse_mode="HTML"
        )
        await state.set_state(PlayerRegistration.full_name_and_number)
    else:
        await callback.message.answer("🔐 Введи пароль тренера:")
        await state.set_state(CoachRegistration.password)

    await callback.answer()

# === Обработка текста до выбора роли ===
@dp.message(~Command("start"), ~Command("restart"), ~Command("profile"), ~Command("trainings"), ~Command("join"), ~Command("new_training"))
async def handle_text_before_role_selection(message: types.Message, state: FSMContext):
    current_state = await state.get_state()
    if current_state is None:
        await message.answer(
            "Пожалуйста, выбери свою роль с помощью кнопок 👇",
            reply_markup=get_role_keyboard()
        )

# === РЕГИСТРАЦИЯ ИГРОКА ===
@dp.message(PlayerRegistration.full_name_and_number)
async def process_full_name_and_number(message: types.Message, state: FSMContext):
    text = message.text.strip().split()
    if len(text) < 2:
        await message.answer(
            "❌ Неверный формат.\n\n"
            "Напиши: <code>Имя Фамилия Номер</code>\n"
            "Пример: <code>Слава Федоров 19</code>",
            parse_mode="HTML"
        )
        return

    number = text[-1]
    if not number.isdigit():
        await message.answer("❌ Номер должен быть числом (например: 19).")
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
    if message.text.strip() != COACH_PASSWORD:
        await message.answer("❌ Неверный пароль. Попробуй снова или напиши /iamcoach.")
        return

    await message.answer("✅ Пароль верный!\nКак тебя зовут? (имя)")
    await state.set_state(CoachRegistration.first_name)

@dp.message(CoachRegistration.first_name)
async def process_coach_first_name(message: types.Message, state: FSMContext):
    await state.update_data(first_name=message.text.strip())
    await message.answer("А фамилия?")
    await state.set_state(CoachRegistration.last_name)

@dp.message(CoachRegistration.last_name)
async def process_coach_last_name(message: types.Message, state: FSMContext):
    data = await state.get_data()
    first = data["first_name"]
    last = message.text.strip()
    user_id = message.from_user.id

    async with aiosqlite.connect("hockey.db") as db:
        await db.execute(
            "INSERT INTO coaches (user_id, first_name, last_name) VALUES (?, ?, ?)",
            (user_id, first, last)
        )
        await db.commit()

    await message.answer(f"✅ Добро пожаловать, тренер {first} {last}!\nТеперь ты можешь создавать тренировки через /new_training.")
    await state.clear()

# === ОСТАЛЬНЫЕ КОМАНДЫ (/new_training, /trainings, /join, /profile) ===
# ... (оставь их как есть — они уже работают)

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

# === /restart — ПОЛНЫЙ СБРОС ===
@dp.message(Command("restart"))
async def cmd_restart(message: types.Message, state: FSMContext):
    user_id = message.from_user.id

    async with aiosqlite.connect("hockey.db") as db:
        await db.execute("DELETE FROM players WHERE user_id = ?", (user_id,))
        await db.execute("DELETE FROM coaches WHERE user_id = ?", (user_id,))
        await db.commit()

    await state.clear()

    await message.answer(
        "🔄 Твой профиль удалён.\n\nПривет! Кто ты?",
        reply_markup=get_role_keyboard()
    )

# === MAIN ===
async def main():
    await init_db()
    print("✅ Бот запущен!")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())