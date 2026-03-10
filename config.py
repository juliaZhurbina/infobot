"""
Конфигурационный файл с настройками бота и списком каналов для мониторинга
"""
import os
from dotenv import load_dotenv

load_dotenv()

# Telegram Bot Token
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")

# GigaChat API credentials
# Используется AUTH_KEY (base64 encoded credentials) или отдельные CLIENT_ID и CLIENT_SECRET
GIGACHAT_AUTH_KEY = os.getenv("GIGACHAT_AUTH_KEY")
GIGACHAT_CLIENT_ID = os.getenv("GIGACHAT_CLIENT_ID")
GIGACHAT_CLIENT_SECRET = os.getenv("GIGACHAT_CLIENT_SECRET")
GIGACHAT_SCOPE = os.getenv("GIGACHAT_SCOPE", "GIGACHAT_API_PERS")
GIGACHAT_API_AUTH_URL = os.getenv("GIGACHAT_API_AUTH_URL", "https://ngw.devices.sberbank.ru:9443/api/v2/oauth")
GIGACHAT_API_CHAT_URL = os.getenv("GIGACHAT_API_CHAT_URL", "https://gigachat.devices.sberbank.ru/api/v1/chat/completions")
GIGACHAT_MODEL = os.getenv("GIGACHAT_MODEL", "GigaChat-Pro")

# Database
DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///news.db")

# Admin user IDs (для административных функций, опционально)
ADMIN_IDS = [int(id.strip()) for id in os.getenv("ADMIN_IDS", "").split(",") if id.strip()]

# Канал/группа для публикации сводок (ID канала или группы, например: -1001234567890)
# Можно указать username канала (например: @my_channel) или ID (число)
SUMMARY_CHAT_ID = os.getenv("SUMMARY_CHAT_ID")

# Update interval in minutes
UPDATE_INTERVAL = int(os.getenv("UPDATE_INTERVAL", "60"))

# Список каналов для мониторинга
MONITORED_CHANNELS = {
    # Министерства
    "МВД России": "@mediamvd",
    "МЧС России": "@mchs_official",
    "МИД России": "@MID_Russia",
    "Минобороны России": "@mod_russia",
    "Минздрав России": "@minzdrav_ru",
    "Минкультуры России": "@mincultrussia",
    "Минобрнауки России": "@minobrnaukiofficial",
    "Минприроды России": "@prirodovedenie_rus",
    "Минпромторг России": "@minpromtorg_ru",
    "Минпросвещения России": "@bpshkola",
    "Минвостокразвития России": "@minvostok",
    "Минсельхоз России": "@mcx_ru",
    "Минспорт России": "@minsport_russia",
    "Минстрой России": "@minstroyrf",
    "Минтруд России": "@mintrudrf",
    "Минфин России": "@minfin",
    "Минцифры России": "@mintsifry",
    "Минэкономразвития России": "@minec_russia",
    "Минэнерго России": "@minenergo_official",
    
    # Федеральные службы и агентства
    "Россотрудничество": "@rossotrudnichestvo",
    "ФСИН России": "@fsinrussia",
    "Росздравнадзор": "@roszdravnadzor_official",
    "Росгидромет": "@roshydromet",
    "Росводресурсы": "@rosvodresursy",
    "Рослесхоз": "@Rosleshoz_official",
    "Роснедра": "@rosnedragovru",
    "Росстандарт": "@rosstandart",
    "Россельхознадзор": "@fsvps_official",
    "Росрыболовство": "@fish_gov_ru",
    "Ространснадзор": "@rostransnadzor_official",
    "Росавтодор": "@rosavtodor",
    "Роструд": "@rostrud_official",
    "ФНС России": "@nalog_gov_ru",
    "ФТС России": "@customs_rf",
    "Казначейство России": "@TreasuryofRussia",
    "Росимущество": "@rosim_gov_ru",
    "Роскомнадзор": "@rkn_tg",
    "Росаккредитация": "@fsagov",
    "Роспатент": "@RospatentFIPS",
    "Росгвардия": "@RosgvardOfficial",
    "Росфинмониторинг": "@fedsfm_ru",
    "ФАС России": "@fasrussia",
    "Росреестр": "@rosreestr_news",
    "Роспотребнадзор": "@rospotrebnadzor_ru",
    "Рособрнадзор": "@rosobrnadzor_official",
    "Ростехнадзор": "@gosnadzorru",
    "ФМБА России": "@fmba_of_russia",
    "Ростуризм": "@rostourism_official",
    "Росмолодежь": "@rosmolodez",
    "ФАДН России": "@fandrf",
}

# Отрасли для фильтрации новостей (10 отраслей)
NEWS_TOPICS = [
    "еком",
    "розничная торговля",
    "оптовая торговля",
    "услуги",
    "транспорт",
    "недвижимость",
    "рестораны",
    "отели",
    "производство",
    "строительство",
]

# Отображаемые названия отраслей (для /topics и сообщений)
INDUSTRY_DISPLAY_NAMES = {
    "еком": "ЕКОМ",
    "розничная торговля": "РОЗНИЧНАЯ ТОРГОВЛЯ",
    "оптовая торговля": "ОПТОВАЯ ТОРГОВЛЯ",
    "услуги": "УСЛУГИ",
    "транспорт": "ТРАНСПОРТ",
    "недвижимость": "НЕДВИЖИМОСТЬ",
    "рестораны": "РЕСТОРАНЫ",
    "отели": "ОТЕЛИ",
    "производство": "Производство",
    "строительство": "Строительство",
}

# Источники по отраслям: отрасль -> {название_источника: username_канала}
# Все отрасли работают одинаково: если у отрасли есть источники — новости берутся из них
INDUSTRY_SOURCES = {topic: {} for topic in NEWS_TOPICS}
INDUSTRY_SOURCES["еком"] = {
    "Коммерс": "@kommerc",
}
INDUSTRY_SOURCES["транспорт"] = {
    "Росавтодор": "@rosavtodor",
    "Ространснадзор": "@rostransnadzor_official",
    "Транспорт и логистика": "@transportandlogistic",
    "Грузовики и вообще": "@truksandall",
}
INDUSTRY_SOURCES["оптовая торговля"] = {
    "Retail.ru": "@retail_ru",
    "ТПП РФ": "@tpp_rf",
    "Минпромторг России": "@minpromtorg_ru",
}
INDUSTRY_SOURCES["производство"] = {
    "Retail.ru": "@retail_ru",
    "ТПП РФ": "@tpp_rf",
    "Минпромторг России": "@minpromtorg_ru",
}
INDUSTRY_SOURCES["розничная торговля"] = {
    "Retail.ru": "@retail_ru",
    "NewRetail": "@NewRetail",
    "Retail Loyalty Journal": "@retailloyaltyjournal",
    "CRPT Breaking": "@crptbreaking",
    "Sostav": "@sostav",
}
INDUSTRY_SOURCES["услуги"] = {
    "Коммерсантъ": "@kommersant",
    "CNewsDaily": "@CNewsDaily",
    "MEL.FM": "@melfm",
    "ActivityEdu": "@ActivityEdu",
    "Vademecum": "@vademecum_ru",
    "Vademecum Live": "@vademecum_live",
    "Госуслуги": "@gosuslugi",
}
INDUSTRY_SOURCES["рестораны"] = {
    "Restoran.me": "@restoran_me",
    "Restoved Official": "@restovedofficial",
    "Gastronom Super": "@gastronom_super",
}
INDUSTRY_SOURCES["отели"] = {
    "RBC Life": "@rbc_life",
    "FRiO Russia": "@frio_russia",
}
INDUSTRY_SOURCES["строительство"] = {
    "Great of Development": "@ggreat_of_development",
    "RCMM": "@rcmm_ru",
    "CCN88 Восток": "@ccn88vostok",
}
# Для добавления каналов по другим отраслям — заполняйте INDUSTRY_SOURCES["еком"], и т.д.

# Общие каналы (используются, если отрасль не выбрана)
GENERAL_SOURCES = {
    "Минэкономразвития России": "@minec_russia",
    "Российский экспорт": "@rusexportnews",
    "Минцифры России": "@mintsifry",
    "Опора России": "@opora_russia",
    "Ведомости": "@vedomosti",
    "Гарант Новости": "@garantnews",
    "Коммерсантъ": "@kommersant",
}