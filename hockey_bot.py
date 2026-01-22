import sqlite3
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes

# Путь к базе данных
DB_PATH = 'hockey.db'

# Инициализация БД
def init_db():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS players (
            user_id INTEGER PRIMARY KEY,
            first_name TEXT NOT NULL,
            last_name TEXT NOT NULL,
            jersey_number INTEGER NOT NULL
        )
    ''')
    conn.commit()
    conn.close()

# Сохранение профиля
def save_player(user_id, first_name, last_name, jersey_number):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute('''
        INSERT OR REPLACE INTO players (user_id, first_name, last_name, jersey_number)
        VALUES (?, ?, ?, ?)
    ''', (user_id, first_name, last_name, jersey_number))
    conn.commit()
    conn.close()

# Проверка, существует ли игрок
def player_exists(user_id):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute('SELECT 1 FROM players WHERE user_id = ?', (user_id,))
    exists = cursor.fetchone() is not None
    conn.close()
    return exists

# Команда /start
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if player_exists(user_id):
        await update.message.reply_text("✅ Твой профиль уже создан!")
    else:
        await update.message.reply_text(
            "👋 Привет! Давай создадим твой профиль.\n\n"
            "Напиши в одном сообщении:\n"
            "**Имя Фамилия Номер**\n\n"
            "Пример: `Вячеслав Федоров 19`"
        )

# Обработка сообщения с профилем
async def handle_profile(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    text = update.message.text.strip()

    # Проверяем, что это не команда
    if text.startswith('/'):
        return

    # Проверяем, что профиль ещё не создан
    if player_exists(user_id):
        return

    # Разбиваем текст
    parts = text.split()
    if len(parts) < 3:
        await update.message.reply_text("❌ Неверный формат. Нужно: Имя Фамилия Номер")
        return

    try:
        # Последнее слово — номер
        jersey_number = int(parts[-1])
        first_name = parts[0]
        last_name = ' '.join(parts[1:-1])  # На случай, если фамилия состоит из двух слов
    except ValueError:
        await update.message.reply_text("❌ Номер должен быть числом!")
        return

    # Сохраняем
    save_player(user_id, first_name, last_name, jersey_number)
    await update.message.reply_text(
        f"🎉 Профиль создан!\n"
        f"Имя: {first_name}\n"
        f"Фамилия: {last_name}\n"
        f"Номер: {jersey_number}"
    )

# Основная функция
def main():
    init_db()

    # Замени 'YOUR_BOT_TOKEN' на реальный токен от BotFather
    application = Application.builder().token("8194198392:AAFjEcdDbJw8ev8NKRYM5lOqyKwg-dN4eCs").build()

    application.add_handler(CommandHandler("start", start))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_profile))

    print("✅ Бот запущен. Ждём сообщений...")
    application.run_polling()

if __name__ == '__main__':
    main()