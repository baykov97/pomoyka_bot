import logging
import asyncio
import json
import os
import nest_asyncio
from datetime import datetime, timezone
from telegram import Update
from telegram.constants import ParseMode
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, filters, ContextTypes
from pydub import AudioSegment
import speech_recognition as sr
import random
from dotenv import load_dotenv

# Список ответов для "Magic 8 Ball"
magic_8_ball_responses = [
    "Без сомнений", "Определенно да", "Никаких сомнений", "Да", "Очень вероятно",
    "Знаки говорят да", "Пока не ясно, попробуй снова", "Спроси позже",
    "Лучше не говорить сейчас", "Сконцентрируйся и спроси снова", "Не рассчитывай на это",
    "Мой ответ — нет", "Мои источники говорят нет", "Перспективы не очень хорошие", "Очень сомнительно",
    "Похуй", "А может похуй?", "Бля, отъебись", "Иди ка ты нахуй с такими вопросами",
    "Да я хуй знает, если честно", "А тебя это ебать не должно", "Ой блять, спроси че поумнее",
    "Ну а хули ты хотел?", "Да какая, блять, разница?", "Сам решай, я не гадалка.",
    "Ты серьезно спрашиваешь об этом?", "А смысл вообще задавать этот вопрос?",
    "Я не Гугл, найди сам.", "Зачем тебе это знать? Живи своей жизнью.",
    "Конечно, шо ты сомневаешься?", "Ты сам-то как думаешь?", "А ты попробуй — узнаешь.",
    "Ну, типа, да... Наверное...", "Мне пох, но если что — нет.", "Ты точно готов услышать правду?",
    "Бля, ну ты и выдал вопрос!", "Да ладно тебе париться, все будет норм.",
    "Окей, братан, давай так: да.", "Типа того, но не факт.", "Не знаю, я не в теме ваших дел.",
    "А ты сам как считаешь? Я просто шар.", "Это же очевидно, бро.", "Шаришь за жизнь? Тогда сам догадайся.",
    "Ну такое, знаешь ли...", "Да без разницы, честно.", "Ты меня вообще за кого принимаешь? Я не всезнайка!",
    "Пиздаболство какое-то, а не вопрос.", "Бля, ну ты и придумал тему!", "Я бы на твоем месте не парился.",
    "Ну допустим... А дальше что?", "А смысл вообще в этом разбираться?", "Лучше спроси у кота.",
    "Я бы мог ответить, но мне лень.", "А ты уверен, что хочешь услышать правду?", "Ну, короче, да. Но не факт.",
    "Попробуй снова, но уже с чувством.", "Это секретная информация, доступная только избранным.",
    "Даже если я скажу, ты все равно не поймешь.",
    "Слушай, я не психолог, разберись сам.", "Все зависит от того, как ты посмотришь на ситуацию.",
    "Вселенная говорит «да», но ты можешь спросить еще раз.",
    "Ответ есть, но он находится за пределами твоего понимания.",
    "Истина где-то рядом, но не здесь.", "А что такое «правда» вообще?"
]
# Включаем логирование
logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)

# Разрешаем вложенные циклы событий
nest_asyncio.apply()

# Загрузка переменных окружения из .env файла
load_dotenv()


# Проверка, что токен и chat_id загружены
TELEGRAM_TOKEN = os.getenv('TELEGRAM_TOKEN')  # Ваш токен, полученный от BotFather
if not TELEGRAM_TOKEN:
    print("Ошибка: не заданы TELEGRAM_TOKEN в .env файле.")
    exit(1)

# Путь к файлу для сохранения данных
DATA_FILE = "data/active_users.json"

# Загружаем данные из файла, если он существует
if os.path.exists(DATA_FILE):
    with open(DATA_FILE, 'r') as file:
        chat_data = json.load(file)
else:
    chat_data = {}  # Если файла нет, создаем пустой словарь

# Флаг для отслеживания состояния бота
bot_active = False

# Время, когда бот запустился
bot_start_time = datetime.now(timezone.utc)


# Функция для сохранения данных в файл
def save_data():
    try:
        with open(DATA_FILE, 'w') as file:
            json.dump(chat_data, file)
    except Exception as e:
        logging.error(f"Ошибка при сохранении данных: {e}")


# Функция для добавления пользователей
async def add_user(update: Update) -> None:
    try:
        chat_id = str(update.effective_chat.id)  # Приводим chat_id к строке для использования в JSON
        user = update.message.from_user

        # Если для чата еще нет данных, создаем новый список участников
        if chat_id not in chat_data:
            chat_data[chat_id] = []

        # Проверяем, есть ли пользователь в списке
        user_exists = False
        for member in chat_data[chat_id]:
            if member["id"] == user.id:
                user_exists = True
                break

        # Если пользователя нет, добавляем его
        if not user_exists:
            new_user = {
                "id": user.id,
                "first_name": user.first_name,
                "nickname": ""  # Пустой никнейм по умолчанию
            }
            chat_data[chat_id].append(new_user)
            logging.info(f"Добавлен пользователь: {user.id} ({user.first_name}) в чат {chat_id}")

        # Сохраняем данные в файл
        save_data()
    except Exception as e:
        logging.error(f"Ошибка при добавлении пользователя: {e}")


# Добавляем новую функцию для реакции на ключевые слова
async def add_keyword_response(update: Update, keywords, response_text) -> None:
    try:
        # Проверяем, является ли это сообщение накопившимся
        message_time = update.message.date
        if message_time < bot_start_time:
            logging.info(f"Игнорируем накопившееся сообщение от {update.message.from_user.first_name}")
            return

        # Проверяем, содержит ли сообщение текст
        if not hasattr(update.message, 'text') or update.message.text is None:
            logging.info("Сообщение не содержит текста, игнорируем")
            return

        # Проверяем, содержит ли сообщение одно из ключевых слов
        message_text = update.message.text.lower()
        if any(keyword.lower() in message_text for keyword in keywords):
            await update.message.reply_text(response_text)
    except Exception as e:
        logging.error(f"Ошибка при обработке реакции на ключевые слова: {e}")


# Функция-обработчик всех сообщений для использования add_keyword_response
async def handle_keyword_responses(update: Update) -> None:
    await add_keyword_response(update, ["майнкрафт", "minecraft"], "Кто сказал майнкрафт?")


# Обновляем основной обработчик сообщений, добавляя функцию handle_keyword_responses
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    try:
        # Добавляем пользователя из сообщения
        await add_user(update)
        # Вызываем обработчик ключевых слов
        await handle_keyword_responses(update)

    except Exception as e:
        logging.error(f"Ошибка при обработке сообщения: {e}")


# Функция для команды /tag_all
async def tag_all(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    try:
        # Проверяем, является ли это сообщение накопившимся
        message_time = update.message.date
        if message_time < bot_start_time:
            logging.info(f"Игнорируем накопившееся /tag_all сообщение от {update.message.from_user.first_name}")
            return

        chat_id = str(update.effective_chat.id)

        # Проверяем, есть ли активные пользователи для этого чата
        if chat_id not in chat_data or not chat_data[chat_id]:
            await update.message.reply_text("Никто не взаимодействовал с ботом.")
            return

        mention_text = ""
        errors_count = 0  # Для подсчета ошибок при получении участников

        # Проходим по списку участников чата
        for member in chat_data[chat_id]:
            try:
                user_id = member["id"]
                nickname = member["nickname"]
                first_name = member["first_name"]

                if not nickname and not first_name:
                    # Если first_name не задан, получаем его данные из Telegram
                    user_info = await context.bot.get_chat_member(update.effective_chat.id, user_id)
                    first_name = user_info.user.first_name
                    member["first_name"] = first_name
                    save_data()

                # Используем nickname, если он задан, иначе first_name
                display_name = nickname if nickname else first_name
                mention_text += f"[{display_name}](tg://user?id={user_id}) "
            except Exception as e:
                logging.error(f"Ошибка при получении участника {user_id}: {e}")
                errors_count += 1

        if errors_count > 0:
            logging.warning(f"Не удалось получить {errors_count} участников из {len(chat_data[chat_id])}.")

        # Проверка длины строки
        if len(mention_text) > 4096:
            await update.message.reply_text("Слишком много участников для упоминания в одном сообщении.")
        elif mention_text:
            await update.message.reply_text(mention_text, parse_mode=ParseMode.MARKDOWN)
        else:
            await update.message.reply_text("Не удалось упомянуть участников.")
    except Exception as e:
        logging.error(f"Ошибка при выполнении команды /tag_all: {e}")
        await update.message.reply_text("Произошла ошибка при выполнении команды.")


# Функция для команды /check_all
async def check_all(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    try:
        # Проверяем, является ли это сообщение накопившимся
        message_time = update.message.date
        if message_time < bot_start_time:
            logging.info(f"Игнорируем накопившееся /check_all сообщение от {update.message.from_user.first_name}")
            return

        chat_id = str(update.effective_chat.id)

        # Проверяем, есть ли активные пользователи для этого чата
        if chat_id not in chat_data or not chat_data[chat_id]:
            await update.message.reply_text("Нет активных пользователей в этом чате.")
            return

        user_names = []
        errors_count = 0  # Для подсчета ошибок при получении участников

        # Получаем общее количество участников в чате
        chat_members_count = await context.bot.get_chat_member_count(update.effective_chat.id)

        for member in chat_data[chat_id]:
            try:
                user_id = member["id"]
                nickname = member["nickname"]
                first_name = member["first_name"]

                if not nickname and not first_name:
                    # Если first_name не задан, получаем его данные из Telegram
                    user_info = await context.bot.get_chat_member(update.effective_chat.id, user_id)
                    first_name = user_info.user.first_name
                    member["first_name"] = first_name
                    save_data()

                # Используем nickname, если он задан, иначе first_name
                display_name = nickname if nickname else first_name
                user_names.append(display_name)
            except Exception as e:
                logging.error(f"Ошибка при получении участника {user_id}: {e}")
                errors_count += 1

        # Формируем ответ
        if user_names:
            user_count = len(user_names)
            user_list = "\n".join(user_names)
            missing_members_count = chat_members_count - user_count - 1  # Рассчитываем недостающих участников, исключая бота

            response_text = f"Участники:\n{user_list}\n\n"
            if missing_members_count == 0:
                response_text += "Список пидоров сформирован."
            else:
                response_text += f"Не хватает {missing_members_count} пидоров."
        else:
            response_text = "Нет активных пользователей в этом чате."

        await update.message.reply_text(response_text)
    except Exception as e:
        logging.error(f"Ошибка при выполнении команды /check_all: {e}")
        await update.message.reply_text("Произошла ошибка при выполнении команды.")


# Функция для обработки голосовых сообщений
async def voice_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    try:
        # Проверяем, является ли это сообщение накопившимся
        message_time = update.message.date
        if message_time < bot_start_time:
            logging.info(f"Игнорируем накопившееся голосовое сообщение от {update.message.from_user.first_name}")
            return

        # Передаем голосовое сообщение для расшифровки
        await transcribe_voice(update, context, message=update.message)

    except Exception as e:
        logging.error(f"Ошибка при обработке голосового сообщения: {e}")


# Функция для расшифровки голосового сообщения или кружочка
async def transcribe_voice(update: Update, context: ContextTypes.DEFAULT_TYPE, message=None) -> None:
    file_path = None
    wav_path = None

    try:
        # Проверяем, является ли это сообщение накопившимся
        message_time = update.message.date
        if message_time < bot_start_time:
            logging.info(f"Игнорируем накопившееся /voice сообщение от {update.message.from_user.first_name}")
            return

        # Используем текущее сообщение, если оно передано
        if message is None:
            if update.message.reply_to_message and (
                    update.message.reply_to_message.voice or update.message.reply_to_message.video_note):
                message = update.message.reply_to_message
            else:
                await update.message.reply_text("Ответьте на голосовое сообщение или кружочек, чтобы его расшифровать.")
                return

        # Определяем, какой тип сообщения обрабатываем (голосовое или видеосообщение)
        if message.voice:
            # Обрабатываем голосовое сообщение
            file = await context.bot.get_file(message.voice.file_id)
            file_path = f"voice_{message.message_id}.ogg"
        elif message.video_note:
            # Обрабатываем видеосообщение (кружочек)
            file = await context.bot.get_file(message.video_note.file_id)
            file_path = f"video_note_{message.message_id}.mp4"
        else:
            await update.message.reply_text("Сообщение не содержит голосового сообщения или кружочка.")
            return

        # Сохраняем файл
        await file.download_to_drive(file_path)

        # Конвертируем файл в WAV
        if message.video_note:
            # Извлекаем аудио из видеосообщения
            audio = AudioSegment.from_file(file_path, format="mp4")
        else:
            # Конвертируем OGG файл в WAV
            audio = AudioSegment.from_file(file_path, format="ogg")

        wav_path = file_path.replace(".ogg", ".wav").replace(".mp4", ".wav")
        audio.export(wav_path, format="wav")

        # Используем распознавание речи
        recognizer = sr.Recognizer()
        with sr.AudioFile(wav_path) as source:
            audio_data = recognizer.record(source)
            text = recognizer.recognize_google(audio_data, language="ru-RU")

        await update.message.reply_text(f"Распознанный текст: {text}")

    except Exception as e:
        logging.error(f"Ошибка при расшифровке голосового сообщения: {e}")
        await update.message.reply_text("Произошла ошибка при расшифровке голосового сообщения.")

    finally:
        # Удаляем временные файлы, если они существуют
        if file_path and os.path.exists(file_path):
            os.remove(file_path)
        if wav_path and os.path.exists(wav_path):
            os.remove(wav_path)


# Функция для команды /eball, которая отвечает на сообщение
async def eball(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    try:
        # Проверяем, является ли это сообщение накопившимся
        message_time = update.message.date
        if message_time < bot_start_time:
            logging.info(f"Игнорируем накопившееся /eball сообщение от {update.message.from_user.first_name}")
            return

        # Проверяем, есть ли сообщение, на которое отвечает бот
        if update.message.reply_to_message:
            # Получаем текст сообщения, на которое бот отвечает
            original_message = update.message.reply_to_message.text

            # Случайный выбор ответа из списка
            response = random.choice(magic_8_ball_responses)

            # Отправляем ответ, прикрепленный к оригинальному сообщению
            await update.message.reply_text(f"{response}",
                                            reply_to_message_id=update.message.reply_to_message.message_id)
        else:
            # Если команда не была ответом на сообщение, сообщаем об этом
            await update.message.reply_text("Команда /eball должна быть ответом на сообщение.")

    except Exception as e:
        logging.error(f"Ошибка при выполнении команды /eball: {e}")
        await update.message.reply_text("Произошла ошибка при выполнении команды.")

async def roll(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    Обработчик команды /roll.
    Возвращает случайное число в заданном диапазоне или от 1 до 100 по умолчанию.
    """
    try:
        # Проверяем, активен ли бот
        if not bot_active:
            await update.message.reply_text("Бот временно неактивен. Попробуйте позже.")
            return

        # Проверяем, является ли это сообщение накопившимся
        message_time = update.message.date
        if message_time < bot_start_time:
            logging.info(f"Игнорируем накопившееся /eball сообщение от {update.message.from_user.first_name}")
            return

        # Получаем текст сообщения пользователя
        user_input = update.message.text.strip()

        # Проверяем, есть ли параметры после команды /roll
        if len(user_input.split()) > 1:
            # Извлекаем диапазон из сообщения
            range_part = user_input.split(maxsplit=1)[1]
            if '-' in range_part:
                start, end = map(int, range_part.split('-'))
                if start > end:
                    await update.message.reply_text("Ошибка: начальное число должно быть меньше конечного.")
                    return
            else:
                await update.message.reply_text("Неверный формат диапазона. Используйте /roll X-Y.")
                return
        else:
            # Если диапазон не указан, используем значения по умолчанию
            start, end = 1, 100

        # Генерируем случайное число в указанном диапазоне
        random_number = random.randint(start, end)

        # Отправляем результат пользователю
        await update.message.reply_text(f"🎲 Результат: {random_number}")
    except ValueError:
        await update.message.reply_text("Ошибка: убедитесь, что вы ввели числа в правильном формате.")
    except Exception as e:
        logging.error(f"Ошибка при выполнении команды /roll: {e}")
        await update.message.reply_text("Произошла ошибка. Попробуйте снова.")

async def main() -> None:
    global bot_active, bot_start_time

    try:
        # Замените 'YOUR_TOKEN_HERE' на токен вашего бота
        app = ApplicationBuilder().token(TELEGRAM_TOKEN).build()

        # Регистрируем обработчики
        app.add_handler(CommandHandler("tag_all", tag_all))
        app.add_handler(CommandHandler("check_all", check_all))  # Добавляем обработчик команды /check_all
        app.add_handler(CommandHandler("voice", transcribe_voice))  # Добавляем обработчик команды /voice
        app.add_handler(CommandHandler("eball", eball))  # Добавляем обработчик команды /eball
        app.add_handler(CommandHandler("roll", roll))  # Добавляем обработчик команды /roll
        app.add_handler(MessageHandler(filters.VOICE, voice_handler))  # Добавляем обработчик голосовых сообщений
        app.add_handler(MessageHandler(filters.ALL, handle_message))  # Обрабатываем все сообщения

        # Устанавливаем флаг активности бота и время старта
        bot_active = True
        bot_start_time = datetime.now(timezone.utc)

        # Запускаем бота без сброса накопившихся сообщений
        await app.run_polling(drop_pending_updates=False)
    except Exception as e:
        logging.error(f"Ошибка в основном цикле бота: {e}")


if __name__ == '__main__':
    asyncio.run(main())
