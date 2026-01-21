import asyncio
import aiosqlite
from aiogram import Bot, Dispatcher, types
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.context import FSMContext
from aiogram.filters import Command

BOT_TOKEN = "8194198392:AAFjEcdDbJw8ev8NKRYM5lOqyKwg-dN4eCs"  # ← не забудь!
bot = Bot(token=BOT_TOKEN)
dp = Dispatcher(storage=MemoryStorage())

class Registration(StatesGroup):
    first_name = State()
    last_name = State()
    jersey_number = State()

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
        await db.commit()

async def safe_delete(chat_id: int, message_id: int):
    try:
        await bot.delete_message(chat_id=chat_id, message_id=message_id)
    except Exception:
        pass

# === ФУНКЦИЯ: начать регистрацию (вызывается из /start и /restart) ===
async def start_registration(message: types.Message, state: FSMContext):
    # Удаляем команду (/start или /restart)
    await safe_delete(message.chat.id, message.message_id)

    sent = await message.answer("Привет! Давай зарегистрируем тебя.\n\nКак тебя зовут?")
    await state.update_data(prev_bot_msg_id=sent.message_id)
    await state.set_state(Registration.first_name)

# === КОМАНДА /start ===
@dp.message(Command("start"))
async def cmd_start(message: types.Message, state: FSMContext):
    user_id = message.from_user.id
    async with aiosqlite.connect("hockey.db") as db:
        cursor = await db.execute("SELECT 1 FROM players WHERE user_id = ?", (user_id,))
        if await cursor.fetchone():
            await message.answer("Ты уже зарегистрирован! Используй /profile или /restart чтобы изменить данные.")
            return
    await start_registration(message, state)

# === КОМАНДА /restart ===
@dp.message(Command("restart"))
async def cmd_restart(message: types.Message, state: FSMContext):
    user_id = message.from_user.id
    async with aiosqlite.connect("hockey.db") as db:
        # Удаляем старую запись
        await db.execute("DELETE FROM players WHERE user_id = ?", (user_id,))
        await db.commit()
    # Сбрасываем состояние (на всякий случай)
    await state.clear()
    # Запускаем регистрацию заново
    await start_registration(message, state)

# === ОСТАЛЬНЫЕ ШАГИ РЕГИСТРАЦИИ (без изменений) ===
@dp.message(Registration.first_name)
async def process_first_name(message: types.Message, state: FSMContext):
    data = await state.get_data()
    prev_bot_id = data.get("prev_bot_msg_id")
    await safe_delete(message.chat.id, message.message_id)
    if prev_bot_id:
        await safe_delete(message.chat.id, prev_bot_id)
    await state.update_data(first_name=message.text.strip())
    sent = await message.answer("Отлично! А теперь фамилию:")
    await state.update_data(prev_bot_msg_id=sent.message_id)
    await state.set_state(Registration.last_name)

@dp.message(Registration.last_name)
async def process_last_name(message: types.Message, state: FSMContext):
    data = await state.get_data()
    prev_bot_id = data.get("prev_bot_msg_id")
    await safe_delete(message.chat.id, message.message_id)
    if prev_bot_id:
        await safe_delete(message.chat.id, prev_bot_id)
    await state.update_data(last_name=message.text.strip())
    sent = await message.answer("Супер! Теперь введи свой хоккейный номер (например: 17):")
    await state.update_data(prev_bot_msg_id=sent.message_id)
    await state.set_state(Registration.jersey_number)

@dp.message(Registration.jersey_number)
async def process_jersey_number(message: types.Message, state: FSMContext):
    data = await state.get_data()
    prev_bot_id = data.get("prev_bot_msg_id")
    await safe_delete(message.chat.id, message.message_id)
    if prev_bot_id:
        await safe_delete(message.chat.id, prev_bot_id)
    number = message.text.strip()
    if not number.isdigit():
        sent = await message.answer("Пожалуйста, введи только цифры (например: 17).")
        await state.update_data(prev_bot_msg_id=sent.message_id)
        return
    user_id = message.from_user.id
    first_name = data["first_name"]
    last_name = data["last_name"]
    async with aiosqlite.connect("hockey.db") as db:
        await db.execute(
            "INSERT INTO players (user_id, first_name, last_name, jersey_number) VALUES (?, ?, ?, ?)",
            (user_id, first_name, last_name, number)
        )
        await db.commit()
    await message.answer(f"✅ Регистрация завершена!\n\n"
                         f"Имя: {first_name}\n"
                         f"Фамилия: {last_name}\n"
                         f"Номер: #{number}\n\n"
                         f"Теперь ты в нашей команде! 🏒")
    await state.clear()

@dp.message(Command("profile"))
async def show_profile(message: types.Message):
    user_id = message.from_user.id
    async with aiosqlite.connect("hockey.db") as db:
        cursor = await db.execute(
            "SELECT first_name, last_name, jersey_number FROM players WHERE user_id = ?",
            (user_id,)
        )
        row = await cursor.fetchone()
        if row:
            first, last, num = row
            await message.answer(f"👤 Твой профиль:\n\nИмя: {first}\nФамилия: {last}\nНомер: #{num}")
        else:
            await message.answer("Ты ещё не зарегистрирован. Напиши /start")

async def main():
    await init_db()
    print("✅ Бот запущен!")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())