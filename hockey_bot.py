import aiosqlite
from aiogram import Bot, Dispatcher, types
from aiogram.filters import Command
from aiogram.types import Message, CallbackQuery
from aiogram import F
import asyncio
from datetime import datetime, timedelta

# Токен бота
BOT_TOKEN = "8194198392:AAFjEcdDbJw8ev8NKRYM5lOqyKwg-dN4eCs"

# Путь к базе данных
DB_PATH = 'hockey.db'

# Пароль для тренера
COACH_PASSWORD = "1234"

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
                description TEXT,
                max_participants INTEGER DEFAULT 20
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
async def create_training(date, time, description, max_participants=20):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute('''
            INSERT INTO trainings (date, time, description, max_participants)
            VALUES (?, ?, ?, ?)
        ''', (date, time, description, max_participants))
        await db.commit()

# Получить все тренировки
async def get_trainings():
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute('''
            SELECT id, date, time, description, max_participants
            FROM trainings
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

# Клавиатура главного меню
def main_menu_keyboard(is_coach=False):
    keyboard = [
        [types.InlineKeyboardButton(text="👤 Мой профиль", callback_data="profile")],
        [types.InlineKeyboardButton(text="🏒 Тренировки", callback_data="trainings_list")],
        [types.InlineKeyboardButton(text="🎮 Игры", callback_data="games")],
        [types.InlineKeyboardButton(text="📋 Состав", callback_data="team")],
    ]
    if is_coach:
        keyboard.append([types.InlineKeyboardButton(text="教练 🎯", callback_data="coach_menu")])
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
            "👋 Привет! Давай создадим твой профиль.\n\n"
            "Напиши в одном сообщении:\n"
            "**Имя Фамилия Номер**\n\n"
            "Пример: `Вячеслав Федоров 19`"
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
        "Напиши: **Имя Фамилия Номер**\n\n"
        "Пример: `Вячеслав Федоров 19`"
    )

# Обработка сообщения с профилем
async def handle_profile(message: Message):
    user_id = message.from_user.id

    if await player_exists(user_id):
        return

    text = message.text.strip()

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

    await save_player(user_id, first_name, last_name, jersey_number)

    # Удаляем сообщение пользователя (с профилем)
    try:
        await message.delete()
    except:
        pass

    # Отправляем главное меню
    await message.answer(
        f"🎉 Профиль создан!\n"
        f"Имя: {first_name}\n"
        f"Фамилия: {last_name}\n"
        f"Номер: {jersey_number}\n\n"
        "Выбери действие:",
        reply_markup=main_menu_keyboard()
    )

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
                training_id, date, time, desc, max_p = t
                count = await get_signup_count(training_id)
                text += f"📅 <b>{date}</b> | ⏰ {time}\n"
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

    elif data == "games":
        await callback_query.message.edit_text(
            "🎮 Здесь будет расписание игр.",
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

    elif data == "create_training":
        if await is_coach(user_id):
            await callback_query.message.edit_text(
                "📝 Отправь информацию о тренировке в формате:\n"
                "`Дата Время Описание`\n\n"
                "Пример: `2026-02-01 19:00 Тренировка вратарей`",
                reply_markup=back_keyboard()
            )
            # Здесь можно добавить состояние ожидания
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
                    training_id, date, time, desc, _ = t
                    participants = await get_training_participants(training_id)
                    text += f"📅 {date} | ⏰ {time}\n"
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

# Обработка сообщений с информацией о тренировке (для тренера)
async def handle_create_training(message: Message):
    user_id = message.from_user.id

    if not await is_coach(user_id):
        return

    text = message.text.strip()
    parts = text.split(" ", 2)
    if len(parts) != 3:
        await message.answer("❌ Неверный формат. Нужно: Дата Время Описание")
        return

    date, time, desc = parts

    # Проверим формат даты
    try:
        datetime.strptime(date, "%Y-%m-%d")
    except ValueError:
        await message.answer("❌ Неверный формат даты. Используй: ГГГГ-ММ-ДД")
        return

    await create_training(date, time, desc)

    await message.answer(f"✅ Тренировка создана:\n{date} | {time} | {desc}")

# Функция для отправки уведомлений (в фоне)
async def send_reminders(bot):
    while True:
        await asyncio.sleep(60)  # Проверяем каждую минуту

        now = datetime.now()
        reminder_time = now + timedelta(hours=1)  # За 1 час до начала
        reminder_str = reminder_time.strftime("%Y-%m-%d %H:%M")

        async with aiosqlite.connect(DB_PATH) as db:
            cursor = await db.execute('''
                SELECT t.id, t.date, t.time, t.description
                FROM trainings t
                WHERE t.date || ' ' || t.time = ?
            ''', (reminder_str,))
            trainings = await cursor.fetchall()

        for t in trainings:
            training_id, date, time, desc = t

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
                        await bot.send_message(user_id, f"⏰ Напоминание!\nТренировка:\n{date} | {time} | {desc}")
                    except:
                        pass  # Не смогли отправить — пропускаем

# Основная функция
async def main():
    await init_db()

    bot = Bot(token=BOT_TOKEN)
    dp = Dispatcher()

    # Запускаем задачу для напоминаний
    asyncio.create_task(send_reminders(bot))

    dp.message.register(start_command, Command("start"))
    dp.message.register(restart_command, Command("restart"))
    dp.message.register(handle_profile, F.text & ~F.command)
    dp.message.register(handle_create_training, F.text & F.func(lambda m: m.text and m.text.count(" ") >= 2 and await is_coach(m.from_user.id) if m.from_user else False))
    dp.callback_query.register(button_callback, lambda c: c.data in ["profile", "trainings_list", "games", "team", "coach_menu", "create_training", "list_participants", "back_to_main"] or c.data.startswith("signup_"))

    print("✅ Бот запущен. Ждём сообщений...")
    await dp.start_polling(bot)

if __name__ == '__main__':
    import asyncio
    asyncio.run(main())