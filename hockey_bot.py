import asyncio
from aiogram import Bot, Dispatcher, types
from aiogram.filters import Command
from aiogram.types import ReplyKeyboardMarkup, KeyboardButton
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import StatesGroup, State
import aiosqlite
import re
from datetime import datetime

# === Конфигурация ===
BOT_TOKEN = "8194198392:AAFjEcdDbJw8ev8NKRYM5lOqyKwg-dN4eCs"
DATABASE = "hockey.db"
COACH_PASSWORD = "1234"

# === FSM Состояния ===
class UserStates(StatesGroup):
    waiting_for_role = State()
    waiting_for_coach_password = State()
    waiting_for_coach_name = State()
    coach_menu = State()

    # Создание события
    waiting_for_event_datetime = State()
    waiting_for_event_location = State()
    event_type = State()  # будет хранить 'training' или 'game'

# === Инициализация бота ===
bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()

# === Вспомогательные функции ===

async def init_db():
    async with aiosqlite.connect(DATABASE) as db:
        await db.execute("""
            CREATE TABLE IF NOT EXISTS users (
                user_id INTEGER PRIMARY KEY,
                role TEXT,
                name TEXT,
                surname TEXT
            )
        """)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                type TEXT NOT NULL,          -- 'training' или 'game'
                datetime TEXT NOT NULL,      -- ISO формат: YYYY-MM-DD HH:MM
                location TEXT NOT NULL,
                created_by INTEGER           -- user_id тренера
            )
        """)
        await db.commit()

async def reset_user_profile(user_id: int):
    async with aiosqlite.connect(DATABASE) as db:
        await db.execute("DELETE FROM users WHERE user_id = ?", (user_id,))
        await db.commit()

async def save_coach_name(user_id: int, full_name: str):
    parts = full_name.strip().split()
    if len(parts) < 2:
        return False
    name, surname = parts[0], " ".join(parts[1:])
    async with aiosqlite.connect(DATABASE) as db:
        await db.execute("""
            INSERT OR REPLACE INTO users (user_id, role, name, surname)
            VALUES (?, 'coach', ?, ?)
        """, (user_id, name, surname))
        await db.commit()
    return True

def get_coach_menu():
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="🏒 Создать тренировку")],
            [KeyboardButton(text="🎮 Создать игру")],
            [KeyboardButton(text="👥 Состав")]
        ],
        resize_keyboard=True,
        one_time_keyboard=False
    )

def parse_datetime_input(text: str):
    """Преобразует '12 12 2025 18:00' → '2025-12-12 18:00'"""
    pattern = r"(\d{1,2})\s+(\d{1,2})\s+(\d{4})\s+(\d{1,2}):(\d{2})"
    match = re.fullmatch(pattern, text.strip())
    if not match:
        return None
    day, month, year, hour, minute = map(int, match.groups())
    try:
        dt = datetime(year, month, day, hour, minute)
        return dt.strftime("%Y-%m-%d %H:%M")
    except ValueError:
        return None

# === Обработчики ===

@dp.message(Command("start"))
async def cmd_start(message: types.Message, state: FSMContext):
    await state.clear()
    markup = ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text="Старт")]],
        resize_keyboard=True,
        one_time_keyboard=True
    )
    await message.answer("Привет! Нажми кнопку 'Старт', чтобы начать.", reply_markup=markup)

@dp.message(lambda msg: msg.text == "Старт")
async def handle_start_button(message: types.Message, state: FSMContext):
    markup = ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="Я игрок"), KeyboardButton(text="Я тренер")]
        ],
        resize_keyboard=True,
        one_time_keyboard=True
    )
    await message.answer("Выбери свою роль:", reply_markup=markup)
    await state.set_state(UserStates.waiting_for_role)

@dp.message(UserStates.waiting_for_role)
async def handle_role_selection(message: types.Message, state: FSMContext):
    if message.text == "Я игрок":
        await message.answer("Функционал игрока пока не готов. Выбери 'Я тренер' для тестирования.")
        return
    elif message.text == "Я тренер":
        await message.answer("Введите пароль тренера:")
        await state.set_state(UserStates.waiting_for_coach_password)
    else:
        await message.answer("Пожалуйста, выбери одну из кнопок.")

@dp.message(UserStates.waiting_for_coach_password)
async def handle_coach_password(message: types.Message, state: FSMContext):
    if message.text.strip() == COACH_PASSWORD:
        await message.answer("✅ Пароль верный!\nТеперь введите ваше имя и фамилию (например: Иван Петров):")
        await state.set_state(UserStates.waiting_for_coach_name)
    else:
        await message.answer("❌ Неверный пароль. Попробуйте снова или нажмите /start.")

@dp.message(UserStates.waiting_for_coach_name)
async def handle_coach_name(message: types.Message, state: FSMContext):
    if not re.fullmatch(r"[А-Яа-яЁё]+(?:\s+[А-Яа-яЁё]+)+", message.text.strip()):
        await message.answer("Пожалуйста, введите имя и фамилию через пробел (только буквы). Пример: Иван Петров")
        return
    success = await save_coach_name(message.from_user.id, message.text)
    if not success:
        await message.answer("Ошибка: введите хотя бы два слова (имя и фамилию).")
        return
    await message.answer("✅ Профиль тренера создан!", reply_markup=get_coach_menu())
    await state.set_state(UserStates.coach_menu)

# === Создание тренировки / игры ===

@dp.message(UserStates.coach_menu)
async def handle_coach_menu(message: types.Message, state: FSMContext):
    if message.text == "🏒 Создать тренировку":
        await state.update_data(event_type="training")
        await message.answer("📅 Введите дату и время тренировки в формате:\n`ДД ММ ГГГГ ЧЧ:ММ`\nНапример: `12 12 2025 18:00`", parse_mode="Markdown")
        await state.set_state(UserStates.waiting_for_event_datetime)
    elif message.text == "🎮 Создать игру":
        await state.update_data(event_type="game")
        await message.answer("📅 Введите дату и время игры в формате:\n`ДД ММ ГГГГ ЧЧ:ММ`\nНапример: `15 12 2025 19:30`", parse_mode="Markdown")
        await state.set_state(UserStates.waiting_for_event_datetime)
    elif message.text == "👥 Состав":
        await message.answer("Просмотр состава (в разработке)...")
    else:
        await message.answer("Используйте кнопки меню.")

@dp.message(UserStates.waiting_for_event_datetime)
async def handle_event_datetime(message: types.Message, state: FSMContext):
    parsed = parse_datetime_input(message.text)
    if not parsed:
        await message.answer("❌ Неверный формат.\nПопробуйте снова: `ДД ММ ГГГГ ЧЧ:ММ` (например: `12 12 2025 18:00`)", parse_mode="Markdown")
        return
    await state.update_data(event_datetime=parsed)
    await message.answer("📍 Укажите место проведения:")
    await state.set_state(UserStates.waiting_for_event_location)

@dp.message(UserStates.waiting_for_event_location)
async def handle_event_location(message: types.Message, state: FSMContext):
    location = message.text.strip()
    if len(location) < 3:
        await message.answer("❌ Название места слишком короткое. Попробуйте снова.")
        return

    data = await state.get_data()
    event_type = data["event_type"]
    event_datetime = data["event_datetime"]
    user_id = message.from_user.id

    async with aiosqlite.connect(DATABASE) as db:
        await db.execute("""
            INSERT INTO events (type, datetime, location, created_by)
            VALUES (?, ?, ?, ?)
        """, (event_type, event_datetime, location, user_id))
        await db.commit()

    event_label = "тренировка" if event_type == "training" else "игра"
    await message.answer(f"✅ {event_label.capitalize()} создана!\n📅 {event_datetime}\n📍 {location}", reply_markup=get_coach_menu())
    await state.set_state(UserStates.coach_menu)

# Команда отмены (опционально)
@dp.message(Command("cancel"))
async def cmd_cancel(message: types.Message, state: FSMContext):
    current_state = await state.get_state()
    if current_state and "waiting_for_event" in current_state:
        await message.answer("❌ Отменено. Вернитесь в меню.", reply_markup=get_coach_menu())
        await state.set_state(UserStates.coach_menu)
    else:
        await message.answer("Нечего отменять.")

@dp.message(Command("restart"))
async def cmd_restart(message: types.Message, state: FSMContext):
    user_id = message.from_user.id
    await reset_user_profile(user_id)
    await state.clear()
    await message.answer("Твой профиль сброшен. Нажми /start, чтобы начать заново.")

# === Запуск ===
async def main():
    await init_db()
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())