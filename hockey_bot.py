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

# === КНОПКИ ДЛЯ ТРЕНИРОВКИ ===
def get_training_keyboard(training_id: int):
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✅ Записаться", callback_data=f"join_{training_id}")],
        [InlineKeyboardButton(text="🔄 Обновить", callback_data=f"refresh_{training_id}")]
    ])
    return keyboard

# === ГЛАВНОЕ МЕНЮ ===
def get_main_menu():
    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="📅 Тренировки", callback_data="trainings")],
            [InlineKeyboardButton(text="👥 Состав", callback_data="squad")]
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

        if player or coach:
            await message.answer(
                "Привет! Выбери действие:",
                reply_markup=get_main_menu()
            )
        else:
            await message.answer(
                "Привет! Кто ты?",
                reply_markup=get_role_keyboard()
            )

# === Обработка нажатия кнопок главного меню ===
@dp.callback_query(lambda c: c.data == "trainings")
async def handle_trainings(callback: types.CallbackQuery):
    await cmd_trainings(callback.message)
    await callback.answer()

@dp.callback_query(lambda c: c.data == "squad")
async def handle_squad(callback: types.CallbackQuery):
    await show_squad(callback.message)
    await callback.answer()

# === Обработка нажатия кнопок выбора роли ===
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

    await message.answer(
        f"✅ Добро пожаловать, {first_name} {last_name}!\nТеперь ты в команде.",
        reply_markup=get_main_menu()
    )
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

    await message.answer(
        f"✅ Добро пожаловать, тренер {first} {last}!",
        reply_markup=get_main_menu()
    )
    await state.clear()

# === /new_training ===
@dp.message(Command("new_training"))
async def cmd_new_training(message: types.Message, state: FSMContext):
    if not await is_coach(message.from_user.id):
        await message.answer("❌ Эта команда только для тренеров.")
        return

    await message.answer(
        "📅 Введи дату и время тренировки в формате:\n"
        "<code>ДД.ММ.ГГГГ ЧЧ:ММ</code>\n\n"
        "Пример: <code>05.02.2026 19:00</code>",
        parse_mode="HTML"
    )
    await state.set_state(NewTraining.datetime)

@dp.message(NewTraining.datetime)
async def process_training_datetime(message: types.Message, state: FSMContext):
    text = message.text.strip()
    if len(text) != 16 or text[2] != '.' or text[5] != '.' or text[10] != ' ' or text[13] != ':':
        await message.answer("❌ Неверный формат. Попробуй ещё раз:\n<code>05.02.2026 19:00</code>", parse_mode="HTML")
        return

    await state.update_data(datetime=text)
    await message.answer("📍 Где тренировка?")
    await state.set_state(NewTraining.location)

@dp.message(NewTraining.location)
async def process_training_location(message: types.Message, state: FSMContext):
    await state.update_data(location=message.text.strip())
    await message.answer("👥 Максимальное число игроков (например: 20)")
    await state.set_state(NewTraining.max_players)

@dp.message(NewTraining.max_players)
async def process_training_max_players(message: types.Message, state: FSMContext):
    if not message.text.strip().isdigit():
        await message.answer("❌ Введи число (например: 20)")
        return
    await state.update_data(max_players=int(message.text.strip()))
    await message.answer("📝 Описание (или «-» если не нужно)")
    await state.set_state(NewTraining.description)

@dp.message(NewTraining.description)
async def process_training_description(message: types.Message, state: FSMContext):
    desc = message.text.strip()
    if desc == "-":
        desc = ""

    data = await state.get_data()
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

        for row in rows:
            training_id, dt, loc, max_p = row
            reg_cursor = await db.execute("""
                SELECT p.first_name, p.last_name, p.jersey_number
                FROM registrations r
                JOIN players p ON r.user_id = p.user_id
                WHERE r.training_id = ?
                ORDER BY p.last_name
            """, (training_id,))
            players = await reg_cursor.fetchall()

            text = f"🏒 <b>Тренировка ID {training_id}</b>\n"
            text += f"📅 {dt}\n📍 {loc}\n\n"

            if players:
                text += "<b>Записаны:</b>\n"
                for i, (first, last, num) in enumerate(players, 1):
                    text += f"{i}. {first} {last} (#{num})\n"
                text += f"\n👥 {len(players)}/{max_p} игроков"
            else:
                text += "<i>Пока никто не записался</i>"

            await message.answer(
                text,
                parse_mode="HTML",
                reply_markup=get_training_keyboard(training_id)
            )

# === КОМАНДА /squad — СОСТАВ ===
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

# === КНОПКА «Состав» из меню ===
# (уже обрабатывается через handle_squad → вызывает show_squad)

# === ЗАПИСЬ НА ТРЕНИРОВКУ ===
@dp.callback_query(lambda c: c.data.startswith("join_"))
async def handle_join_training(callback: types.CallbackQuery):
    training_id = int(callback.data.split("_")[1])
    user_id = callback.from_user.id

    async with aiosqlite.connect("hockey.db") as db:
        cursor = await db.execute("SELECT 1 FROM players WHERE user_id = ?", (user_id,))
        if not await cursor.fetchone():
            await callback.answer("❌ Ты должен быть зарегистрирован как игрок.", show_alert=True)
            return

        cursor = await db.execute("SELECT max_players FROM trainings WHERE id = ?", (training_id,))
        tr = await cursor.fetchone()
        if not tr:
            await callback.answer("Тренировка не найдена.", show_alert=True)
            return

        max_players = tr[0]
        cursor = await db.execute("SELECT COUNT(*) FROM registrations WHERE training_id = ?", (training_id,))
        current_count = (await cursor.fetchone())[0]

        if current_count >= max_players:
            await callback.answer("❌ На этой тренировке уже нет мест.", show_alert=True)
            return

        cursor = await db.execute("SELECT 1 FROM registrations WHERE user_id = ? AND training_id = ?", (user_id, training_id))
        if await cursor.fetchone():
            await callback.answer("✅ Ты уже записан!", show_alert=True)
            return

        await db.execute("INSERT INTO registrations (user_id, training_id) VALUES (?, ?)", (user_id, training_id))
        await db.commit()
        await callback.answer("✅ Записан!", show_alert=False)

        # ОБНОВЛЯЕМ СООБЩЕНИЕ
        cursor = await db.execute("SELECT datetime, location, max_players FROM trainings WHERE id = ?", (training_id,))
        tr_data = await cursor.fetchone()
        if not tr_data:
            return

        dt, loc, max_p = tr_data

        reg_cursor = await db.execute("""
            SELECT p.first_name, p.last_name, p.jersey_number
            FROM registrations r
            JOIN players p ON r.user_id = p.user_id
            WHERE r.training_id = ?
            ORDER BY p.last_name
        """, (training_id,))
        players = await reg_cursor.fetchall()

        text = f"🏒 <b>Тренировка ID {training_id}</b>\n"
        text += f"📅 {dt}\n📍 {loc}\n\n"

        if players:
            text += "<b>Записаны:</b>\n"
            for i, (first, last, num) in enumerate(players, 1):
                text += f"{i}. {first} {last} (#{num})\n"
            text += f"\n👥 {len(players)}/{max_p} игроков"
        else:
            text += "<i>Пока никто не записался</i>"

        try:
            await callback.message.edit_text(
                text,
                parse_mode="HTML",
                reply_markup=get_training_keyboard(training_id)
            )
        except Exception:
            pass

# === ОБНОВЛЕНИЕ СПИСКА ===
@dp.callback_query(lambda c: c.data.startswith("refresh_"))
async def handle_refresh_training(callback: types.CallbackQuery):
    training_id = int(callback.data.split("_")[1])
    async with aiosqlite.connect("hockey.db") as db:
        cursor = await db.execute("SELECT datetime, location, max_players FROM trainings WHERE id = ?", (training_id,))
        tr_data = await cursor.fetchone()
        if not tr_data:
            await callback.answer("Тренировка не найдена.", show_alert=True)
            return

        dt, loc, max_p = tr_data

        reg_cursor = await db.execute("""
            SELECT p.first_name, p.last_name, p.jersey_number
            FROM registrations r
            JOIN players p ON r.user_id = p.user_id
            WHERE r.training_id = ?
            ORDER BY p.last_name
        """, (training_id,))
        players = await reg_cursor.fetchall()

        text = f"🏒 <b>Тренировка ID {training_id}</b>\n"
        text += f"📅 {dt}\n📍 {loc}\n\n"

        if players:
            text += "<b>Записаны:</b>\n"
            for i, (first, last, num) in enumerate(players, 1):
                text += f"{i}. {first} {last} (#{num})\n"
            text += f"\n👥 {len(players)}/{max_p} игроков"
        else:
            text += "<i>Пока никто не записался</i>"

        try:
            await callback.message.edit_text(
                text,
                parse_mode="HTML",
                reply_markup=get_training_keyboard(training_id)
            )
            await callback.answer("🔄 Обновлено!", show_alert=False)
        except Exception:
            await callback.answer("Не удалось обновить.", show_alert=True)

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
    await message.answer(
        "🔄 Твой профиль удалён.\n\nПривет! Кто ты?",
        reply_markup=get_role_keyboard()
    )

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
        await message.answer(
            "⚠️ Произошла ошибка. Давай начнём заново.\n\n"
            "Напиши /start или выбери роль:",
            reply_markup=get_role_keyboard()
        )
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