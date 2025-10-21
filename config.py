import os
from pathlib import Path
from dotenv import load_dotenv

# Загружаем переменные окружения из .env файла
load_dotenv()

BASE_DIR = Path(__file__).parent.parent

class Config:
    """Класс конфигурации для удобного доступа к настройкам"""

    # Основные настройки
    BOT_TOKEN = os.getenv("BOT_TOKEN", "YOUR_BOT_TOKEN_HERE")
    ADMIN_IDS = [int(id) for id in os.getenv("ADMIN_IDS", "").split(",") if id.strip()]
    BOT_USERNAME = os.getenv("BOT_USERNAME", "your_bot_username")

    # Настройки каналов и чатов
    REVIEWS_CHANNEL_ID = int(os.getenv("REVIEWS_CHANNEL_ID", "-1000000000000"))
    TELEGRAM_CHANNEL = os.getenv("TELEGRAM_CHANNEL", "@your_channel")
    SUPPORT_CHAT_ID = int(os.getenv("SUPPORT_CHAT_ID", "0"))  # Добавлено для админ-панели

    # Пути к файлам
    DATABASE_DIR = BASE_DIR / "DocGeneratorBot" / "database"
    DATABASE_PATH = DATABASE_DIR / "bot.db"

    # Пути к документам
    DOCUMENTS_PATH = BASE_DIR / "DocGeneratorBot" / "documents"
    TEMPLATES_PATH = BASE_DIR / "DocGeneratorBot" / "documents" / "templates"
    GENERATED_DOCUMENTS_PATH = BASE_DIR / "DocGeneratorBot" / "documents" / "generated"
    STATIC_PATH = BASE_DIR / "DocGeneratorBot" / "documents" / "static"
    TEMP_PATH = BASE_DIR / "DocGeneratorBot" / "temp"
    LOGS_PATH = BASE_DIR / "DocGeneratorBot" / "logs" / "bot.log"

    # Настройки платежной системы
    YOOKASSA_SHOP_ID = os.getenv("YOOKASSA_SHOP_ID")
    YOOKASSA_SECRET_KEY = os.getenv("YOOKASSA_SECRET_KEY")

    # Настройки бота
    BOT_NAME = os.getenv("BOT_NAME", "DocGeneratorBot")
    BOT_DESCRIPTION = os.getenv("BOT_DESCRIPTION", "Автогенерация документов по вашим реквизитам")

    # Срок действия черновиков (в часах)
    DRAFT_EXPIRATION_HOURS = int(os.getenv("DRAFT_EXPIRATION_HOURS", "24"))

    # Настройки для рассылки
    NEWSLETTER_INTERVAL = int(os.getenv("NEWSLETTER_INTERVAL", "24"))  # часы

    # Настройки для админ-панели
    ADMIN_BOT_TOKEN = os.getenv("ADMIN_BOT_TOKEN", "")  # Для отдельного бота админ-уведомлений
    STATS_NOTIFICATION_TIME = os.getenv("STATS_NOTIFICATION_TIME", "09:00")  # Время отправки статистики

    # Настройки для партнерской программы
    PARTNER_PERCENT = int(os.getenv("PARTNER_PERCENT", "30"))  # процент от заказа

    # Настройки для генерации документов
    DEFAULT_FONT_PATH = BASE_DIR / "DocGeneratorBot" / "documents" / "static" / "fonts" / "DejaVuSans.ttf"


# Создаем экземпляр конфигурации
config = Config()

# Проверка критических настроек
if config.BOT_TOKEN == "YOUR_BOT_TOKEN_HERE":
    raise ValueError("Не установлен BOT_TOKEN в .env файле")

if not config.ADMIN_IDS:
    raise ValueError("Не установлены ADMIN_IDS в .env файле")

if not config.YOOKASSA_SHOP_ID or not config.YOOKASSA_SECRET_KEY or config.YOOKASSA_SHOP_ID.strip() == "" or config.YOOKASSA_SECRET_KEY.strip() == "":
    raise ValueError("Не установлены настройки ЮKassa в .env файле")

if config.SUPPORT_CHAT_ID == 0:
    raise ValueError("Не установлен SUPPORT_CHAT_ID в .env файле")

# Создаем необходимые директории
for path in [
    config.DOCUMENTS_PATH,
    config.TEMPLATES_PATH,
    config.GENERATED_DOCUMENTS_PATH,
    config.STATIC_PATH,
    config.DATABASE_DIR,
    config.TEMP_PATH,
    config.LOGS_PATH.parent
]:
    path.mkdir(parents=True, exist_ok=True)