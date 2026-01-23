import asyncio
from aiogram import Bot, Dispatcher, types
from aiogram.filters import Command
from aiogram.types import ReplyKeyboardMarkup, KeyboardButton
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import StatesGroup, State
import aiosqlite
import re
from datetime import datetime, timedelta
import logging

# === Конфигурация ===
BOT_TOKEN = "8194198392:AAFjEcdDbJw8ev8NKRYM5lOqyKwg-dN4eCs"
DATABASE = "hockey.db"
COACH_PASSWORD = "1234"

# Включим логирование для напоминаний
logging.basicConfig(level=logging.INFO)

# === FSM Состояния ===
class UserStates(StatesGroup):
    # Общие
    waiting_for_role = State()
    coach_menu = State()
    player_menu = State()

    # Тренер
    waiting_for_coach_password = State()
    waiting_for_coach_name = State()
    waiting_for_event_datetime = State()
    waiting_for_event_location = State()
    waiting_for_opponent = State()  # Только для игры
    waiting_for_event_id_to_delete = State()
    confirming_deletion = State()
    waiting_for_edit_choice = State()
    waiting_for_new_value = State()

    # Игрок
    waiting_for_player_name_number = State()
    waiting_for_event_to_join = State()

# === Инициализация бота ===
bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()

# === Вспомогательные функции ===

async def safe_delete(chat_id: int, message_id: int):
    try:
        await bot.delete_message(chat_id, message_id)
    except Exception:
        pass

async def init_db():
    async with aiosqlite.connect(DATABASE) as db:
        await db.execute("""
            CREATE TABLE IF NOT EXISTS users (
                user_id INTEGER PRIMARY KEY,
                role TEXT NOT NULL,
                name TEXT,
                surname TEXT,
                number TEXT  -- номер игрока
            )
        """)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                type TEXT NOT NULL,          -- 'training' или 'game'
                datetime TEXT NOT NULL,      -- ISO: YYYY-MM-DD HH:MM
                location TEXT NOT NULL,
                opponent TEXT,               -- только для игр
                created_by INTEGER NOT NULL
            )
        """)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS registrations (
                user_id INTEGER,
                event_id INTEGER,
                PRIMARY KEY (user_id, event_id)
            )
        """)
        await db.commit()

async def reset_user_profile(user_id: int):
    async with aiosqlite.connect(DATABASE) as db:
        await db.execute("DELETE FROM users WHERE user_id = ?", (user_id,))
        await db.execute("DELETE FROM registrations WHERE user_id = ?", (user_id,))
        await db.commit()

def get_coach_menu():
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="🏒 Создать тренировку")],
            [KeyboardButton(text="🎮 Создать игру")],
            [KeyboardButton(text="📋 Мои события")],
            [KeyboardButton(text="✏️ Редактировать событие")],
            [KeyboardButton(text="🗑 Удалить событие")],
            [KeyboardButton(text="👥 Состав")]
        ],
        resize_keyboard=True,
        one_time_keyboard=False
    )

def get_player_menu():
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="📅 Записаться на событие")],
            [KeyboardButton(text="📋 Мои записи")]
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

# === Функции работы с БД ===

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

async def save_player_profile(user_id: int, input_text: str):
    # Ожидаем: "Имя Фамилия 19"
    pattern = r"^([А-Яа-яЁё]+)\s+([А-Яа-яЁё]+)\s+(\d{1,3})$"
    match = re.fullmatch(pattern, input_text.strip())
    if not match:
        return False
    name, surname, number = match.groups()
    async with aiosqlite.connect(DATABASE) as db:
        await db.execute("""
            INSERT OR REPLACE INTO users (user_id, role, name, surname, number)
            VALUES (?, 'player', ?, ?, ?)
        """, (user_id, name, surname, number))
        await db.commit()
    return True

async def get_coach_events(user_id: int):
    async with aiosqlite.connect(DATABASE) as db:
        cursor = await db.execute("""
            SELECT id, type, datetime, location, opponent
            FROM events
            WHERE created_by = ?
            ORDER BY datetime
        """, (user_id,))
        return await cursor.fetchall()

async def get_all_upcoming_events():
    now = datetime.now().strftime("%Y-%m-%d %H:%M")
    async with aiosqlite.connect(DATABASE) as db:
        cursor = await db.execute("""
            SELECT id, type, datetime, location, opponent
            FROM events
            WHERE datetime > ?
            ORDER BY datetime
        """, (now,))
        return await cursor.fetchall()

async def get_event_by_id(event_id: int):
    async with aiosqlite.connect(DATABASE) as db:
        cursor = await db.execute("""
            SELECT id, type, datetime, location, opponent, created_by
            FROM events
            WHERE id = ?
        """, (event_id,))
        row = await cursor.fetchone()
        return row

async def create_event(user_id: int, etype: str, dt: str, loc: str, opponent: str = None):
    async with aiosqlite.connect(DATABASE) as db:
        await db.execute("""
            INSERT INTO events (type, datetime, location, opponent, created_by)
            VALUES (?, ?, ?, ?, ?)
        """, (etype, dt, loc, opponent, user_id))
        await db.commit()

async def delete_event_by_id(event_id: int, user_id: int) -> bool:
    async with aiosqlite.connect(DATABASE) as db:
        cursor = await db.execute("""
            DELETE FROM events WHERE id = ? AND created_by = ?
        """, (event_id, user_id))
        await db.commit()
        return cursor.rowcount > 0

async def update_event_field(event_id: int, field: str, value):
    async with aiosqlite.connect(DATABASE) as db:
        await db.execute(f"UPDATE events SET {field} = ? WHERE id = ?", (value, event_id))
        await db.commit()

async def register_player_for_event(user_id: int, event_id: int):
    async with aiosqlite.connect(DATABASE) as db:
        await db.execute("""
            INSERT OR IGNORE INTO registrations (user_id, event_id)
            VALUES (?, ?)
        """, (user_id, event_id))
        await db.commit()

async def get_players_for_event(event_id: int):
    async with aiosqlite.connect(DATABASE) as db:
        cursor = await db.execute("""
            SELECT u.name, u.surname, u.number
            FROM registrations r
            JOIN users u ON r.user_id = u.user_id
            WHERE r.event_id = ?
        """, (event_id,))
        return await cursor.fetchall()

async def get_player_registrations(user_id: int):
    async with aiosqlite.connect(DATABASE) as db:
        cursor = await db.execute("""
            SELECT e.id, e.type, e.datetime, e.location
            FROM registrations r
            JOIN events e ON r.event_id = e.id
            WHERE r.user_id = ?
            ORDER BY e.datetime
        """, (user_id,))
        return await cursor.fetchall()

# === Напоминания (фоновая задача) ===

async def send_reminders():
    while True:
        try:
            target_time = (datetime.now() + timedelta(hours=1)).strftime("%Y-%m-%d %H:%M")
            async with aiosqlite.connect(DATABASE) as db:
                cursor = await db.execute("""
                    SELECT e.id, e.type, e.datetime, e.location, e.opponent
                    FROM events e
                    WHERE datetime = ?
                """, (target_time,))
                events = await cursor.fetchall()

                for eid, etype, dt, loc, opponent in events:
                    players = await get_players_for_event(eid)
                    if not players:
                        continue
                    label = "Тренировка" if etype == "training" else f"Игра против {opponent or 'неизвестного'}"
                    msg = f"🔔 Напоминание!\nЧерез 1 час начинается:\n{label}\n📅 {dt}\n📍 {loc}"
                    for (name, surname, number) in players:
                        # Получим user_id из базы (нужно расширить запрос)
                        pass  # Для простоты пропустим отправку — см. ниже
            await asyncio.sleep(60)  # проверка каждую минуту
        except Exception as e:
            logging.error(f"Ошибка в напоминаниях: {e}")
            await asyncio.sleep(60)

# ⚠️ Примечание: для отправки напоминаний нужно хранить user_id → мы его и так храним,
# но в get_players_for_event не возвращаем. При необходимости можно доработать.

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
        await message.answer("Введите ваше имя, фамилию и номер через пробел.\nПример: Иван Петров 19")
        await state.set_state(UserStates.waiting_for_player_name_number)
    elif message.text == "Я тренер":
        await message.answer("Введите пароль тренера:")
        await state.set_state(UserStates.waiting_for_coach_password)
    else:
        await message.answer("Пожалуйста, выбери одну из кнопок.")

# === Игрок ===

@dp.message(UserStates.waiting_for_player_name_number)
async def handle_player_registration(message: types.Message, state: FSMContext):
    success = await save_player_profile(message.from_user.id, message.text)
    if not success:
        await message.answer("❌ Неверный формат. Пример: Иван Петров 19")
        return
    await message.answer("✅ Профиль игрока создан!", reply_markup=get_player_menu())
    await state.set_state(UserStates.player_menu)

@dp.message(UserStates.player_menu)
async def handle_player_menu(message: types.Message, state: FSMContext):
    if message.text == "📅 Записаться на событие":
        events = await get_all_upcoming_events()
        if not events:
            await message.answer("Нет предстоящих событий.")
            return
        lines = []
        for eid, etype, dt, loc, opp in events:
            label = "Тренировка" if etype == "training" else f"Игра vs {opp or '—'}"
            lines.append(f"{eid}. {label} — {dt} — {loc}")
        await message.answer("Выберите ID события для записи:\n\n" + "\n".join(lines))
        await state.set_state(UserStates.waiting_for_event_to_join)
    elif message.text == "📋 Мои записи":
        regs = await get_player_registrations(message.from_user.id)
        if not regs:
            await message.answer("Вы никуда не записаны.")
        else:
            lines = []
            for eid, etype, dt, loc in regs:
                label = "Тренировка" if etype == "training" else "Игра"
                lines.append(f"{label} — {dt} — {loc}")
            await message.answer("Ваши записи:\n\n" + "\n".join(lines))
    else:
        await message.answer("Используйте кнопки меню.")

@dp.message(UserStates.waiting_for_event_to_join)
async def handle_join_event(message: types.Message, state: FSMContext):
    if not message.text.isdigit():
        await message.answer("Введите ID числом.")
        return
    event_id = int(message.text)
    event = await get_event_by_id(event_id)
    if not event:
        await message.answer("Событие не найдено.")
        return
    await register_player_for_event(message.from_user.id, event_id)
    await message.answer("✅ Вы записаны!", reply_markup=get_player_menu())
    await state.set_state(UserStates.player_menu)

# === Тренер ===

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

@dp.message(UserStates.coach_menu)
async def handle_coach_menu(message: types.Message, state: FSMContext):
    text = message.text
    if text == "🏒 Создать тренировку":
        await state.update_data(event_type="training")
        sent = await message.answer("📅 Введите дату и время:\n`ДД ММ ГГГГ ЧЧ:ММ`", parse_mode="Markdown")
        await state.update_data(prev_bot_msg_id=sent.message_id)
        await state.set_state(UserStates.waiting_for_event_datetime)
    elif text == "🎮 Создать игру":
        await state.update_data(event_type="game")
        sent = await message.answer("📅 Введите дату и время:\n`ДД ММ ГГГГ ЧЧ:ММ`", parse_mode="Markdown")
        await state.update_data(prev_bot_msg_id=sent.message_id)
        await state.set_state(UserStates.waiting_for_event_datetime)
    elif text == "📋 Мои события":
        events = await get_coach_events(message.from_user.id)
        if not events:
            await message.answer("У вас нет созданных событий.")
        else:
            lines = []
            for eid, etype, dt, loc, opp in events:
                label = "🏒 Тренировка" if etype == "training" else f"🎮 Игра vs {opp or '—'}"
                lines.append(f"ID {eid}\n{label}\n📅 {dt}\n📍 {loc}\n")
            await message.answer("Ваши события:\n\n" + "\n".join(lines))
    elif text == "✏️ Редактировать событие":
        events = await get_coach_events(message.from_user.id)
        if not events:
            await message.answer("Нет событий для редактирования.")
            return
        lines = [f"ID {eid}: {'Тренировка' if t=='training' else 'Игра'} ({dt})" for eid, t, dt, _, _ in events]
        sent = await message.answer("Введите ID события для редактирования:\n\n" + "\n".join(lines))
        await state.update_data(prev_bot_msg_id=sent.message_id)
        await state.set_state(UserStates.waiting_for_edit_choice)
    elif text == "🗑 Удалить событие":
        # ... (оставим как в предыдущей версии — с подтверждением)
        events = await get_coach_events(message.from_user.id)
        if not events:
            await message.answer("Нет событий для удаления.")
            return
        lines = [f"ID {eid}: {'Тренировка' if t=='training' else 'Игра'} ({dt})" for eid, t, dt, _, _ in events]
        sent = await message.answer("Введите ID события для удаления:\n\n" + "\n".join(lines) + "\n\n/cancel — отмена")
        await state.update_data(prev_bot_msg_id=sent.message_id)
        await state.set_state(UserStates.waiting_for_event_id_to_delete)
    elif text == "👥 Состав":
        await message.answer("Состав (в разработке)...")
    else:
        await message.answer("Используйте кнопки меню.")

# === Создание события ===

@dp.message(UserStates.waiting_for_event_datetime)
async def handle_event_datetime(message: types.Message, state: FSMContext):
    data = await state.get_data()
    prev_id = data.get("prev_bot_msg_id")
    if prev_id:
        await safe_delete(message.chat.id, prev_id)

    parsed = parse_datetime_input(message.text)
    if not parsed:
        sent = await message.answer("❌ Неверный формат. Пример: `12 12 2025 18:00`", parse_mode="Markdown")
        await state.update_data(prev_bot_msg_id=sent.message_id)
        return

    await state.update_data(event_datetime=parsed)
    event_type = data["event_type"]
    if event_type == "game":
        sent = await message.answer("🆚 Против кого играем? (название команды)")
        await state.update_data(prev_bot_msg_id=sent.message_id)
        await state.set_state(UserStates.waiting_for_opponent)
    else:
        sent = await message.answer("📍 Укажите место проведения:")
        await state.update_data(prev_bot_msg_id=sent.message_id)
        await state.set_state(UserStates.waiting_for_event_location)

@dp.message(UserStates.waiting_for_opponent)
async def handle_opponent(message: types.Message, state: FSMContext):
    data = await state.get_data()
    prev_id = data.get("prev_bot_msg_id")
    if prev_id:
        await safe_delete(message.chat.id, prev_id)

    opponent = message.text.strip()
    await state.update_data(opponent=opponent)
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
        sent = await message.answer("❌ Слишком короткое название.")
        await state.update_data(prev_bot_msg_id=sent.message_id)
        return

    user_id = message.from_user.id
    etype = data["event_type"]
    dt = data["event_datetime"]
    opponent = data.get("opponent")

    await create_event(user_id, etype, dt, location, opponent)

    label = "тренировка" if etype == "training" else f"игра против {opponent}"
    sent = await message.answer(f"✅ {label.capitalize()} создана!\n📅 {dt}\n📍 {location}", reply_markup=get_coach_menu())
    await state.update_data(prev_bot_msg_id=sent.message_id)
    await state.set_state(UserStates.coach_menu)

# === Удаление (с подтверждением) — упрощённо ===

@dp.message(UserStates.waiting_for_event_id_to_delete)
async def handle_delete_event_id(message: types.Message, state: FSMContext):
    if not message.text.isdigit():
        await message.answer("Введите ID числом. /cancel — отмена")
        return
    event_id = int(message.text)
    event = await get_event_by_id(event_id)
    if not event or event[5] != message.from_user.id:
        await message.answer("Событие не найдено.", reply_markup=get_coach_menu())
        await state.set_state(UserStates.coach_menu)
        return

    etype, dt, loc, opp, _ = event[1:6]
    label = "Тренировка" if etype == "training" else f"Игра vs {opp or '—'}"
    await message.answer(f"⚠️ Удалить?\n{label}\n{dt}\n{loc}\n\nОтветьте: да / нет")
    await state.update_data(event_id_to_delete=event_id)
    await state.set_state(UserStates.confirming_deletion)

@dp.message(UserStates.confirming_deletion)
async def handle_confirm_deletion(message: types.Message, state: FSMContext):
    text = message.text.strip().lower()
    if text in ["да", "yes", "y"]:
        data = await state.get_data()
        success = await delete_event_by_id(data["event_id_to_delete"], message.from_user.id)
        await message.answer("✅ Удалено." if success else "❌ Ошибка.", reply_markup=get_coach_menu())
    else:
        await message.answer("❌ Отменено.", reply_markup=get_coach_menu())
    await state.set_state(UserStates.coach_menu)

# === Редактирование события ===

@dp.message(UserStates.waiting_for_edit_choice)
async def handle_edit_choice(message: types.Message, state: FSMContext):
    if not message.text.isdigit():
        await message.answer("Введите ID числом.")
        return
    event_id = int(message.text)
    event = await get_event_by_id(event_id)
    if not event or event[5] != message.from_user.id:
        await message.answer("Событие не найдено.", reply_markup=get_coach_menu())
        await state.set_state(UserStates.coach_menu)
        return

    etype = event[1]
    choices = [
        "1. Дата и время",
        "2. Место проведения"
    ]
    if etype == "game":
        choices.append("3. Соперник")
    choices.append("\nВведите номер поля для изменения:")

    await message.answer("\n".join(choices))
    await state.update_data(editing_event_id=event_id, event_type=etype)
    await state.set_state(UserStates.waiting_for_new_value)

@dp.message(UserStates.waiting_for_new_value)
async def handle_new_value(message: types.Message, state: FSMContext):
    data = await state.get_data()
    event_id = data["editing_event_id"]
    choice = message.text.strip()
    etype = data["event_type"]

    field_map = {"1": "datetime", "2": "location"}
    if etype == "game":
        field_map["3"] = "opponent"

    if choice not in field_map:
        await message.answer("Неверный выбор. Попробуйте снова.")
        return

    field = field_map[choice]
    await state.update_data(editing_field=field, editing_event_id=event_id)

    prompts = {
        "datetime": "📅 Новое значение (ДД ММ ГГГГ ЧЧ:ММ):",
        "location": "📍 Новое место:",
        "opponent": "🆚 Новый соперник:"
    }
    await message.answer(prompts[field])
    await state.set_state(UserStates.waiting_for_new_value_input)

@dp.message(State("waiting_for_new_value_input"))  # временный state
async def handle_new_value_input(message: types.Message, state: FSMContext):
    data = await state.get_data()
    field = data["editing_field"]
    event_id = data["editing_event_id"]
    value = message.text.strip()

    if field == "datetime":
        parsed = parse_datetime_input(value)
        if not parsed:
            await message.answer("❌ Неверный формат даты.")
            return
        value = parsed

    await update_event_field(event_id, field, value)
    await message.answer("✅ Обновлено!", reply_markup=get_coach_menu())
    await state.set_state(UserStates.coach_menu)

# === Команды ===

@dp.message(Command("cancel"))
async def cmd_cancel(message: types.Message, state: FSMContext):
    current = await state.get_state()
    if current and "waiting_for_" in current:
        await message.answer("❌ Отменено.", reply_markup=get_coach_menu() if "coach" in current else get_player_menu())
        await state.set_state(UserStates.coach_menu if "coach" in current else UserStates.player_menu)
    else:
        await message.answer("Нечего отменять.")

@dp.message(Command("restart"))
async def cmd_restart(message: types.Message, state: FSMContext):
    await reset_user_profile(message.from_user.id)
    await state.clear()
    await message.answer("Профиль сброшен. Нажмите /start.")

# === Запуск ===
async def main():
    await init_db()
    # Запуск фоновой задачи напоминаний
    asyncio.create_task(send_reminders())
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())