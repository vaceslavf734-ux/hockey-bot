import asyncio
from aiogram import Bot, Dispatcher, types
from aiogram.filters import Command
from aiogram.types import ReplyKeyboardMarkup, KeyboardButton
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import StatesGroup, State
import aiosqlite
import re

# === Конфигурация ===
BOT_TOKEN = "8194198392:AAFjEcdDbJw8ev8NKRYM5lOqyKwg-dN4eCs"
DATABASE = "hockey.db"
COACH_PASSWORD = "1234"

# === FSM Состояния ===
class UserStates(StatesGroup):
    waiting_for_role = State()
    waiting_for_coach_password = State()
    waiting_for_coach_name = State()
    coach_menu = State()  # состояние активного меню тренера

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
        one_time_keyboard=False  # Кнопки остаются в чате
    )

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
        # TODO: реализация игрока позже
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

# Меню тренера — обработка кнопок
@dp.message(UserStates.coach_menu)
async def handle_coach_menu(message: types.Message, state: FSMContext):
    if message.text == "🏒 Создать тренировку":
        await message.answer("Создание тренировки (в разработке)...")
    elif message.text == "🎮 Создать игру":
        await message.answer("Создание игры (в разработке)...")
    elif message.text == "👥 Состав":
        await message.answer("Просмотр состава (в разработке)...")
    else:
        await message.answer("Используйте кнопки меню.")

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