"""
Модуль для работы с GigaChat API
"""
import os
import re
import requests
import base64
import json
from typing import List, Dict, Optional
import logging
import uuid
import urllib3
from config import (
    GIGACHAT_AUTH_KEY, 
    GIGACHAT_CLIENT_ID, 
    GIGACHAT_CLIENT_SECRET, 
    GIGACHAT_SCOPE,
    GIGACHAT_API_AUTH_URL,
    GIGACHAT_API_CHAT_URL,
    GIGACHAT_MODEL,
)

# Отключаем предупреждения SSL для dev окружения
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

logger = logging.getLogger(__name__)

# Путь к справочнику банковских продуктов (статика с сайта банка)
BANKING_REFERENCE_PATH = os.path.join(os.path.dirname(__file__), "banking_products_reference.txt")


def _load_infopovod_examples() -> str:
    """Загружает примеры инфоповодов из файлов «пример инфоповода*.txt» в папке проекта."""
    import glob
    base_dir = os.path.dirname(__file__)
    pattern = os.path.join(base_dir, "*пример*инфоповод*.txt")
    files = sorted(glob.glob(pattern))
    if not files:
        return ""
    parts = []
    for path in files:
        try:
            with open(path, "r", encoding="utf-8") as f:
                content = f.read().strip()
                if content:
                    parts.append(content)
        except Exception as e:
            logger.warning(f"Не удалось прочитать пример инфоповода {path}: {e}")
    return "\n\n---\n\n".join(parts) if parts else ""


def _load_banking_reference() -> str:
    """Загружает справочник банковских продуктов из файла. Строки с # и пустые пропускаются."""
    if not os.path.isfile(BANKING_REFERENCE_PATH):
        return ""
    try:
        with open(BANKING_REFERENCE_PATH, "r", encoding="utf-8") as f:
            lines = [line.strip() for line in f if line.strip() and not line.strip().startswith("#")]
        return "\n".join(lines).strip()
    except Exception as e:
        logger.warning(f"Не удалось загрузить справочник банковских продуктов: {e}")
        return ""


class GigaChatClient:
    """Клиент для работы с GigaChat API"""
    
    def __init__(self):
        self.auth_key = GIGACHAT_AUTH_KEY
        self.client_id = GIGACHAT_CLIENT_ID
        self.client_secret = GIGACHAT_CLIENT_SECRET
        self.scope = GIGACHAT_SCOPE
        self.access_token = None
        self.token_url = GIGACHAT_API_AUTH_URL
        self.api_url = GIGACHAT_API_CHAT_URL
    
    def _get_access_token(self) -> str:
        """Получение access token для GigaChat API"""
        if self.access_token:
            return self.access_token
        
        # Используем AUTH_KEY если он предоставлен, иначе используем client_id и client_secret
        if self.auth_key:
            encoded_credentials = self.auth_key
        elif self.client_id and self.client_secret:
            # Кодирование credentials в base64
            credentials = f"{self.client_id}:{self.client_secret}"
            encoded_credentials = base64.b64encode(credentials.encode()).decode()
        else:
            raise ValueError("Не указаны учетные данные GigaChat (AUTH_KEY или CLIENT_ID/CLIENT_SECRET)")
        
        headers = {
            "Authorization": f"Basic {encoded_credentials}",
            "RqUID": str(uuid.uuid4()),
            "Content-Type": "application/x-www-form-urlencoded"
        }
        
        data = {
            "scope": self.scope
        }
        
        try:
            response = requests.post(
                self.token_url,
                headers=headers,
                data=data,
                verify=False,  # Отключаем проверку SSL для dev окружения
                timeout=30
            )
            response.raise_for_status()
            
            token_data = response.json()
            self.access_token = token_data.get("access_token")
            
            if not self.access_token:
                error_msg = token_data.get("error_description", "Неизвестная ошибка")
                raise ValueError(f"Не удалось получить access token: {error_msg}")
            
            logger.info("Access token получен успешно")
            return self.access_token
            
        except requests.exceptions.RequestException as e:
            logger.error(f"Ошибка сети при получении access token: {e}")
            raise
        except Exception as e:
            logger.error(f"Ошибка при получении access token: {e}")
            raise
    
    def _ensure_token(self):
        """Проверка и обновление токена при необходимости"""
        if not self.access_token:
            self._get_access_token()
    
    def generate_summary(self, news_items: List[Dict[str, str]], topic: Optional[str] = None) -> str:
        """
        Генерация краткой сводки новостей по определенной теме
        
        Args:
            news_items: Список новостей в формате [{"title": "...", "text": "...", "source": "..."}, ...]
            topic: Тема для фильтрации (опционально)
        
        Returns:
            Краткая сводка новостей
        """
        self._ensure_token()
        
        # Формируем промпт для GigaChat
        news_text = "\n\n".join([
            f"Источник: {item.get('source', 'Неизвестно')}\n"
            f"Заголовок: {item.get('title', 'Без заголовка')}\n"
            f"Текст: {item.get('text', '')}"
            for item in news_items[:10]  # Ограничиваем количество новостей до 10
        ])
        
        # Подсчитываем источники для информации
        sources_list = list(set([item.get('source', 'Неизвестно') for item in news_items[:10]]))
        
        # Логируем информацию об источниках для отладки
        logger.info(f"Передано в GigaChat новостей: {len(news_items[:10])}, уникальных источников: {len(sources_list)}")
        logger.info(f"Список источников: {sources_list}")
        
        # Подсчитываем количество новостей по каждому источнику
        source_counts = {}
        for item in news_items[:10]:
            source = item.get('source', 'Неизвестно')
            source_counts[source] = source_counts.get(source, 0) + 1
        logger.info(f"Распределение новостей по источникам: {source_counts}")
        
        topic_prompt = f" по теме '{topic}'" if topic else ""
        banking_ref = _load_banking_reference()
        banking_ref_block = ""
        if banking_ref:
            banking_ref_block = f"""
СПРАВОЧНИК БАНКОВСКИХ ПРОДУКТОВ (в блоке «Банковские решения» выбирай только из этого списка, не придумывай другие):
---
{banking_ref}
---

"""
        examples_block = ""
        if len(news_items) == 1:
            examples = _load_infopovod_examples()
            if examples:
                examples_block = f"""
ПРИМЕРЫ ИНФОПОВОДОВ (ориентируйся на этот формат и стиль: заголовок/факты/источник, затем блок «ИНФОПОВОД» — формулировка для звонка клиенту «[Имя клиента], ...»):
---
{examples}
---

"""
        
        prompt = f"""Ты — профессиональный аналитик и копирайтер, который создаёт краткие и понятные сводки новостей для внутреннего Telegram-канала банка.

КОНТЕКСТ АУДИТОРИИ:
Твои читатели — сотрудники банка, которые работают с корпоративными клиентами сегмента малый и микро-бизнес в России (менеджеры по работе с корпоративными клиентами, специалисты по корпоративному бизнесу). Они ищут инфоповоды для контакта с клиентами, обсуждения их потребностей и предложения банковских продуктов и услуг.

Твоя задача — проанализировать следующие новости из официальных источников и создать яркую, структурированную сводку{topic_prompt}, которая станет ИНФОПОВОДОМ для:
- Назначения встречи с корпоративным клиентом 
- Совершения звонка клиенту
- Обсуждения с клиентом новых возможностей и потребностей
- Предложения банковских продуктов (кредиты, финансирование, РКО, зарплатные проекты, эквайринг, гарантии, лизинг и т.д.)

Новости:
{news_text}
{banking_ref_block}
{examples_block}
Требования к сводке:

СТИЛЬ:
* Простой и понятный язык, без канцелярита и сложных терминов
* Дружелюбный, энергичный, но профессиональный тон
* Легко читается, сразу цепляет внимание
* Используй 3-5 уместных эмодзи для визуального оформления
* Акцент на действиях и возможностях для банковского бизнеса

СТРУКТУРА (соблюдай порядок блоков):

1. ЗАГОЛОВОК + ТЕКСТ НОВОСТИ + ИСТОЧНИК
   * Заголовок — суть новости емко (1 предложение)
   * Текст новости — главная мысль, ключевые факты и цифры из новости
   * Обязательно укажи источник в формате: [Источник: Название источника]

2. ТЕКСТ ИНФОПОВОДА (чем полезна бизнесу)
   * Обязательно укажи, чем эта новость может быть полезна бизнесу клиента
   * Вызовы, возможности, выгоды для клиентов сегмента малый и микро-бизнес
   * Какие отрасли или типы компаний могут быть заинтересованы

3. БАНКОВСКИЕ РЕШЕНИЯ (одно самое реальное, почему подходит)
   * Подбери ровно одно, самое реальное и уместное банковское решение под этот инфоповод. Если выше дан СПРАВОЧНИК — выбирай только из него.
   * Кратко объясни, почему именно это решение подходит (кредит, РКО, эквайринг, гарантия, лизинг, зарплатный проект и т.д.).



ВАЖНО: В сводке обязательно указывай источник для каждой упомянутой новости в формате [Источник: Название источника]. Обязательно указывай, чем новость полезна бизнесу, и одно самое реальное банковское решение (почему подходит).

ТРЕБОВАНИЯ:
* Длина: 300-350 слов (все блоки структуры должны быть заполнены)
* Пиши на русском языке
* Соблюдай порядок блоков: заголовок+новость+источник → инфоповод (польза для бизнеса) → банковские решения
* Обязательно включи блок «чем полезна бизнесу» и блок «банковские решения» — одно самое реальное решение
* Учитывай сегмент малый и микро-бизнес

ВАЖНО — ИЗБЕГАЙ СЛЕДУЮЩИХ ТЕМ:
* Религиозные вопросы и темы
* Политические дискуссии и споры
* Военные действия и конфликты
* Спорные политические заявления
* Религиозные обряды и практики
* Информация рекламного характера сторонних компаний (конкретные организации, тарифы)
* Судебные разбирательства
* Новости о конкретных персоналиях, должностных лицах

Если в новостях встречаются такие темы, либо пропусти их, либо представь информацию максимально нейтрально и фактологично, без оценок и интерпретаций. Фокусируйся на деловых, экономических, социальных и культурных аспектах, которые могут быть интересны корпоративным клиентам банка.

ЦЕЛЬ СВОДКИ:
Сводка должна помочь менеджеру по работе с корпоративными клиентами — совершить звонок, наладить контакт, назначить встречу, обсудить с клиентом новые возможности. Выделяй новости, которые:
- Создают возможности для предложения банковских продуктов и услуг
- Требуют быстрой реакции или обсуждения с клиентами
- Могут быть интересны корпоративным клиентам банка
- Содержат важные изменения или обновления, которые стоит обсудить с клиентами
- Имеют конкретные сроки или дедлайны, требующие действий
- Открывают новые возможности для развития бизнеса клиентов (и соответственно, для банковских продуктов)
- Связаны с государственными программами поддержки, субсидиями, льготами (которые могут требовать банковского сопровождения)
- Касаются изменений в законодательстве, которые влияют на бизнес клиентов
- Относятся к инфраструктурным проектам, инвестициям, развитию отраслей

Используй формулировки, которые подталкивают к действию: "стоит обсудить с клиентами", "можно предложить", "важно учесть при работе с клиентами", "отличный повод для звонка", "срочно нужно связаться", "открывает возможность для", "клиенты могут быть заинтересованы в", "повод предложить".
Используй краткие, но емкие фразы. Избегай повторений и сложных оборотов. 

Создай сводку:"""
        
        headers = {
            "Authorization": f"Bearer {self.access_token}",
            "Content-Type": "application/json"
        }
        
        payload = {
            "model": GIGACHAT_MODEL,
            "messages": [
                {
                    "role": "system",
                    "content": "Ты профессиональный аналитик и копирайтер, который создает сводки новостей для банка. Используй факты из предоставленных новостей и структурируй их согласно инструкциям."
                },
                {
                    "role": "user",
                    "content": prompt
                }
            ],
            "temperature": 0.7,
            "max_tokens": 2000
        }
        
        try:
            response = requests.post(
                self.api_url,
                headers=headers,
                json=payload,
                verify=False,
                timeout=120  # Увеличиваем таймаут для генерации сводок
            )
            response.raise_for_status()
            
            result = response.json()
            summary = result.get("choices", [{}])[0].get("message", {}).get("content", "")
            
            if not summary:
                error_info = result.get("error", {})
                error_msg = error_info.get("message", "Пустой ответ от GigaChat API")
                raise ValueError(f"Ошибка GigaChat API: {error_msg}")
            
            # Проверяем, не отказалась ли модель генерировать контент
            if "не обладают собственным мнением" in summary.lower() or "ограничены" in summary.lower():
                logger.warning("GigaChat отказался генерировать контент. Пробуем упрощенный промпт...")
                # Пробуем более простой промпт без упоминания банковских продуктов
                simple_prompt = f"""Создай краткую сводку{topic_prompt} на основе новостей.

НОВОСТИ:
{news_text}

Структура:
1. Заголовок + текст новости + источник
2. Текст инфоповода (чем полезна бизнесу)
3. Банковские решения (одно самое реальное, почему подходит)

Требования: 300-350 слов, русский язык, 3-5 эмодзи, только факты из новостей.

Создай сводку:"""
                
                payload_simple = {
                    "model": GIGACHAT_MODEL,
                    "messages": [
                        {
                            "role": "system",
                            "content": "Ты помощник, который создает информационные сводки из новостей. Используй только факты."
                        },
                        {
                            "role": "user",
                            "content": simple_prompt
                        }
                    ],
                    "temperature": 0.7,
                    "max_tokens": 2000
                }
                
                response_simple = requests.post(
                    self.api_url,
                    headers=headers,
                    json=payload_simple,
                    verify=False,
                    timeout=120
                )
                response_simple.raise_for_status()
                result_simple = response_simple.json()
                summary = result_simple.get("choices", [{}])[0].get("message", {}).get("content", "")
                
                if not summary or "не обладают собственным мнением" in summary.lower():
                    logger.error("GigaChat отказался генерировать контент даже с упрощенным промптом")
                    raise ValueError("GigaChat отказался генерировать контент. Возможно, новости содержат чувствительные темы.")
            
            logger.info(f"Сводка успешно сгенерирована, длина: {len(summary)} символов")
            return summary
            
        except requests.exceptions.Timeout:
            logger.error("Таймаут при запросе к GigaChat API")
            raise Exception("Превышено время ожидания ответа от GigaChat API. Попробуйте позже.")
        except requests.exceptions.RequestException as e:
            logger.error(f"Ошибка сети при генерации сводки: {e}")
            raise Exception(f"Ошибка подключения к GigaChat API: {str(e)}")
        except Exception as e:
            logger.error(f"Ошибка при генерации сводки: {e}")
            raise
    
    def generate_thesis_summary(self, news_items: List[Dict[str, str]], topic: Optional[str] = None) -> str:
        """
        Генерация краткой тезисной сводки — нумерованный список новостей (заголовок/тезис + источник).
        Используется для выбора пользователем новости, по которой потом делается полный инфоповод.
        
        Args:
            news_items: Список новостей [{"title": "...", "text": "...", "source": "..."}, ...]
            topic: Тема (опционально)
        
        Returns:
            Текст вида "1. Тезис. [Источник: X]\\n2. ..."
        """
        self._ensure_token()
        
        news_text = "\n\n".join([
            f"Источник: {item.get('source', 'Неизвестно')}\n"
            f"Заголовок: {item.get('title', 'Без заголовка')}\n"
            f"Текст: {item.get('text', '')}"
            for item in news_items[:15]
        ])
        
        topic_prompt = f" по теме '{topic}'" if topic else ""
        
        prompt = f"""Ты — редактор новостной сводки для банка. По списку новостей составь КРАТКУЮ тезисную сводку.

Новости:
{news_text}

Требования:
* Выведи каждую новость одной строкой в формате: НОМЕР. Краткий тезис (1–2 предложения). [Источник: Название]
* Нумерация строго с 1 по N (по количеству новостей выше).
* Без лишних вводных фраз, без эмодзи — только нумерованный список.
* Тезис — суть новости для менеджера банка (что произошло, почему важно).
* Русский язык.

Пример формата:
1. Рекордное число субъектов МСП в России; рост за полгода 500 тыс. [Источник: Росстат]
2. ...

Создай тезисную сводку{topic_prompt}:"""
        
        headers = {
            "Authorization": f"Bearer {self.access_token}",
            "Content-Type": "application/json"
        }
        payload = {
            "model": GIGACHAT_MODEL,
            "messages": [
                {"role": "system", "content": "Ты составляешь краткие тезисные списки новостей. Только нумерованный список, без вступления."},
                {"role": "user", "content": prompt}
            ],
            "temperature": 0.4,
            "max_tokens": 1500
        }
        
        try:
            response = requests.post(
                self.api_url,
                headers=headers,
                json=payload,
                verify=False,
                timeout=90
            )
            response.raise_for_status()
            result = response.json()
            summary = result.get("choices", [{}])[0].get("message", {}).get("content", "")
            if not summary:
                raise ValueError("Пустой ответ от GigaChat API")
            logger.info(f"Тезисная сводка сгенерирована, {len(summary)} символов")
            return summary.strip()
        except Exception as e:
            logger.error(f"Ошибка при генерации тезисной сводки: {e}")
            raise
    
    def generate_infopovod(self, news_item: Dict[str, str], topic: Optional[str] = None) -> str:
        """
        Генерация полного инфоповода по одной новости (структура: заголовок+источник, польза для бизнеса, банковские решения, предложение/мостик).
        
        Args:
            news_item: Одна новость {"title": "...", "text": "...", "source": "..."}
            topic: Тема (опционально)
        
        Returns:
            Текст полного инфоповода по структуре.
        """
        return self.generate_summary([news_item], topic=topic)
    
    def filter_relevant_news(self, news_items: List[Dict], batch_size: int = 10) -> List[Dict]:
        """
        Оставляет только новости, релевантные для банковского сотрудника, работающего с корпоративными клиентами малого бизнеса в России.
        Запрос к GigaChat пачками; ответ «Да/Нет» по каждой новости.
        
        Args:
            news_items: Список новостей (dict с ключами title, text и source или source_name)
            batch_size: Сколько новостей отправлять в одном запросе (по умолчанию 10)
        
        Returns:
            Подсписок news_items, для которых ответ «Да».
        """
        if not news_items:
            return []
        
        self._ensure_token()
        relevant: List[Dict] = []
        for start in range(0, len(news_items), batch_size):
            batch = news_items[start : start + batch_size]
            numbered = []
            for i, item in enumerate(batch, 1):
                title = item.get("title", "") or item.get("text", "")[:80]
                text = (item.get("text", "") or "")[:500]
                source = item.get("source") or item.get("source_name", "")
                numbered.append(f"{i}. [Источник: {source}]\nЗаголовок: {title}\nТекст: {text}")
            block = "\n\n".join(numbered)
            
            prompt = f"""Ниже список новостей (нумерованный). По каждой определи: релевантна ли она для банковского сотрудника, работающего с корпоративными клиентами малого бизнеса в России?

Релевантны (считай Да):
— Бизнес, финансы компаний, кредиты, РКО, гарантии, господдержка МСП; отраслевая специфика (розница, производство, строительство, транспорт и логистика, рестораны, отели, опт, e-commerce, услуги).
— Маркировка («Честный знак»), вебинары и разъяснения по маркировке для бизнеса.
— Налоги и ФНС: налоговый контроль, разъяснения для плательщиков (ЕСХН, УСН и т.д.), онлайн-кассы, штрафы и регуляторика для предпринимателей; самозанятость и режимы для МСП.
— Регуляторика для бизнеса: гособоронзаказ, реестры (например транспортно-экспедиционная деятельность), ЭТН/ЭТрН, цифровые платформы (ГосЛог и аналоги).
— Отраслевые события: конгрессы, вебинары для предпринимателей (рестораны, отели, ритейл, производство), ТПП РФ, ОПОРА РОССИИ; сертификаты происхождения товаров, внешняя торговля.
— Ритейл и e-commerce: оборот интернет-магазинов, доставка, СТМ, ритейлеры; строительство (производительность, маржа, подрядчики); девелопмент и недвижимость в контексте бизнеса.

Нерелевантны (считай Нет): развлекательные, спорт, криминал, политика, культура, происшествия и любые новости без явной связи с бизнесом, финансами, МСП или отраслями. При сомнении — Нет.

Новости:
{block}

Ответь строго по одной строке на каждую новость в формате: N. Да или N. Нет (N — номер новости 1, 2, 3...). Без вступления и пояснений."""
            
            headers = {
                "Authorization": f"Bearer {self.access_token}",
                "Content-Type": "application/json"
            }
            payload = {
                "model": GIGACHAT_MODEL,
                "messages": [
                    {"role": "system", "content": "Ты классификатор релевантности новостей для корпоративного банкинга (МСП). Релевантны: отраслевые новости (розница, производство, строительство, транспорт, рестораны, отели, маркировка, налоги/ФНС, регуляторика для бизнеса, ТПП/ОПОРА, ритейл и e-commerce). Нерелевантны: развлечения, спорт, криминал, политика, культура, происшествия. Отвечай только строками N. Да или N. Нет. При сомнении — Нет."},
                    {"role": "user", "content": prompt}
                ],
                "temperature": 0.2,
                "max_tokens": 500
            }
            try:
                response = requests.post(
                    self.api_url,
                    headers=headers,
                    json=payload,
                    verify=False,
                    timeout=60
                )
                response.raise_for_status()
                result = response.json()
                content = (result.get("choices", [{}])[0].get("message", {}).get("content", "") or "").strip()
                for line in content.splitlines():
                    line = line.strip()
                    m = re.match(r"^\s*(\d+)\.\s*(Да|Нет)\s*$", line, re.IGNORECASE)
                    if m:
                        idx = int(m.group(1)) - 1
                        if 0 <= idx < len(batch) and m.group(2).lower() == "да":
                            relevant.append(batch[idx])
                added = sum(1 for line in content.splitlines() if re.search(r"^\s*\d+\.\s*Да\s*$", line.strip(), re.I))
                logger.info(f"Фильтр релевантности: пачка {start // batch_size + 1}, оставлено {added} из {len(batch)}")
            except Exception as e:
                logger.warning(f"Ошибка фильтра релевантности для пачки: {e}. Оставляем все новости пачки.")
                relevant.extend(batch)
        
        logger.info(f"Фильтр релевантности: всего {len(news_items)} → {len(relevant)} релевантных")
        return relevant
    
    def categorize_news(self, news_text: str) -> List[str]:
        """
        Определение тем новости с помощью GigaChat
        
        Args:
            news_text: Текст новости
        
        Returns:
            Список тем новости
        """
        self._ensure_token()
        
        prompt = f"""Ты — эксперт по категоризации новостей. Определи, относится ли следующая новость к теме "транспорт".

Новость:
{news_text}

Проанализируй содержание новости и определи, относится ли она к теме "транспорт".

Верни только "транспорт" если новость относится к транспорту, или "нет" если не относится. Без дополнительных пояснений.
Пример ответа: транспорт"""
        
        headers = {
            "Authorization": f"Bearer {self.access_token}",
            "Content-Type": "application/json"
        }
        
        payload = {
            "model": GIGACHAT_MODEL,
            "messages": [
                {
                    "role": "user",
                    "content": prompt
                }
            ],
            "temperature": 0.3,
            "max_tokens": 100
        }
        
        try:
            response = requests.post(
                self.api_url,
                headers=headers,
                json=payload,
                verify=False,
                timeout=60
            )
            response.raise_for_status()
            
            result = response.json()
            categories_text = result.get("choices", [{}])[0].get("message", {}).get("content", "").strip().lower()
            
            # Парсим ответ - если содержит "транспорт", возвращаем список с одной темой
            if "транспорт" in categories_text and "нет" not in categories_text:
                return ["транспорт"]
            else:
                return []
            
        except Exception as e:
            logger.error(f"Ошибка при категоризации новости: {e}")
            return []