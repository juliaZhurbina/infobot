"""
Модуль для сбора новостей из Telegram каналов
"""
import logging
import os
import re
from typing import List, Dict, Optional
from datetime import datetime, timedelta
from telegram import Update
from telegram.ext import ContextTypes
from telegram.constants import ChatType
import sqlite3
from config import MONITORED_CHANNELS, DATABASE_URL

logger = logging.getLogger(__name__)


class NewsCollector:
    """Класс для сбора новостей из Telegram каналов"""
    
    def __init__(self):
        self.monitored_channels = MONITORED_CHANNELS
        # Обрабатываем путь к базе данных
        if DATABASE_URL.startswith("sqlite:///"):
            self.db_path = DATABASE_URL.replace("sqlite:///", "")
        else:
            self.db_path = DATABASE_URL
        # Делаем путь абсолютным
        if not os.path.isabs(self.db_path):
            self.db_path = os.path.join(os.path.dirname(__file__), self.db_path)
        self._init_database()
    
    def _init_database(self):
        """Инициализация базы данных для хранения новостей"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS news (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                message_id INTEGER NOT NULL,
                chat_id INTEGER NOT NULL,
                chat_username TEXT,
                source_name TEXT,
                title TEXT,
                text TEXT,
                date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                topics TEXT,
                processed BOOLEAN DEFAULT 0,
                UNIQUE(message_id, chat_id)
            )
        """)
        
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_date ON news(date)
        """)
        
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_processed ON news(processed)
        """)
        
        conn.commit()
        conn.close()
        logger.info("База данных инициализирована")
    
    async def process_channel_message(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """
        Обработка сообщения из канала
        
        Args:
            update: Обновление от Telegram
            context: Контекст бота
        """
        if not update.message or not update.message.chat:
            return
        
        chat = update.message.chat
        
        # Логируем информацию о чате для отладки
        logger.info(f"Получено сообщение из чата: ID={chat.id}, Тип={chat.type}, Название={chat.title or chat.username or 'N/A'}")
        
        # Проверяем, что это канал или супергруппа
        if chat.type not in [ChatType.CHANNEL, ChatType.SUPERGROUP]:
            return
        
        # Проверяем, отслеживаем ли мы этот канал
        chat_username = chat.username
        if not chat_username:
            # Если у канала нет username, проверяем по chat_id
            chat_id = str(chat.id)
            if not any(chat_id in str(channel) for channel in self.monitored_channels.values()):
                return
        else:
            # Проверяем по username
            if f"@{chat_username}" not in self.monitored_channels.values():
                return
        
        # Определяем название источника
        source_name = None
        for name, username in self.monitored_channels.items():
            if f"@{chat_username}" == username:
                source_name = name
                break
        
        if not source_name:
            return
        
        # Извлекаем данные сообщения
        message = update.message
        message_id = message.message_id
        chat_id = chat.id
        
        # Получаем текст сообщения
        text = message.text or message.caption or ""
        
        # Получаем заголовок (если есть)
        title = None
        if message.text:
            # Первая строка может быть заголовком
            lines = message.text.split("\n")
            if len(lines) > 1:
                title = lines[0][:200]  # Ограничиваем длину заголовка
        
        # Сохраняем новость в базу данных
        self._save_news(
            message_id=message_id,
            chat_id=chat_id,
            chat_username=chat_username,
            source_name=source_name,
            title=title,
            text=text,
            date=message.date,
        )
        
        logger.info(f"Новость сохранена: {source_name} - {message_id}")
    
    def _save_news(
        self,
        message_id: int,
        chat_id: int,
        chat_username: Optional[str],
        source_name: str,
        title: Optional[str],
        text: str,
        date: Optional[datetime] = None,
    ):
        """Сохранение новости в базу данных"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        try:
            date_val = date or datetime.now()
            if isinstance(date_val, datetime) and date_val.tzinfo is not None:
                date_val = date_val.astimezone().replace(tzinfo=None)
            cursor.execute("""
                INSERT OR IGNORE INTO news 
                (message_id, chat_id, chat_username, source_name, title, text, date)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """, (message_id, chat_id, chat_username, source_name, title, text, date_val))
            
            conn.commit()
        except Exception as e:
            logger.error(f"Ошибка при сохранении новости: {e}")
        finally:
            conn.close()
    
    def get_recent_news(self, hours: int = 24, limit: int = 100) -> List[Dict]:
        """
        Получение свежих новостей за указанный период
        
        Args:
            hours: Количество часов для выборки
            limit: Максимальное количество новостей
        
        Returns:
            Список новостей
        """
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cutoff_time = datetime.now() - timedelta(hours=hours)
        
        cursor.execute("""
            SELECT id, message_id, chat_id, chat_username, source_name, title, text, date, topics
            FROM news
            WHERE date >= ? AND text != ''
            ORDER BY date DESC
            LIMIT ?
        """, (cutoff_time, limit))
        
        rows = cursor.fetchall()
        conn.close()
        
        logger.info(f"Найдено свежих новостей за последние {hours} часов: {len(rows)}")
        
        news_items = []
        for row in rows:
            news_items.append({
                "id": row[0],
                "message_id": row[1],
                "chat_id": row[2],
                "chat_username": row[3],
                "source_name": row[4],
                "title": row[5] or "Без заголовка",
                "text": row[6],
                "date": row[7],
                "topics": row[8] if row[8] else ""
            })
        
        return news_items
    
    def get_all_news_count(self) -> int:
        """Получить общее количество новостей в базе"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM news")
        count = cursor.fetchone()[0]
        conn.close()
        return count
    
    def get_news_by_source(self, source_names: List[str], hours: int = 168) -> List[Dict]:
        """
        Получить новости из указанных источников
        
        Args:
            source_names: Список названий источников
            hours: За какой период получать новости (по умолчанию 168 часов = 7 дней)
        
        Returns:
            Список новостей
        """
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cutoff_time = datetime.now() - timedelta(hours=hours)
        placeholders = ",".join(["?"] * len(source_names))
        
        query = f"""
            SELECT id, message_id, chat_id, chat_username, source_name, title, text, date, topics
            FROM news
            WHERE date >= ? AND text != '' 
            AND source_name IN ({placeholders})
            ORDER BY date DESC
            LIMIT 50
        """
        params = (cutoff_time,) + tuple(source_names)
        
        cursor.execute(query, params)
        rows = cursor.fetchall()
        conn.close()
        
        logger.info(f"Найдено новостей из источников {source_names} за последние {hours}ч: {len(rows)}")
        
        news_items = []
        for row in rows:
            news_items.append({
                "id": row[0],
                "message_id": row[1],
                "chat_id": row[2],
                "chat_username": row[3],
                "source_name": row[4],
                "title": row[5] or "Без заголовка",
                "text": row[6],
                "date": row[7],
                "topics": row[8] if row[8] else ""
            })
        
        return news_items

    def get_news_by_telegram_link(self, link: str) -> Optional[Dict]:
        """
        Находит новость в БД по ссылке на сообщение в Telegram.
        Поддерживает форматы: t.me/username/msg_id, t.me/c/chat_internal_id/msg_id.

        Returns:
            Словарь новости (как в get_news_by_source) или None, если не найдено.
        """
        link = (link or "").strip()
        if not link:
            return None
        m_public = re.match(r"https?://(?:t\.me|telegram\.me)/([a-zA-Z0-9_]+)/(\d+)/?", link)
        m_private = re.match(r"https?://(?:t\.me|telegram\.me)/c/(\d+)/(\d+)/?", link)
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        try:
            if m_public:
                username, msg_id = m_public.group(1), int(m_public.group(2))
                cursor.execute(
                    """
                    SELECT id, message_id, chat_id, chat_username, source_name, title, text, date, topics
                    FROM news
                    WHERE message_id = ? AND (chat_username = ? OR chat_username = ?)
                    LIMIT 1
                    """,
                    (msg_id, username, f"@{username}"),
                )
            elif m_private:
                internal_id, msg_id = int(m_private.group(1)), int(m_private.group(2))
                chat_id = -(10**11 + internal_id)
                cursor.execute(
                    """
                    SELECT id, message_id, chat_id, chat_username, source_name, title, text, date, topics
                    FROM news
                    WHERE message_id = ? AND chat_id = ?
                    LIMIT 1
                    """,
                    (msg_id, chat_id),
                )
            else:
                return None
            row = cursor.fetchone()
            if not row:
                return None
            return {
                "id": row[0],
                "message_id": row[1],
                "chat_id": row[2],
                "chat_username": row[3],
                "source_name": row[4],
                "title": row[5] or "Без заголовка",
                "text": row[6],
                "date": row[7],
                "topics": row[8] if row[8] else "",
            }
        finally:
            conn.close()

    def get_news_by_topic(self, topic: str, hours: int = 24, source_names: Optional[List[str]] = None, 
                         skip_topic_search: bool = False) -> List[Dict]:
        """
        Получение новостей по определенной теме
        
        Args:
            topic: Тема для фильтрации
            hours: Количество часов для выборки
            source_names: Список названий источников для фильтрации (опционально)
            skip_topic_search: Если True, не ищет по ключевому слову темы, только по источникам
        
        Returns:
            Список новостей по теме
        """
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cutoff_time = datetime.now() - timedelta(hours=hours)
        
        # Если указаны конкретные источники
        if source_names:
            placeholders = ",".join(["?"] * len(source_names))
            
            # Если skip_topic_search=True, берем ВСЕ новости из этих источников
            if skip_topic_search:
                query = f"""
                    SELECT id, message_id, chat_id, chat_username, source_name, title, text, date, topics
                    FROM news
                    WHERE date >= ? AND text != '' 
                    AND source_name IN ({placeholders})
                    ORDER BY date DESC
                    LIMIT 50
                """
                params = (cutoff_time,) + tuple(source_names)
            else:
                # Ищем по источникам И по ключевому слову темы
                query = f"""
                    SELECT id, message_id, chat_id, chat_username, source_name, title, text, date, topics
                    FROM news
                    WHERE date >= ? AND text != '' 
                    AND source_name IN ({placeholders})
                    AND (topics LIKE ? OR text LIKE ? OR title LIKE ?)
                    ORDER BY date DESC
                    LIMIT 50
                """
                params = (cutoff_time,) + tuple(source_names) + (f"%{topic}%", f"%{topic}%", f"%{topic}%")
        else:
            # Обычный поиск по ключевому слову
            query = """
                SELECT id, message_id, chat_id, chat_username, source_name, title, text, date, topics
                FROM news
                WHERE date >= ? AND text != '' AND (topics LIKE ? OR text LIKE ? OR title LIKE ?)
                ORDER BY date DESC
                LIMIT 50
            """
            params = (cutoff_time, f"%{topic}%", f"%{topic}%", f"%{topic}%")
        
        cursor.execute(query, params)
        
        rows = cursor.fetchall()
        conn.close()
        
        logger.info(f"Найдено новостей по теме '{topic}': {len(rows)}")
        if source_names:
            logger.info(f"Источники: {source_names}")
        
        news_items = []
        for row in rows:
            news_items.append({
                "id": row[0],
                "message_id": row[1],
                "chat_id": row[2],
                "chat_username": row[3],
                "source_name": row[4],
                "title": row[5] or "Без заголовка",
                "text": row[6],
                "date": row[7],
                "topics": row[8] if row[8] else ""
            })
        
        return news_items
    
    def mark_as_processed(self, news_ids: List[int]):
        """Отметка новостей как обработанных"""
        if not news_ids:
            return
        
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        placeholders = ",".join(["?"] * len(news_ids))
        cursor.execute(f"""
            UPDATE news
            SET processed = 1
            WHERE id IN ({placeholders})
        """, news_ids)
        
        conn.commit()
        conn.close()
    
    def get_statistics(self) -> Dict:
        """Получение статистики по новостям"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        # Общее количество новостей
        cursor.execute("SELECT COUNT(*) FROM news")
        total = cursor.fetchone()[0]
        
        # Новости за последние 24 часа
        cutoff_time = datetime.now() - timedelta(hours=24)
        cursor.execute("SELECT COUNT(*) FROM news WHERE date >= ?", (cutoff_time,))
        last_24h = cursor.fetchone()[0]
        
        # Новости по источникам
        cursor.execute("""
            SELECT source_name, COUNT(*) as count
            FROM news
            WHERE date >= ?
            GROUP BY source_name
            ORDER BY count DESC
            LIMIT 10
        """, (cutoff_time,))
        by_source = {row[0]: row[1] for row in cursor.fetchall()}
        
        conn.close()
        
        return {
            "total": total,
            "last_24h": last_24h,
            "by_source": by_source
        }