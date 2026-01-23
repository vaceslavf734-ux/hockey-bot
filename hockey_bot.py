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

# Включим логирование
logging.basicConfig(level=logging.INFO)

# === FSM Состояния ===
class UserStates(StatesGroup):
    waiting_for_role = State()
    waiting_for_coach_password = State()
    waiting_for_coach_name = State()
    coach_menu = State()
    waiting_for_event_datetime = State()
    waiting_for_event_location = State()
    waiting_for_opponent = State()
    waiting_for_event_id_to_delete = State()
    confirming_deletion = State()
    waiting_for_player_profile = State()
    waiting_for_event_to_join = State()
    player_menu = State()

# === Инициализация бота ===
bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()

# === Вспомогательные функции ===

async def init_db():
    async with aiosqlite.connect(DATABASE) as db:
        await db.execute("""
            CREATE TABLE IF NOT EXISTS users (
                user_id INTEGER PRIMARY KEY,
                role TEXT NOT NULL,
                name TEXT,
                surname TEXT,
                number TEXT
            )
        """)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                type TEXT NOT NULL,
                datetime TEXT NOT NULL,
                location TEXT NOT NULL,
                opponent TEXT,
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

# === Работа с БД ===

async def save_coach(user_id: int, full_name: str):
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

async def save_player(user_id: int, input_text: str):
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

async def get_user_role(user_id: int):
    async with aiosqlite.connect(DATABASE) as db:
        cursor = await db.execute("SELECT role FROM users WHERE user_id = ?", (user_id,))
        row = await cursor.fetchone()
        return row[0] if row else None

async def create_event(user_id: int, etype: str, dt: str, loc: str, opponent: str = None):
    async with aiosqlite.connect(DATABASE) as db:
        await db.execute("""
            INSERT INTO events (type, datetime, location, opponent, created_by)
            VALUES (?, ?, ?, ?, ?)
        """, (etype, dt, loc, opponent, user_id))
        await db.commit()

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

async def get_coach_events_with_registrations(user_id: int):
    async with aiosqlite.connect(DATABASE) as db:
        cursor = await db.execute("""
            SELECT e.id, e.type, e.datetime, e.location, e.opponent,
                   GROUP_CONCAT(u.name || ' ' || u.surname || ' (' || IFNULL(u.number, '?') || ')', '\n') AS players
            FROM events e
            LEFT JOIN registrations r ON e.id = r.event_id
            LEFT JOIN users u ON r.user_id = u.user_id
            WHERE e.created_by = ?
            GROUP BY e.id
            ORDER BY e.datetime
        """, (user_id,))
        return await cursor.fetchall()

async def register_player(user_id: int, event_id: int):
    async with aiosqlite.connect(DATABASE) as db:
        await db.execute("""
            INSERT OR IGNORE INTO registrations (user_id, event_id)
            VALUES (?, ?)
        """, (user_id, event_id))
        await db.commit()

async def get_player_registrations(user_id: int):
    async with aiosqlite.connect(DATABASE) as db:
        cursor = await db.execute("""
            SELECT e.id, e.type, e.datetime, e.location, e.opponent
            FROM registrations r
            JOIN events e ON r.event_id = e.id
            WHERE r.user_id = ?
            ORDER BY e.datetime
        """, (user_id,))
        return await cursor.fetchall()

# === НОВАЯ ФУНКЦИЯ: получаем участников с user_id ===
async def get_players_for_event_with_user_id(event_id: int):
    async with aiosqlite.connect(DATABASE) as db:
        cursor = await db.execute("""
            SELECT u.user_id, u.name, u.surname, u.number
            FROM registrations r
            JOIN users u ON r.user_id = u.user_id
            WHERE r.event_id = ?
        """, (event_id,))
        return await cursor.fetchall()

# === ФОН: Напоминания ===

async def send_reminders():
    """Проверяет каждую минуту, не наступило ли время напоминаний"""
    while True:
        try:
            # Целевое время: сейчас + 1 час
            target_dt = datetime.now() + timedelta(hours=1)
            target_str = target_dt.strftime("%Y-%m-%d %H:%M")

            async with aiosqlite.connect(DATABASE) as db:
                cursor = await db.execute("""
                    SELECT id, type, datetime, location, opponent
                    FROM events
                    WHERE datetime = ?
                """, (target_str,))
                events = await cursor.fetchall()

            for eid, etype, dt, loc, opp in events:
                players = await get_players_for_event_with_user_id(eid)
                if not players:
                    continue

                label = "Тренировка" if etype == "training" else f"Игра vs {opp or '—'}"
                message_text = (
                    f"🔔 Напоминание!\n"
                    f"Через 1 час начинается:\n"
                    f"{label}\n"
                    f"📅 {dt}\n"
                    f"📍 {loc}"
                )

                for user_id, name, surname, number in players:
                    try:
                        await bot.send_message(user_id, message_text)
                    except Exception as e:
                        logging.warning(f"Не удалось отправить напоминание пользователю {user_id}: {e}")

            await asyncio.sleep(60)  # проверка раз в минуту

        except Exception as e:
            logging.error(f"Ошибка в фоновой задаче напоминаний: {e}")
            await asyncio.sleep(60)

# === ОБРАБОТЧИКИ ===

@dp.message(Command("start"))
async def cmd_start(message: types.Message, state: FSMContext):
    await state.clear()
    markup = ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text="Старт")]],
        resize_keyboard=True,
        one_time_keyboard=True
    )
    await message.answer("Привет! Нажми кнопку ниже, чтобы начать.", reply_markup=markup)

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
    if message.text == "Я тренер":
        await message.answer("Введите пароль тренера:")
        await state.set_state(UserStates.waiting_for_coach_password)
    elif message.text == "Я игрок":
        await message.answer("Введите ваш профиль: Имя Фамилия Номер\nПример: Иван Петров 19")
        await state.set_state(UserStates.waiting_for_player_profile)
    else:
        await message.answer("Пожалуйста, выберите одну из кнопок.")

# === Тренер ===

@dp.message(UserStates.waiting_for_coach_password)
async def handle_coach_password(message: types.Message, state: FSMContext):
    if message.text.strip() == COACH_PASSWORD:
        await message.answer("✅ Пароль верный!\nВведите имя и фамилию (например: Иван Петров):")
        await state.set_state(UserStates.waiting_for_coach_name)
    else:
        await message.answer("❌ Неверный пароль. Попробуйте снова.")

@dp.message(UserStates.waiting_for_coach_name)
async def handle_coach_name(message: types.Message, state: FSMContext):
    if not re.fullmatch(r"[А-Яа-яЁё]+(?:\s+[А-Яа-яЁё]+)+", message.text.strip()):
        await message.answer("Ошибка. Пример: Иван Петров")
        return
    success = await save_coach(message.from_user.id, message.text)
    if not success:
        await message.answer("Введите имя и фамилию.")
        return
    await message.answer("✅ Профиль тренера создан!", reply_markup=get_coach_menu())
    await state.set_state(UserStates.coach_menu)

@dp.message(UserStates.coach_menu)
async def handle_coach_menu(message: types.Message, state: FSMContext):
    if message.text == "🏒 Создать тренировку":
        await state.update_data(event_type="training")
        await message.answer("📅 Введите дату и время:\n`ДД ММ ГГГГ ЧЧ:ММ`", parse_mode="Markdown")
        await state.set_state(UserStates.waiting_for_event_datetime)
    elif message.text == "🎮 Создать игру":
        await state.update_data(event_type="game")
        await message.answer("📅 Введите дату и время:\n`ДД ММ ГГГГ ЧЧ:ММ`", parse_mode="Markdown")
        await state.set_state(UserStates.waiting_for_event_datetime)
    elif message.text == "📋 Мои события":
        events = await get_coach_events_with_registrations(message.from_user.id)
        if not events:
            await message.answer("У вас нет событий.")
        else:
            lines = []
            for eid, etype, dt, loc, opp, players in events:
                label = "🏒 Тренировка" if etype == "training" else f"🎮 Игра vs {opp or '—'}"
                players_text = "\nУчастники:\n" + (players if players else "Никто не записался")
                lines.append(f"ID {eid}\n{label}\n📅 {dt}\n📍 {loc}{players_text}\n")
            await message.answer("Ваши события:\n\n" + "\n".join(lines))
    elif message.text == "🗑 Удалить событие":
        events = await get_coach_events_with_registrations(message.from_user.id)
        if not events:
            await message.answer("Нет событий для удаления.")
            return
        lines = [f"ID {eid}: {'Тренировка' if t=='training' else 'Игра'} ({dt})" for eid, t, dt, _, _, _ in events]
        await message.answer("Введите ID для удаления:\n\n" + "\n".join(lines) + "\n\n/cancel — отмена")
        await state.set_state(UserStates.waiting_for_event_id_to_delete)
    elif message.text == "👥 Состав":
        await message.answer("Состав (в разработке)...")
    else:
        await message.answer("Используйте кнопки.")

# === Создание события ===

@dp.message(UserStates.waiting_for_event_datetime)
async def handle_event_datetime(message: types.Message, state: FSMContext):
    parsed = parse_datetime_input(message.text)
    if not parsed:
        await message.answer("❌ Неверный формат. Пример: `12 12 2025 18:00`", parse_mode="Markdown")
        return
    await state.update_data(event_datetime=parsed)
    data = await state.get_data()
    if data["event_type"] == "game":
        await message.answer("🆚 Против кого играем?")
        await state.set_state(UserStates.waiting_for_opponent)
    else:
        await message.answer("📍 Место проведения:")
        await state.set_state(UserStates.waiting_for_event_location)

@dp.message(UserStates.waiting_for_opponent)
async def handle_opponent(message: types.Message, state: FSMContext):
    await state.update_data(opponent=message.text.strip())
    await message.answer("📍 Место проведения:")
    await state.set_state(UserStates.waiting_for_event_location)

@dp.message(UserStates.waiting_for_event_location)
async def handle_location(message: types.Message, state: FSMContext):
    location = message.text.strip()
    if len(location) < 3:
        await message.answer("❌ Слишком коротко.")
        return
    data = await state.get_data()
    await create_event(
        message.from_user.id,
        data["event_type"],
        data["event_datetime"],
        location,
        data.get("opponent")
    )
    label = "тренировка" if data["event_type"] == "training" else f"игра против {data.get('opponent', '—')}"
    await message.answer(f"✅ {label.capitalize()} создана!", reply_markup=get_coach_menu())
    await state.set_state(UserStates.coach_menu)

# === Удаление события ===

@dp.message(UserStates.waiting_for_event_id_to_delete)
async def handle_delete_id(message: types.Message, state: FSMContext):
    if not message.text.isdigit():
        await message.answer("Введите ID числом. /cancel — отмена")
        return
    event_id = int(message.text)
    async with aiosqlite.connect(DATABASE) as db:
        cursor = await db.execute("SELECT type, datetime, location, opponent FROM events WHERE id = ? AND created_by = ?", (event_id, message.from_user.id))
        row = await cursor.fetchone()
    if not row:
        await message.answer("Событие не найдено.", reply_markup=get_coach_menu())
        await state.set_state(UserStates.coach_menu)
        return
    etype, dt, loc, opp = row
    label = "Тренировка" if etype == "training" else f"Игра vs {opp or '—'}"
    await message.answer(f"⚠️ Удалить?\n{label}\n{dt}\n{loc}\n\nОтветьте: да / нет")
    await state.update_data(event_id_to_delete=event_id)
    await state.set_state(UserStates.confirming_deletion)

@dp.message(UserStates.confirming_deletion)
async def confirm_deletion(message: types.Message, state: FSMContext):
    if message.text.strip().lower() in ["да", "yes", "y"]:
        data = await state.get_data()
        async with aiosqlite.connect(DATABASE) as db:
            await db.execute("DELETE FROM events WHERE id = ? AND created_by = ?", (data["event_id_to_delete"], message.from_user.id))
            await db.commit()
        await message.answer("✅ Удалено.", reply_markup=get_coach_menu())
    else:
        await message.answer("❌ Отменено.", reply_markup=get_coach_menu())
    await state.set_state(UserStates.coach_menu)

# === Игрок ===

@dp.message(UserStates.waiting_for_player_profile)
async def handle_player_profile(message: types.Message, state: FSMContext):
    success = await save_player(message.from_user.id, message.text)
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
        await message.answer("Выберите ID события:\n\n" + "\n".join(lines))
        await state.set_state(UserStates.waiting_for_event_to_join)
    elif message.text == "📋 Мои записи":
        regs = await get_player_registrations(message.from_user.id)
        if not regs:
            await message.answer("Вы никуда не записаны.")
        else:
            lines = []
            for eid, etype, dt, loc, opp in regs:
                label = "Тренировка" if etype == "training" else f"Игра vs {opp or '—'}"
                lines.append(f"{label} — {dt} — {loc}")
            await message.answer("Ваши записи:\n\n" + "\n".join(lines))
    else:
        await message.answer("Используйте кнопки.")

@dp.message(UserStates.waiting_for_event_to_join)
async def join_event(message: types.Message, state: FSMContext):
    if not message.text.isdigit():
        await message.answer("Введите ID числом.")
        return
    event_id = int(message.text)
    async with aiosqlite.connect(DATABASE) as db:
        cursor = await db.execute("SELECT id FROM events WHERE id = ?", (event_id,))
        if not await cursor.fetchone():
            await message.answer("Событие не найдено.")
            return
    await register_player(message.from_user.id, event_id)
    await message.answer("✅ Вы записаны!", reply_markup=get_player_menu())
    await state.set_state(UserStates.player_menu)

# === КОМАНДЫ ===

@dp.message(Command("cancel"))
async def cmd_cancel(message: types.Message, state: FSMContext):
    current = await state.get_state()
    if current and "waiting_for_" in current:
        role = await get_user_role(message.from_user.id)
        if role == "coach":
            await message.answer("❌ Отменено.", reply_markup=get_coach_menu())
            await state.set_state(UserStates.coach_menu)
        elif role == "player":
            await message.answer("❌ Отменено.", reply_markup=get_player_menu())
            await state.set_state(UserStates.player_menu)
        else:
            await cmd_start(message, state)
    else:
        await message.answer("Нечего отменять.")

@dp.message(Command("restart"))
async def cmd_restart(message: types.Message, state: FSMContext):
    user_id = message.from_user.id
    await reset_user_profile(user_id)
    await state.clear()
    await message.answer("🔄 Ваш профиль полностью удалён.\nТеперь вы можете зарегистрироваться заново.")
    await cmd_start(message, state)

# === ЗАПУСК ===
async def main():
    await init_db()
    # Запуск фоновой задачи напоминаний
    asyncio.create_task(send_reminders())
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())