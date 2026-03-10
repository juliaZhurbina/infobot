"""
Основной файл Telegram-бота для сбора и анализа новостей
"""
import logging
import asyncio
import os
import tempfile
from datetime import datetime
from telegram import Update
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    filters,
    ContextTypes
)
from telegram.constants import ChatType
from telegram.error import TimedOut, BadRequest, Conflict, NetworkError

from config import (
    TELEGRAM_BOT_TOKEN,
    ADMIN_IDS,
    UPDATE_INTERVAL,
    NEWS_TOPICS,
    INDUSTRY_DISPLAY_NAMES,
    INDUSTRY_SOURCES,
    GENERAL_SOURCES,
    SUMMARY_CHAT_ID,
)
from news_collector import NewsCollector
from news_processor import NewsProcessor

# Импорт для чтения каналов через Client API
try:
    from channel_reader import ChannelReader
    import os
    from dotenv import load_dotenv
    load_dotenv()
    CHANNEL_READER_AVAILABLE = bool(os.getenv("TELEGRAM_API_ID") and os.getenv("TELEGRAM_API_HASH"))
except ImportError:
    CHANNEL_READER_AVAILABLE = False

# Настройка логирования
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO,
    handlers=[
        logging.FileHandler('bot.log', encoding='utf-8'),
        logging.StreamHandler()  # Вывод в консоль
    ]
)
logger = logging.getLogger(__name__)

# Глобальные объекты
news_collector = NewsCollector()
news_processor = NewsProcessor()


async def safe_send_message(update_or_context, text: str, max_retries: int = 3, chat_id=None, **kwargs):
    """
    Безопасная отправка сообщения с обработкой ошибок и retry логикой
    
    Args:
        update_or_context: Update объект или ContextTypes.DEFAULT_TYPE
        text: Текст сообщения
        max_retries: Максимальное количество попыток
        chat_id: ID чата для отправки (если используется context)
        **kwargs: Дополнительные параметры для reply_text/send_message
    """
    for attempt in range(max_retries):
        try:
            if isinstance(update_or_context, Update):
                return await update_or_context.message.reply_text(text, **kwargs)
            else:
                # Это context для send_message
                target_chat_id = chat_id or kwargs.pop('chat_id', None)
                if target_chat_id:
                    return await update_or_context.bot.send_message(chat_id=target_chat_id, text=text, **kwargs)
                else:
                    raise ValueError("chat_id required for context")
        except (TimedOut, NetworkError) as e:
            if attempt < max_retries - 1:
                wait_time = (attempt + 1) * 2
                logger.warning(f"Ошибка сети/таймаут при отправке, попытка {attempt + 1}/{max_retries}. Повтор через {wait_time} сек...")
                await asyncio.sleep(wait_time)
            else:
                logger.error(f"Не удалось отправить сообщение после {max_retries} попыток")
                raise
        except BadRequest as e:
            # Ошибка 400 может быть из-за удаленного сообщения или других проблем
            logger.error(f"BadRequest при отправке сообщения: {e}")
            raise
        except Exception as e:
            logger.error(f"Неожиданная ошибка при отправке сообщения: {e}")
            raise


async def send_long_message(update_or_context, text: str, chunk_size: int = 3500, chat_id=None):
    """
    Отправка длинного текста частями с паузой между частями (снижает таймауты и ReadError).
    """
    for i in range(0, len(text), chunk_size):
        chunk = text[i : i + chunk_size]
        await safe_send_message(update_or_context, chunk, chat_id=chat_id)
        if i + chunk_size < len(text):
            await asyncio.sleep(0.4)


async def safe_edit_message(message, text: str, max_retries: int = 3, **kwargs):
    """
    Безопасное редактирование сообщения с обработкой ошибок
    
    Args:
        message: Message объект для редактирования
        text: Новый текст сообщения
        max_retries: Максимальное количество попыток
        **kwargs: Дополнительные параметры для edit_text
    """
    for attempt in range(max_retries):
        try:
            return await message.edit_text(text, **kwargs)
        except TimedOut:
            if attempt < max_retries - 1:
                wait_time = (attempt + 1) * 2
                logger.warning(f"Timeout при редактировании сообщения, попытка {attempt + 1}/{max_retries}. Повтор через {wait_time} сек...")
                await asyncio.sleep(wait_time)
            else:
                logger.error(f"Не удалось отредактировать сообщение после {max_retries} попыток")
                # Не выбрасываем исключение, просто логируем
                return None
        except BadRequest as e:
            # Сообщение могло быть удалено или изменено
            if "message to edit not found" in str(e).lower() or "message is not modified" in str(e).lower():
                logger.warning(f"Сообщение не найдено или не изменено: {e}")
                return None
            else:
                logger.error(f"BadRequest при редактировании сообщения: {e}")
                raise
        except Exception as e:
            logger.error(f"Неожиданная ошибка при редактировании сообщения: {e}")
            return None


async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик команды /start"""
    is_admin = ADMIN_IDS and update.effective_user.id in ADMIN_IDS
    
    welcome_message = """
👋 Добро пожаловать в бота для сбора и анализа новостей!

Этот бот собирает новости из официальных каналов и создает краткие сводки с помощью GigaChat AI.

📋 Команды:
/summary_topic <отрасль> — тезисная сводка по отрасли → выбор новости для инфоповода
/topics — показать 10 отраслей
/help — справка

💡 Отрасли: ЕКОМ, розничная/оптовая торговля, услуги, транспорт, недвижимость, рестораны, отели, производство, строительство.
"""
    
    # Показываем служебные команды только администраторам
    if is_admin:
        welcome_message += """
        
🔧 Служебные команды (только для администраторов):
/stats - Статистика по новостям
/fetch_news - Ручной сбор новостей из каналов
/publish - Опубликовать сводки в группу
/get_chat_id - Получить ID текущего чата
/channels - Список отслеживаемых каналов
"""
    
    await update.message.reply_text(welcome_message)


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик команды /help"""
    is_admin = ADMIN_IDS and update.effective_user.id in ADMIN_IDS
    
    help_text = """
📖 СПРАВКА ПО КОМАНДАМ

📋 ОСНОВНЫЕ КОМАНДЫ:

/summary_topic <отрасль> — сводка по выбранной отрасли
   • Собирает новости по отрасли и выдает тезисную сводку
   • По номеру новости или своему тексту — полный инфоповод по структуре
   • Примеры: /summary_topic транспорт, /summary_topic производство

/topics — показать 10 отраслей

🎯 Отрасли: ЕКОМ, розничная торговля, оптовая торговля, услуги, транспорт, недвижимость, рестораны, отели, производство, строительство.
"""
    
    # Показываем служебные команды только администраторам
    if is_admin:
        help_text += """
        
🔧 СЛУЖЕБНЫЕ КОМАНДЫ (только для администраторов):

/stats - Показать статистику по собранным новостям
   • Общее количество новостей в базе
   • Новости за последние 24 часа
   • Статистика по источникам

/fetch_news - Вручную собрать новости из каналов
   • Обновляет базу данных новостей
   • Используется перед генерацией сводок

/export_relevant - Выгрузить релевантные новости в Excel
   • Новости из БД (channel_reader), за последние 24 часа
   • Фильтрует релевантные через GigaChat; в файле дата — публикация в канале

/export_relevant_week - Выгрузить релевантные новости за неделю в Excel
   • Новости из БД (channel_reader), за последние 7 дней
   • Фильтрует релевантные через GigaChat; в файле дата — публикация в канале

/export_all - Выгрузить все новости за 24 часа в Excel
   • Новости из БД (channel_reader), за последние 24 часа
   • Без фильтра релевантности; в файле дата — публикация в канале

/export_all_week - Выгрузить все новости за неделю в Excel
   • Новости из БД (channel_reader), за последние 7 дней
   • Без фильтра релевантности; в файле дата — публикация в канале

/publish - Опубликовать сводки по всем темам в группу
   • Генерирует сводки по всем темам
   • Отправляет их в указанную группу (SUMMARY_CHAT_ID)

/get_chat_id - Получить ID текущего чата/канала/группы
   • Для настройки SUMMARY_CHAT_ID в .env

/channels - Показать список отслеживаемых каналов
"""
    
    await update.message.reply_text(help_text)


async def summary_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Редирект: используйте /summary_topic <отрасль>. Одна команда для всех отраслей."""
    await safe_send_message(
        update,
        "Используйте команду с указанием отрасли:\n"
        "/summary_topic <отрасль>\n\n"
        "Список отраслей: /topics"
    )


async def summary_topic_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик команды /summary_topic: тезисная сводка по теме → вопрос по какой новости сделать инфоповод."""
    if not context.args:
        # Общая сводка по общим каналам
        status_msg = None
        try:
            status_msg = await safe_send_message(update, "⏳ Генерирую общую тезисную сводку по общим каналам...")

            thesis_text, news_data = news_processor.get_news_and_thesis_summary_by_sources(
                source_names=list(GENERAL_SOURCES.keys()), hours=24
            )

            try:
                await status_msg.delete()
            except Exception:
                pass

            if not news_data:
                await safe_send_message(update, thesis_text)
                return

            # Полный нумерованный список
            max_title_len = 200
            lines = []
            for i, item in enumerate(news_data, 1):
                title = item.get("title", "")
                if len(title) > max_title_len:
                    title = title[: max_title_len - 1] + "…"
                source = item.get("source", "—")
                lines.append(f"{i}. {title} [Источник: {source}]")
            thesis_body = "\n".join(lines)
            header = "📋 **Общая тезисная сводка (общие каналы):**\n\n"
            full_thesis = header + thesis_body
            msg_limit = 4000
            if len(full_thesis) <= msg_limit:
                await safe_send_message(update, full_thesis)
            else:
                await safe_send_message(update, header + thesis_body[: msg_limit - len(header)])
                for j in range(msg_limit - len(header), len(thesis_body), msg_limit):
                    await safe_send_message(update, thesis_body[j : j + msg_limit])
                    await asyncio.sleep(0.3)

            n = len(news_data)
            await safe_send_message(
                update,
                f"По какой новости сделать инфоповод? Введите номер от 1 до {n}, пришлите ссылку на пост (t.me/…) или свой текст новости — сделаю инфоповод по той же структуре."
            )

            context.user_data["infopovod_news_list"] = news_data
            context.user_data["awaiting_infopovod"] = True
            context.user_data["infopovod_topic"] = None
            return
        except Exception as e:
            logger.error(f"Ошибка при генерации общей сводки: {e}", exc_info=True)
            if status_msg:
                await safe_edit_message(status_msg, f"❌ Произошла ошибка: {str(e)}")
            else:
                await safe_send_message(update, f"❌ Произошла ошибка: {str(e)}")
            return
    
    topic = " ".join(context.args).lower().strip()
    
    if topic not in NEWS_TOPICS:
        await update.message.reply_text(
            f"❌ Отрасль «{topic}» не найдена.\n"
            "Используйте /topics для просмотра доступных отраслей."
        )
        return
    
    status_msg = None
    try:
        display_name = INDUSTRY_DISPLAY_NAMES.get(topic, topic)
        status_msg = await safe_send_message(update, f"⏳ Генерирую тезисную сводку по отрасли «{display_name}»...")
        
        limit_sources = 5 if INDUSTRY_SOURCES.get(topic) else None
        thesis_text, news_data = news_processor.get_news_and_thesis_summary(
            topic=topic, limit_sources=limit_sources
        )
        
        try:
            await status_msg.delete()
        except Exception:
            pass
        
        if not news_data:
            await safe_send_message(update, thesis_text)
            return
        
        # Полный нумерованный список из news_data (все пункты)
        max_title_len = 200
        lines = []
        for i, item in enumerate(news_data, 1):
            title = item.get("title", "")
            if len(title) > max_title_len:
                title = title[: max_title_len - 1] + "…"
            source = item.get("source", "—")
            lines.append(f"{i}. {title} [Источник: {source}]")
        thesis_body = "\n".join(lines)
        display_name = INDUSTRY_DISPLAY_NAMES.get(topic, topic)
        header = f"📋 **Краткая тезисная сводка ({display_name}):**\n\n"
        full_thesis = header + thesis_body
        msg_limit = 4000
        if len(full_thesis) <= msg_limit:
            await safe_send_message(update, full_thesis)
        else:
            await safe_send_message(update, header + thesis_body[: msg_limit - len(header)])
            for j in range(msg_limit - len(header), len(thesis_body), msg_limit):
                await safe_send_message(update, thesis_body[j : j + msg_limit])
                await asyncio.sleep(0.3)
        
        n = len(news_data)
        await safe_send_message(
            update,
            f"По какой новости сделать инфоповод? Введите номер от 1 до {n}, пришлите ссылку на пост (t.me/…) или свой текст новости — сделаю инфоповод по той же структуре."
        )

        context.user_data["infopovod_news_list"] = news_data
        context.user_data["awaiting_infopovod"] = True
        context.user_data["infopovod_topic"] = topic

    except Exception as e:
        logger.error(f"Ошибка при генерации сводки по теме {topic}: {e}", exc_info=True)
        try:
            if status_msg:
                await safe_edit_message(status_msg, f"❌ Произошла ошибка: {str(e)}")
            else:
                await safe_send_message(update, f"❌ Произошла ошибка: {str(e)}")
        except Exception:
            try:
                await update.message.reply_text(f"❌ Произошла ошибка: {str(e)}")
            except Exception:
                logger.error("Не удалось отправить сообщение об ошибке")


async def handle_infopovod_choice(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработка ввода номера новости для генерации полного инфоповода (после тезисной сводки)."""
    if not context.user_data.get("awaiting_infopovod"):
        return
    
    news_list = context.user_data.get("infopovod_news_list", [])
    if not news_list:
        context.user_data["awaiting_infopovod"] = False
        context.user_data.pop("infopovod_news_list", None)
        context.user_data.pop("infopovod_topic", None)
        return
    
    text = (update.message.text or "").strip()
    if not text.isdigit():
        # Не число — передаём в обработчик своей новости (если он обработает)
        return
    
    n = int(text)
    if n < 1 or n > len(news_list):
        await safe_send_message(
            update,
            f"Введите число от 1 до {len(news_list)}, пришлите ссылку на пост (t.me/…) или свой текст новости."
        )
        return
    
    news_item = news_list[n - 1]
    topic = context.user_data.get("infopovod_topic")
    context.user_data["awaiting_infopovod"] = False
    context.user_data.pop("infopovod_news_list", None)
    context.user_data.pop("infopovod_topic", None)
    
    status_msg = None
    try:
        status_msg = await safe_send_message(update, "⏳ Генерирую инфоповод по выбранной новости...")
        
        infopovod = news_processor.generate_infopovod_for_news(news_item, topic=topic)
        sources = getattr(news_processor, "_last_sources", None) or [news_item.get("source", "")]
        formatted = news_processor.format_summary(infopovod, topic=topic, sources=sources)
        
        try:
            await status_msg.delete()
        except Exception:
            pass
        
        # Отправка частями с паузой — снижает таймауты и ReadError при нестабильной сети
        await send_long_message(update, formatted, chunk_size=3500)
    except Exception as e:
        logger.error(f"Ошибка при генерации инфоповода: {e}", exc_info=True)
        try:
            if status_msg:
                await safe_edit_message(status_msg, f"❌ Ошибка при генерации инфоповода: {str(e)}")
            else:
                await safe_send_message(update, f"❌ Ошибка при генерации инфоповода: {str(e)}")
        except Exception:
            await safe_send_message(update, f"❌ Ошибка: {str(e)}")


def _is_telegram_message_link(text: str) -> bool:
    """Проверяет, похож ли текст на ссылку на сообщение в Telegram."""
    import re
    text = (text or "").strip()
    return bool(re.match(r"https?://(?:t\.me|telegram\.me)/(?:[a-zA-Z0-9_]+/\d+|c/\d+/\d+)", text))


async def handle_infopovod_by_link(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработка присланной ссылки на пост Telegram — поиск новости в БД и генерация инфоповода."""
    if not context.user_data.get("awaiting_infopovod"):
        return
    text = (update.message.text or "").strip()
    if not _is_telegram_message_link(text):
        return
    topic = context.user_data.get("infopovod_topic")
    context.user_data["awaiting_infopovod"] = False
    context.user_data.pop("infopovod_news_list", None)
    context.user_data.pop("infopovod_topic", None)
    news_item = news_collector.get_news_by_telegram_link(text)
    if not news_item:
        await safe_send_message(
            update,
            "По этой ссылке новость в базе не найдена. Выполните сбор новостей (/fetch_news) или укажите номер из списка выше."
        )
        return
    news_item["source"] = news_item.get("source_name", "")
    status_msg = None
    try:
        status_msg = await safe_send_message(update, "⏳ Генерирую инфоповод по новости из ссылки...")
        infopovod = news_processor.generate_infopovod_for_news(news_item, topic=topic)
        sources = getattr(news_processor, "_last_sources", None) or [news_item.get("source_name", "")]
        formatted = news_processor.format_summary(infopovod, topic=topic, sources=sources)
        try:
            await status_msg.delete()
        except Exception:
            pass
        await send_long_message(update, formatted, chunk_size=3500)
    except Exception as e:
        logger.error(f"Ошибка при генерации инфоповода по ссылке: {e}", exc_info=True)
        try:
            if status_msg:
                await safe_edit_message(status_msg, f"❌ Ошибка при генерации инфоповода: {str(e)}")
            else:
                await safe_send_message(update, f"❌ Ошибка при генерации инфоповода: {str(e)}")
        except Exception:
            await safe_send_message(update, f"❌ Ошибка: {str(e)}")


async def handle_custom_news_for_infopovod(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработка ввода своей новости (текст) для генерации полного инфоповода по структуре."""
    if not context.user_data.get("awaiting_infopovod"):
        return
    text = (update.message.text or "").strip()
    if _is_telegram_message_link(text):
        return
    if not text or len(text) < 10:
        await safe_send_message(
            update,
            "Введите текст новости (хотя бы пару предложений), и я сделаю по нему инфоповод по той же структуре."
        )
        return
    
    topic = context.user_data.get("infopovod_topic")
    context.user_data["awaiting_infopovod"] = False
    context.user_data.pop("infopovod_news_list", None)
    context.user_data.pop("infopovod_topic", None)
    
    news_item = {
        "source": "Пользователь",
        "title": text[:150] + ("…" if len(text) > 150 else ""),
        "text": text[:3000],
    }
    
    status_msg = None
    try:
        status_msg = await safe_send_message(update, "⏳ Генерирую инфоповод по вашей новости...")
        
        infopovod = news_processor.generate_infopovod_for_news(news_item, topic=topic)
        formatted = news_processor.format_summary(infopovod, topic=topic, sources=["Пользователь"])
        
        try:
            await status_msg.delete()
        except Exception:
            pass
        
        await send_long_message(update, formatted, chunk_size=3500)
    except Exception as e:
        logger.error(f"Ошибка при генерации инфоповода по своей новости: {e}", exc_info=True)
        try:
            if status_msg:
                await safe_edit_message(status_msg, f"❌ Ошибка при генерации инфоповода: {str(e)}")
            else:
                await safe_send_message(update, f"❌ Ошибка при генерации инфоповода: {str(e)}")
        except Exception:
            await safe_send_message(update, f"❌ Ошибка: {str(e)}")


async def topics_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик команды /topics — показать 10 отраслей"""
    topics_text = "🎯 ОТРАСЛИ (10):\n\n"
    for i, topic in enumerate(NEWS_TOPICS, 1):
        display = INDUSTRY_DISPLAY_NAMES.get(topic, topic)
        topics_text += f"{i}. {display}\n"
    
    topics_text += "\n💡 Пример: /summary_topic транспорт или /summary_topic производство"
    
    await update.message.reply_text(topics_text)


async def stats_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик команды /stats - служебная команда"""
    # Проверяем права администратора (если ADMIN_IDS указаны)
    if ADMIN_IDS and update.effective_user.id not in ADMIN_IDS:
        await update.message.reply_text(
            "❌ Эта команда доступна только администраторам.\n\n"
            "Используйте /summary для получения сводки."
        )
        return
    
    try:
        stats_text = news_processor.get_news_statistics()
        
        # Статистика по отраслям (у которых заданы источники)
        for industry, sources in INDUSTRY_SOURCES.items():
            if sources:
                industry_news = news_collector.get_news_by_source(list(sources.keys()), hours=168)
                if industry_news:
                    stats_text += f"\n\n📂 {INDUSTRY_DISPLAY_NAMES.get(industry, industry)} (за 7 дней): {len(industry_news)} новостей"
                    stats_text += f"\n   Источники: {', '.join(sources.keys())}"
        
        # Общее количество новостей в базе
        total_news = news_collector.get_all_news_count()
        stats_text += f"\n\n📊 Всего новостей в базе: {total_news}"
        
        await update.message.reply_text(stats_text)
    except Exception as e:
        logger.error(f"Ошибка при получении статистики: {e}")
        await update.message.reply_text(f"❌ Произошла ошибка при получении статистики: {str(e)}")


async def get_chat_id_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик команды /get_chat_id - получение ID текущего чата (служебная команда)"""
    # Проверяем права администратора (если ADMIN_IDS указаны)
    if ADMIN_IDS and update.effective_user.id not in ADMIN_IDS:
        await update.message.reply_text(
            "❌ Эта команда доступна только администраторам."
        )
        return
    
    chat = update.effective_chat
    
    if not chat:
        await update.message.reply_text("❌ Не удалось определить чат.")
        return
    
    chat_id = chat.id
    chat_type = chat.type
    chat_title = chat.title or chat.username or "Личные сообщения"
    
    info_text = f"📋 ИНФОРМАЦИЯ О ЧАТЕ:\n\n"
    info_text += f"Тип: {chat_type}\n"
    info_text += f"Название: {chat_title}\n"
    info_text += f"ID чата: `{chat_id}`\n\n"
    
    if chat.username:
        info_text += f"Username: @{chat.username}\n"
        info_text += f"Можно использовать: `@{chat.username}` или `{chat_id}`\n"
    else:
        info_text += f"⚠️ У чата нет username, используйте ID: `{chat_id}`\n"
    
    info_text += f"\n💡 Скопируйте ID и добавьте в файл .env:\n"
    info_text += f"`SUMMARY_CHAT_ID={chat_id}`"
    
    await update.message.reply_text(info_text, parse_mode='Markdown')


async def channels_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик команды /channels - служебная команда"""
    # Проверяем права администратора (если ADMIN_IDS указаны)
    if ADMIN_IDS and update.effective_user.id not in ADMIN_IDS:
        await update.message.reply_text(
            "❌ Эта команда доступна только администраторам.\n\n"
            "Используйте /summary для получения сводки."
        )
        return
    
    from config import MONITORED_CHANNELS
    
    channels_text = "📡 ОТСЛЕЖИВАЕМЫЕ КАНАЛЫ:\n\n"
    
    # Группируем по категориям
    ministries = []
    agencies = []
    
    for name, username in MONITORED_CHANNELS.items():
        if any(keyword in name for keyword in ["Мин", "МИД", "МВД", "МЧС"]):
            ministries.append(f"{name} {username}")
        else:
            agencies.append(f"{name} {username}")
    
    channels_text += "📍 Министерства:\n"
    for channel in ministries[:10]:  # Показываем первые 10
        channels_text += f"• {channel}\n"
    
    if len(ministries) > 10:
        channels_text += f"... и еще {len(ministries) - 10} министерств\n"
    
    channels_text += "\n📍 Федеральные службы и агентства:\n"
    for channel in agencies[:10]:  # Показываем первые 10
        channels_text += f"• {channel}\n"
    
    if len(agencies) > 10:
        channels_text += f"... и еще {len(agencies) - 10} служб\n"
    
    channels_text += f"\nВсего отслеживается: {len(MONITORED_CHANNELS)} каналов"
    
    await update.message.reply_text(channels_text)


async def fetch_news_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик команды /fetch_news - ручной сбор новостей"""
    if not CHANNEL_READER_AVAILABLE:
        await update.message.reply_text(
            "❌ Сбор новостей через Client API не настроен.\n"
            "Добавьте TELEGRAM_API_ID и TELEGRAM_API_HASH в файл .env"
        )
        return
    
    status_msg = None
    try:
        status_msg = await safe_send_message(update, "📡 Начинаю сбор новостей из каналов... Это может занять время.")
        
        await fetch_news_from_channels()
        
        stats = news_collector.get_statistics()
        response_text = "✅ Новости успешно собраны!\n\n"
        response_text += f"📊 Статистика:\n"
        response_text += f"• Всего новостей в базе: {stats['total']}\n"
        response_text += f"• Новостей за 24ч: {stats['last_24h']}\n"
        for industry, sources in INDUSTRY_SOURCES.items():
            if sources:
                industry_news = news_collector.get_news_by_source(list(sources.keys()), hours=24)
                if industry_news:
                    response_text += f"• По отрасли {INDUSTRY_DISPLAY_NAMES.get(industry, industry)}: {len(industry_news)}\n"
        
        await safe_edit_message(status_msg, response_text)
    except Exception as e:
        logger.error(f"Ошибка при сборе новостей: {e}")
        error_msg = str(e)
        if "Требуется авторизация" in error_msg:
            try:
                await status_msg.edit_text(
                    "⚠️ Требуется авторизация в Telegram.\n\n"
                    "Запустите один раз в консоли:\n"
                    "`python channel_reader.py`\n\n"
                    "После авторизации сессия сохранится и будет использоваться автоматически."
                )
            except:
                await update.message.reply_text(
                    "⚠️ Требуется авторизация. Запустите 'python channel_reader.py' для первой авторизации."
                )
        else:
            try:
                await status_msg.edit_text(f"❌ Ошибка при сборе новостей: {error_msg}")
            except:
                await update.message.reply_text(f"❌ Ошибка при сборе новостей: {error_msg}")


async def export_relevant_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик команды /export_relevant — фильтрация всех отраслей по релевантности и выгрузка в Excel."""
    status_msg = None
    try:
        status_msg = await safe_send_message(
            update,
            "📡 Собираю новости по всем отраслям и фильтрую релевантные (GigaChat). Это может занять несколько минут…"
        )
        filepath = news_processor.export_relevant_news_to_excel(hours=24)
        if not filepath:
            await safe_edit_message(
                status_msg,
                "Релевантных новостей не найдено или произошла ошибка при выгрузке."
            )
            return
        with open(filepath, "rb") as f:
            await update.message.reply_document(
                document=f,
                filename=os.path.basename(filepath),
                caption="✅ Релевантные новости по всем отраслям (за последние 24 часа, дата — публикация в канале).",
            )
        await safe_edit_message(
            status_msg,
            f"✅ Готово. Файл отправлен: {os.path.basename(filepath)}"
        )
    except Exception as e:
        logger.error(f"Ошибка при выгрузке релевантных в Excel: {e}")
        try:
            if status_msg:
                await status_msg.edit_text(f"❌ Ошибка: {e}")
            else:
                await update.message.reply_text(f"❌ Ошибка при выгрузке: {e}")
        except Exception:
            await update.message.reply_text(f"❌ Ошибка при выгрузке: {e}")


async def export_relevant_week_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик команды /export_relevant_week — релевантные новости за неделю в Excel."""
    status_msg = None
    try:
        status_msg = await safe_send_message(
            update,
            "📡 Фильтрую релевантные новости за неделю (GigaChat) и выгружаю в Excel…"
        )
        filepath = news_processor.export_relevant_news_to_excel(hours=168)
        if not filepath:
            await safe_edit_message(status_msg, "Релевантных новостей за неделю не найдено или произошла ошибка.")
            return
        with open(filepath, "rb") as f:
            await update.message.reply_document(
                document=f,
                filename=os.path.basename(filepath),
                caption="✅ Релевантные новости по всем отраслям (за неделю, дата — публикация в канале).",
            )
        await safe_edit_message(status_msg, f"✅ Готово. Файл отправлен: {os.path.basename(filepath)}")
    except Exception as e:
        logger.error(f"Ошибка при выгрузке релевантных за неделю в Excel: {e}")
        try:
            if status_msg:
                await status_msg.edit_text(f"❌ Ошибка: {e}")
            else:
                await update.message.reply_text(f"❌ Ошибка при выгрузке: {e}")
        except Exception:
            await update.message.reply_text(f"❌ Ошибка при выгрузке: {e}")


async def export_all_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик команды /export_all — все новости за 24 часа в Excel (без фильтра релевантности)."""
    status_msg = None
    try:
        status_msg = await safe_send_message(update, "📤 Выгружаю все новости за 24 часа в Excel…")
        filepath = news_processor.export_all_news_to_excel(hours=24)
        if not filepath:
            await safe_edit_message(status_msg, "Новостей за 24 часа не найдено или произошла ошибка при выгрузке.")
            return
        with open(filepath, "rb") as f:
            await update.message.reply_document(
                document=f,
                filename=os.path.basename(filepath),
                caption="✅ Все новости (за последние 24 часа, дата — публикация в канале).",
            )
        await safe_edit_message(status_msg, f"✅ Готово. Файл отправлен: {os.path.basename(filepath)}")
    except Exception as e:
        logger.error(f"Ошибка при выгрузке всех новостей в Excel: {e}")
        try:
            if status_msg:
                await status_msg.edit_text(f"❌ Ошибка: {e}")
            else:
                await update.message.reply_text(f"❌ Ошибка при выгрузке: {e}")
        except Exception:
            await update.message.reply_text(f"❌ Ошибка при выгрузке: {e}")


async def export_all_week_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик команды /export_all_week — все новости за неделю в Excel (без фильтра релевантности)."""
    status_msg = None
    try:
        status_msg = await safe_send_message(update, "📤 Выгружаю все новости за неделю в Excel…")
        filepath = news_processor.export_all_news_to_excel(hours=168)
        if not filepath:
            await safe_edit_message(status_msg, "Новостей за неделю не найдено или произошла ошибка при выгрузке.")
            return
        with open(filepath, "rb") as f:
            await update.message.reply_document(
                document=f,
                filename=os.path.basename(filepath),
                caption="✅ Все новости (за неделю, дата — публикация в канале).",
            )
        await safe_edit_message(status_msg, f"✅ Готово. Файл отправлен: {os.path.basename(filepath)}")
    except Exception as e:
        logger.error(f"Ошибка при выгрузке всех новостей за неделю в Excel: {e}")
        try:
            if status_msg:
                await status_msg.edit_text(f"❌ Ошибка: {e}")
            else:
                await update.message.reply_text(f"❌ Ошибка при выгрузке: {e}")
        except Exception:
            await update.message.reply_text(f"❌ Ошибка при выгрузке: {e}")


async def publish_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик команды /publish - публикация сводки по отрасли (по умолчанию транспорт) в канал/группу"""
    # Проверяем права администратора (если ADMIN_IDS указаны)
    if ADMIN_IDS and update.effective_user.id not in ADMIN_IDS:
        await update.message.reply_text("❌ У вас нет прав для выполнения этой команды.")
        return
    
    if not SUMMARY_CHAT_ID:
        await update.message.reply_text(
            "❌ Не указан канал для публикации сводок.\n"
            "Добавьте SUMMARY_CHAT_ID в файл .env"
        )
        return
    
    status_msg = None
    try:
        status_msg = await safe_send_message(update, "⏳ Начинаю генерацию сводки по транспорту...")
        
        await safe_edit_message(status_msg, "📡 Сбор новостей из каналов...")
        await fetch_news_from_channels()
        
        await safe_edit_message(status_msg, "🤖 Генерация сводки через GigaChat...")
        
        # Генерируем ТОЛЬКО сводку по транспорту
        summary = news_processor.generate_daily_summary(topic="транспорт", limit_sources=5)
        
        # Получаем список источников
        sources = getattr(news_processor, '_last_sources', None)
        formatted_summary = news_processor.format_summary(
            summary, 
            topic="транспорт",
            sources=sources
        )
        
        await safe_edit_message(status_msg, f"📤 Отправка сводки в группу {SUMMARY_CHAT_ID}...")
        
        # Отправляем одно сообщение в группу
        max_length = 4000
        if len(formatted_summary) > max_length:
            # Если сводка слишком длинная, разбиваем на части
            parts = [formatted_summary[i:i+max_length] for i in range(0, len(formatted_summary), max_length)]
            for part in parts:
                await safe_send_message(context, part, chat_id=SUMMARY_CHAT_ID)
                await asyncio.sleep(0.5)
        else:
            await safe_send_message(context, formatted_summary, chat_id=SUMMARY_CHAT_ID)
        
        await safe_edit_message(status_msg, f"✅ Сводка по транспорту успешно отправлена в группу {SUMMARY_CHAT_ID}!")
        
    except Exception as e:
        logger.error(f"Ошибка при публикации сводки: {e}", exc_info=True)
        try:
            if status_msg:
                await safe_edit_message(status_msg, f"❌ Ошибка при публикации сводки: {str(e)}")
            else:
                await safe_send_message(update, f"❌ Ошибка при публикации сводки: {str(e)}")
        except:
            try:
                await update.message.reply_text(f"❌ Ошибка при публикации сводки: {str(e)}")
            except:
                logger.error("Не удалось отправить сообщение об ошибке")


async def handle_channel_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик сообщений из каналов"""
    # Логируем информацию о чате для отладки
    if update.message and update.message.chat:
        chat = update.message.chat
        logger.info(f"📥 Сообщение из чата: ID={chat.id}, Тип={chat.type}, Название={chat.title or chat.username or 'N/A'}")
    
    await news_collector.process_channel_message(update, context)


async def publish_summaries_to_chat(context: ContextTypes.DEFAULT_TYPE, chat_id: str):
    """
    Публикация сводок в указанный чат (канал/группу)
    ОТКЛЮЧЕНО - используется только ручная публикация через /publish
    """
    logger.warning("publish_summaries_to_chat отключена. Используйте команду /publish для ручной публикации.")
    pass


async def fetch_news_from_channels():
    """Автоматический сбор новостей из каналов через Client API"""
    if not CHANNEL_READER_AVAILABLE:
        logger.warning("ChannelReader недоступен. Проверьте настройки TELEGRAM_API_ID и TELEGRAM_API_HASH")
        return
    
    try:
        logger.info("🔄 Начало автоматического сбора новостей из каналов...")
        
        api_id = os.getenv("TELEGRAM_API_ID")
        api_hash = os.getenv("TELEGRAM_API_HASH")
        phone = os.getenv("TELEGRAM_PHONE")
        
        if not api_id or not api_hash:
            logger.warning("TELEGRAM_API_ID или TELEGRAM_API_HASH не указаны")
            return
        
        reader = ChannelReader(api_id, api_hash, phone)
        
        try:
            # Подключаемся через метод connect (авторизация происходит автоматически, если сессия сохранена)
            await reader.connect()
            
            # Проверяем авторизацию
            if not await reader.client.is_user_authorized():
                logger.warning("⚠️ Требуется авторизация. Запустите channel_reader.py отдельно для первой авторизации.")
                logger.warning("После авторизации сессия сохранится и будет использоваться автоматически.")
                return
            
            # Сбор новостей по всем отраслям: у каждой отрасли — свои каналы (отдельные сообщения/источники)
            total_saved = 0
            for industry, sources in INDUSTRY_SOURCES.items():
                if not sources:
                    continue
                for source_name, channel_username in sources.items():
                    if channel_username:
                        logger.info(f"[{industry}] Получение новостей из {source_name} ({channel_username})...")
                        messages = await reader.fetch_channel_messages(channel_username, limit=20, hours=24)
                        if messages:
                            reader.save_news_to_db(messages, source_name)
                            total_saved += len(messages)
                            logger.info(f"Сохранено {len(messages)} новостей из {source_name}")
                        await asyncio.sleep(1)

            # Общие каналы (если отрасль не выбрана — сводка по ним)
            for source_name, channel_username in GENERAL_SOURCES.items():
                if channel_username:
                    logger.info(f"[общие] Получение новостей из {source_name} ({channel_username})...")
                    messages = await reader.fetch_channel_messages(channel_username, limit=20, hours=24)
                    if messages:
                        reader.save_news_to_db(messages, source_name)
                        total_saved += len(messages)
                        logger.info(f"Сохранено {len(messages)} новостей из {source_name}")
                    await asyncio.sleep(1)
            
            logger.info(f"✅ Сбор новостей завершен. Всего сохранено: {total_saved}")
            
        finally:
            await reader.disconnect()
            
    except Exception as e:
        logger.error(f"Ошибка при сборе новостей: {e}")
        import traceback
        logger.error(traceback.format_exc())


async def scheduled_summary(context: ContextTypes.DEFAULT_TYPE):
    """Планируемая задача для генерации ежедневных сводок (ОТКЛЮЧЕНО)"""
    # Автоматическая публикация отключена - используется только ручная команда /publish
    logger.info("Автоматическая публикация отключена. Используйте команду /publish для ручной публикации.")
    pass


def main():
    """Основная функция запуска бота"""
    if not TELEGRAM_BOT_TOKEN:
        logger.error("TELEGRAM_BOT_TOKEN не установлен в переменных окружения!")
        return
    
    # Создаем приложение с поддержкой JobQueue и увеличенными таймаутами
    application = (
        Application.builder()
        .token(TELEGRAM_BOT_TOKEN)
        .read_timeout(30)  # Увеличиваем таймаут чтения до 30 секунд
        .write_timeout(30)  # Увеличиваем таймаут записи до 30 секунд
        .connect_timeout(30)  # Увеличиваем таймаут подключения до 30 секунд
        .build()
    )
    
    # Регистрируем обработчики команд
    application.add_handler(CommandHandler("start", start_command))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CommandHandler("summary", summary_command))
    application.add_handler(CommandHandler("summary_topic", summary_topic_command))
    application.add_handler(
        MessageHandler(filters.Regex(r"^\d+$"), handle_infopovod_choice)
    )
    application.add_handler(
        MessageHandler(
            filters.TEXT & ~filters.COMMAND & filters.Regex(r"https?://(?:t\.me|telegram\.me)/"),
            handle_infopovod_by_link,
        )
    )
    application.add_handler(
        MessageHandler(filters.TEXT & ~filters.COMMAND, handle_custom_news_for_infopovod)
    )
    application.add_handler(CommandHandler("topics", topics_command))
    application.add_handler(CommandHandler("stats", stats_command))
    application.add_handler(CommandHandler("channels", channels_command))
    application.add_handler(CommandHandler("publish", publish_command))
    application.add_handler(CommandHandler("get_chat_id", get_chat_id_command))
    application.add_handler(CommandHandler("fetch_news", fetch_news_command))
    application.add_handler(CommandHandler("export_relevant", export_relevant_command))
    application.add_handler(CommandHandler("export_relevant_week", export_relevant_week_command))
    application.add_handler(CommandHandler("export_all", export_all_command))
    application.add_handler(CommandHandler("export_all_week", export_all_week_command))

    # Обработчик сообщений из каналов
    application.add_handler(
        MessageHandler(
            filters.ChatType.CHANNEL | filters.ChatType.SUPERGROUP,
            handle_channel_message
        )
    )
    
    # Глобальный обработчик ошибок
    async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Обработчик необработанных ошибок"""
        error = context.error
        
        # Если это ошибка TimedOut, логируем но не отправляем сообщение пользователю
        if isinstance(error, TimedOut):
            logger.warning("Timeout при запросе к Telegram API - ошибка проигнорирована")
            return
        
        # Если это ошибка Conflict (несколько экземпляров бота), логируем и завершаем
        if isinstance(error, Conflict):
            logger.error("Конфликт: запущено несколько экземпляров бота одновременно. Остановите другие экземпляры.")
            return
        
        # Для других ошибок логируем и пытаемся отправить сообщение пользователю
        logger.error(f"Необработанная ошибка: {error}", exc_info=error)
        
        if update and isinstance(update, Update) and update.effective_message:
            try:
                await safe_send_message(
                    update,
                    f"❌ Произошла ошибка: {str(error)[:200]}"
                )
            except:
                logger.error("Не удалось отправить сообщение об ошибке пользователю")
    
    application.add_error_handler(error_handler)
    
    # Планировщик отключен - публикация только вручную через команду /publish
    logger.info("Автоматическая публикация отключена. Используйте /publish для ручной публикации сводки.")
    
    # Запускаем бота
    logger.info("Бот запущен и готов к работе!")
    application.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()