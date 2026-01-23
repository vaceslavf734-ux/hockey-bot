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

    # Удаление события
    waiting_for_event_id_to_delete = State()
    confirming_deletion = State()  # Подтверждение удаления

# === Инициализация бота ===
bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()

# === Вспомогательные функции ===

async def safe_delete(chat_id: int, message_id: int):
    """Безопасное удаление сообщения (игнорирует ошибки)"""
    try:
        await bot.delete_message(chat_id, message_id)
    except Exception:
        pass

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
                type TEXT NOT NULL,
                datetime TEXT NOT NULL,
                location TEXT NOT NULL,
                created_by INTEGER
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
            [KeyboardButton(text="📋 Мои события")],
            [KeyboardButton(text="🗑 Удалить событие")],
            [KeyboardButton(text="👥 Состав")]
        ],
        resize_keyboard=True,
        one_time_keyboard=False
    )

def parse_datetime_input(text: str):
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

async def get_coach_events(user_id: int):
    async with aiosqlite.connect(DATABASE) as db:
        cursor = await db.execute("""
            SELECT id, type, datetime, location
            FROM events
            WHERE created_by = ?
            ORDER BY datetime
        """, (user_id,))
        return await cursor.fetchall()

async def delete_event_by_id(event_id: int, user_id: int) -> bool:
    async with aiosqlite.connect(DATABASE) as db:
        cursor = await db.execute("""
            DELETE FROM events
            WHERE id = ? AND created_by = ?
        """, (event_id, user_id))
        await db.commit()
        return cursor.rowcount > 0

async def get_event_by_id(event_id: int, user_id: int):
    async with aiosqlite.connect(DATABASE) as db:
        cursor = await db.execute("""
            SELECT type, datetime, location
            FROM events
            WHERE id = ? AND created_by = ?
        """, (event_id, user_id))
        row = await cursor.fetchone()
        return row

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
        await message.answer("Функционал игрока пока не готов.")
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
        await message.answer("Ошибка: введите хотя бы два слова.")
        return
    await message.answer("✅ Профиль тренера создан!", reply_markup=get_coach_menu())
    await state.set_state(UserStates.coach_menu)

# === Меню тренера ===

@dp.message(UserStates.coach_menu)
async def handle_coach_menu(message: types.Message, state: FSMContext):
    text = message.text
    if text == "🏒 Создать тренировку":
        await state.update_data(event_type="training")
        sent = await message.answer("📅 Введите дату и время тренировки:\n`ДД ММ ГГГГ ЧЧ:ММ`\nНапример: `12 12 2025 18:00`", parse_mode="Markdown")
        await state.update_data(prev_bot_msg_id=sent.message_id)
        await state.set_state(UserStates.waiting_for_event_datetime)
    elif text == "🎮 Создать игру":
        await state.update_data(event_type="game")
        sent = await message.answer("📅 Введите дату и время игры:\n`ДД ММ ГГГГ ЧЧ:ММ`\nНапример: `15 12 2025 19:30`", parse_mode="Markdown")
        await state.update_data(prev_bot_msg_id=sent.message_id)
        await state.set_state(UserStates.waiting_for_event_datetime)
    elif text == "📋 Мои события":
        events = await get_coach_events(message.from_user.id)
        if not events:
            await message.answer("У вас нет созданных событий.")
        else:
            lines = []
            for eid, etype, dt, loc in events:
                label = "🏒 Тренировка" if etype == "training" else "🎮 Игра"
                lines.append(f"ID {eid}\n{label}\n📅 {dt}\n📍 {loc}\n")
            await message.answer("Ваши события:\n\n" + "\n".join(lines))
    elif text == "🗑 Удалить событие":
        events = await get_coach_events(message.from_user.id)
        if not events:
            await message.answer("Нет событий для удаления.")
            return
        lines = [f"ID {eid}: {'Тренировка' if t=='training' else 'Игра'} ({dt})" for eid, t, dt, _ in events]
        sent = await message.answer(
            "Введите ID события для удаления:\n\n" + "\n".join(lines) +
            "\n\nОтмена: /cancel"
        )
        await state.update_data(prev_bot_msg_id=sent.message_id)
        await state.set_state(UserStates.waiting_for_event_id_to_delete)
    elif text == "👥 Состав":
        await message.answer("Состав (в разработке)...")
    else:
        await message.answer("Используйте кнопки меню.")

# === Создание события (минималистично) ===

@dp.message(UserStates.waiting_for_event_datetime)
async def handle_event_datetime(message: types.Message, state: FSMContext):
    data = await state.get_data()
    prev_id = data.get("prev_bot_msg_id")
    if prev_id:
        await safe_delete(message.chat.id, prev_id)

    parsed = parse_datetime_input(message.text)
    if not parsed:
        sent = await message.answer("❌ Неверный формат.\nПопробуйте: `ДД ММ ГГГГ ЧЧ:ММ`", parse_mode="Markdown")
        await state.update_data(prev_bot_msg_id=sent.message_id)
        return

    await state.update_data(event_datetime=parsed)
    sent = await message.answer("📍 Укажите место проведения:")
    await state.update_data(prev_bot_msg_id=sent.message_id)
    await state.set_state(UserStates.waiting_for_event_location)

@dp.message(UserStates.waiting_for_event_location)
async def handle_event_location(message: types.Message, state: FSMContext):
    data = await state.get_data()
    prev_id = data.get("prev_bot_msg_id")
    if prev_id:
        await safe_delete(message.chat.id, prev_id)

    location = message.text.strip()
    if len(location) < 3:
        sent = await message.answer("❌ Слишком короткое название. Попробуйте снова.")
        await state.update_data(prev_bot_msg_id=sent.message_id)
        return

    event_type = data["event_type"]
    event_datetime = data["event_datetime"]
    user_id = message.from_user.id

    async with aiosqlite.connect(DATABASE) as db:
        await db.execute("""
            INSERT INTO events (type, datetime, location, created_by)
            VALUES (?, ?, ?, ?)
        """, (event_type, event_datetime, location, user_id))
        await db.commit()

    label = "тренировка" if event_type == "training" else "игра"
    sent = await message.answer(f"✅ {label.capitalize()} создана!\n📅 {event_datetime}\n📍 {location}", reply_markup=get_coach_menu())
    await state.update_data(prev_bot_msg_id=sent.message_id)
    await state.set_state(UserStates.coach_menu)

# === Удаление события с подтверждением ===

@dp.message(UserStates.waiting_for_event_id_to_delete)
async def handle_delete_event_id(message: types.Message, state: FSMContext):
    data = await state.get_data()
    prev_id = data.get("prev_bot_msg_id")
    if prev_id:
        await safe_delete(message.chat.id, prev_id)

    if not message.text.isdigit():
        sent = await message.answer("❌ Введите число (ID события). Отмена: /cancel")
        await state.update_data(prev_bot_msg_id=sent.message_id)
        return

    event_id = int(message.text)
    event_info = await get_event_by_id(event_id, message.from_user.id)
    if not event_info:
        sent = await message.answer("❌ Событие не найдено или у вас нет прав на его удаление.", reply_markup=get_coach_menu())
        await state.update_data(prev_bot_msg_id=sent.message_id)
        await state.set_state(UserStates.coach_menu)
        return

    etype, dt, loc = event_info
    label = "Тренировка" if etype == "training" else "Игра"
    confirm_text = f"⚠️ Вы действительно хотите удалить:\n{label} ({dt})\n📍 {loc}\n\nОтветьте: да / нет"

    sent = await message.answer(confirm_text)
    await state.update_data(event_id_to_delete=event_id, prev_bot_msg_id=sent.message_id)
    await state.set_state(UserStates.confirming_deletion)

@dp.message(UserStates.confirming_deletion)
async def handle_confirm_deletion(message: types.Message, state: FSMContext):
    data = await state.get_data()
    prev_id = data.get("prev_bot_msg_id")
    if prev_id:
        await safe_delete(message.chat.id, prev_id)

    text = message.text.strip().lower()
    if text in ["да", "yes", "y"]:
        event_id = data["event_id_to_delete"]
        success = await delete_event_by_id(event_id, message.from_user.id)
        if success:
            sent = await message.answer("✅ Событие удалено.", reply_markup=get_coach_menu())
        else:
            sent = await message.answer("❌ Ошибка при удалении.", reply_markup=get_coach_menu())
    elif text in ["нет", "no", "n"]:
        sent = await message.answer("❌ Удаление отменено.", reply_markup=get_coach_menu())
    else:
        sent = await message.answer("Пожалуйста, ответьте: да или нет.", reply_markup=get_coach_menu())

    await state.update_data(prev_bot_msg_id=sent.message_id)
    await state.set_state(UserStates.coach_menu)

# === Отмена ===

@dp.message(Command("cancel"))
async def cmd_cancel(message: types.Message, state: FSMContext):
    current_state = await state.get_state()
    if current_state and ("waiting_for_event" in current_state or "waiting_for_event_id" in current_state or "confirming_deletion" in current_state):
        await message.answer("❌ Действие отменено.", reply_markup=get_coach_menu())
        await state.set_state(UserStates.coach_menu)
    else:
        await message.answer("Нечего отменять.")

@dp.message(Command("restart"))
async def cmd_restart(message: types.Message, state: FSMContext):
    user_id = message.from_user.id
    await reset_user_profile(user_id)
    await state.clear()
    await message.answer("Профиль сброшен. Нажмите /start.")

# === Запуск ===
async def main():
    await init_db()
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())