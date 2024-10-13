import openai
import logging
import sqlite3
from aiogram import Bot, Dispatcher, types, executor
from typing import List, Dict
import tiktoken  # Для подсчёта токенов

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

# Описание стиля общения бота
SYSTEM_PROMPT = {
    "role": "system",
    "content": (
        "Ты — старый тренер по волейболу, который жил в советском союзе. Ты строгий, придирчивый и любишь покритиковать. "
        "Обращаешься ко всем на 'ты'. Ненавидишь все другие командные виды спорта и современные увлечения, такие как аниме. "
        "На шутки реагируешь негативно, часто критикуешь и напоминаешь о старых временах."
    )
}

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

# Функция для загрузки переписки
def load_conversation(user_id: int, limit: int = 10) -> List[Dict[str, str]]:
    cursor.execute('SELECT role, content FROM conversations WHERE user_id = ? ORDER BY rowid DESC LIMIT ?', (user_id, limit))
    rows = cursor.fetchall()

    # Всегда начинаем с SYSTEM_PROMPT
    conversation = [SYSTEM_PROMPT]
    if rows:
        conversation.extend(reversed([{'role': role, 'content': content} for role, content in rows]))
    
    return conversation

# Функция для подсчёта токенов
def count_tokens(messages: List[Dict[str, str]], model: str = "gpt-4-turbo") -> int:
    encoding = tiktoken.encoding_for_model(model)
    num_tokens = 0
    for message in messages:
        num_tokens += len(encoding.encode(message['content']))
    return num_tokens

# Функция для общения с OpenAI
async def ask_openai(user_id: int, prompt: str, model: str = "gpt-4-turbo") -> str:
    conversation = load_conversation(user_id)

    conversation.append({"role": "user", "content": prompt})
    save_message(user_id, "user", prompt)

    # Ограничиваем переписку до 3000 токенов
    while count_tokens(conversation, model=model) > 3000:
        conversation.pop(1)  # Удаляем самые старые сообщения

    try:
        response = await openai.ChatCompletion.acreate(
            model=model,
            messages=conversation,
            temperature=0.7
        )
        bot_reply = response["choices"][0]["message"]["content"].strip()
        save_message(user_id, "assistant", bot_reply)
        return bot_reply
    except Exception as e:
        logging.error(f"Ошибка при обращении к OpenAI: {e}")
        return "Извините, произошла ошибка при обработке вашего запроса."

# Команда для смены модели (GPT-3.5 или GPT-4)
@dp.message_handler(commands=["setmodel"])
async def set_model(message: types.Message):
    if message.from_user.id != ADMIN_ID:
        await message.answer("У тебя нет прав для использования этой команды.")
        return

    model = message.text[len("/setmodel "):].strip()
    if model not in ["gpt-3.5-turbo", "gpt-4-turbo"]:
        await message.answer("Пожалуйста, выбери одну из моделей: gpt-3.5-turbo или gpt-4-turbo.")
        return

    await message.answer(f"Модель изменена на {model}.")

# Команда для рассылки сообщений
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

# Обработка сообщений от пользователей
@dp.message_handler()
async def handle_message(message: types.Message):
    user_id = message.from_user.id
    save_user(user_id)
    await bot.send_chat_action(chat_id=message.chat.id, action="typing")
    model = "gpt-3.5-turbo" if message.text.lower().startswith("3.5") else "gpt-4-turbo"
    reply = await ask_openai(user_id, message.text, model=model)
    await message.answer(reply)

# Запуск бота
if __name__ == "__main__":
    executor.start_polling(dp, skip_updates=True)

