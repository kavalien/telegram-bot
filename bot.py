import openai
import logging
import sqlite3
from aiogram import Bot, Dispatcher, types, executor
from typing import List, Dict

# Вставь свои токены:
TELEGRAM_TOKEN = "7976844185:AAG-ifHnwd2pu4EB69aWReFUHRgC0Ui2z9o"
OPENAI_API_KEY = (
    "sk-proj-Znyw00LDc7QxFyFYUxG-vuxvp8k5zv_VypJuvzP8eZH9h8khU5gePK8XWJ-jxaabQDgu"
    "OwLdRLT3BlbkFJbehFdxCdjPWsjo-AjL-kJL2fn7Vxx1v6NozcbBo_o78lrnLU0wbS1VOlnjX3AW9"
    "XWwtjwJfg0A"
)

# Настройка логирования
logging.basicConfig(level=logging.INFO)

# Инициализация бота и диспетчера
bot = Bot(token=TELEGRAM_TOKEN)
dp = Dispatcher(bot)

# Укажи свой ID администратора
ADMIN_ID = 400783137  # Замени на свой ID

# Настройка OpenAI API
openai.api_key = OPENAI_API_KEY

# Подключение к базе данных SQLite
conn = sqlite3.connect('conversations.db')
cursor = conn.cursor()

# Создаём таблицы для переписок и пользователей, если их нет
cursor.execute('''
    CREATE TABLE IF NOT EXISTS conversations (
        user_id INTEGER,
        role TEXT,
        content TEXT
    )
''')
cursor.execute('''
    CREATE TABLE IF NOT EXISTS users (
        user_id INTEGER PRIMARY KEY
    )
''')
conn.commit()

# Функция для сохранения ID пользователя
def save_user(user_id: int):
    cursor.execute('INSERT OR IGNORE INTO users (user_id) VALUES (?)', (user_id,))
    conn.commit()

# Функция для получения всех ID пользователей
def get_all_users() -> List[int]:
    cursor.execute('SELECT user_id FROM users')
    rows = cursor.fetchall()
    return [row[0] for row in rows]

# Функция для сохранения сообщений в базе данных
def save_message(user_id: int, role: str, content: str):
    cursor.execute(
        'INSERT INTO conversations (user_id, role, content) VALUES (?, ?, ?)',
        (user_id, role, content)
    )
    conn.commit()

# Описание стиля общения бота
SYSTEM_PROMPT = {
    "role": "system",
    "content": (
        "Ты — старый тренер по волейболу, который жил в советском союзе. Ты строгий, придирчивый и любишь покритиковать. "
        "Обращаешься ко всем на 'ты'. Ненавидишь все другие командные виды спорта и современные увлечения, такие как аниме. "
        "На шутки реагируешь негативно, часто критикуешь и напоминаешь о старых временах."
    )
}

# Функция для загрузки переписки из базы данных
def load_conversation(user_id: int) -> List[Dict[str, str]]:
    cursor.execute('SELECT role, content FROM conversations WHERE user_id = ?', (user_id,))
    rows = cursor.fetchall()

    # Всегда начинаем с SYSTEM_PROMPT, если переписки нет
    conversation = [SYSTEM_PROMPT]
    if rows:
        conversation.extend([{'role': role, 'content': content} for role, content in rows])
    
    return conversation

# Функция для общения с OpenAI GPT-4 Turbo
async def ask_openai(user_id: int, prompt: str) -> str:
    conversation = load_conversation(user_id)  # Загружаем переписку

    conversation.append({"role": "user", "content": prompt})
    save_message(user_id, "user", prompt)  # Сохраняем сообщение пользователя

    try:
        response = await openai.ChatCompletion.acreate(
            model="gpt-4-turbo",
            messages=conversation,
            temperature=0.7
        )
        bot_reply = response["choices"][0]["message"]["content"].strip()
        save_message(user_id, "assistant", bot_reply)  # Сохраняем ответ бота
        return bot_reply
    except Exception as e:
        logging.error(f"Ошибка при обращении к OpenAI: {e}")
        return "Извините, произошла ошибка при обработке вашего запроса."

# Команда для рассылки сообщений всем пользователям
@dp.message_handler(commands=["broadcast"])
async def broadcast_message(message: types.Message):
    if message.from_user.id != ADMIN_ID:
        await message.answer("У тебя нет прав для использования этой команды.")
        return

    text = message.text[len("/broadcast "):].strip()
    if not text:
        await message.answer("Пожалуйста, напиши сообщение для рассылки.")
        return

    users = get_all_users()
    for user_id in users:
        try:
            await bot.send_message(user_id, text)
        except Exception as e:
            logging.error(f"Не удалось отправить сообщение пользователю {user_id}: {e}")

    await message.answer("Рассылка завершена!")

# Хендлер для обработки сообщений от пользователей
@dp.message_handler()
async def handle_message(message: types.Message):
    user_id = message.from_user.id
    save_user(user_id)  # Сохраняем ID пользователя
    await bot.send_chat_action(chat_id=message.chat.id, action="typing")  # Эффект "печатает..."
    reply = await ask_openai(user_id, message.text)  # Получаем ответ от OpenAI
    await message.answer(reply)  # Отправляем ответ пользователю

# Запуск бота
if __name__ == "__main__":
    executor.start_polling(dp, skip_updates=True)
