import os
import logging
import datetime
from pathlib import Path
from config import config

logger = logging.getLogger('doc_bot.file_utils')
logger.info("services/file_utils.py ЗАГРУЖЕН УСПЕШНО")


def ensure_dir_exists(path: str) -> bool:
    try:
        os.makedirs(path, exist_ok=True)
        return True
    except Exception as e:
        logger.error(f"Ошибка при создании директории {path}: {e}", exc_info=True)
        return False


def get_document_path(user_id: int, template_name: str) -> str:
    try:
        # Создаем путь для сохранения
        timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"{template_name}_{timestamp}.pdf"
        full_path = os.path.join(config.GENERATED_DOCUMENTS_PATH, str(user_id), filename)

        # Создаем директорию пользователя
        ensure_dir_exists(os.path.dirname(full_path))

        return full_path
    except Exception as e:
        logger.error(f"Ошибка при получении пути к документу: {e}", exc_info=True)
        return None


def get_logs_path() -> str:
    try:
        # Создаем директорию для логов, если она не существует
        logs_dir = os.path.dirname(config.LOGS_PATH)
        ensure_dir_exists(logs_dir)

        return config.LOGS_PATH
    except Exception as e:
        logger.error(f"Ошибка при получении пути к логам: {e}", exc_info=True)
        return "logs/bot.log"


def get_temp_path(filename: str) -> str:
    try:
        # Создаем полный путь
        full_path = os.path.join(config.TEMP_PATH, filename)

        # Создаем директорию, если она не существует
        ensure_dir_exists(config.TEMP_PATH)

        return full_path
    except Exception as e:
        logger.error(f"Ошибка при получении временного пути: {e}", exc_info=True)
        return filename


def clean_temp_files(days_old=1):
    try:
        if not os.path.exists(config.TEMP_PATH):
            return 0

        cutoff = datetime.datetime.now() - datetime.timedelta(days=days_old)
        deleted_count = 0

        for filename in os.listdir(config.TEMP_PATH):
            file_path = os.path.join(config.TEMP_PATH, filename)
            if os.path.isfile(file_path):
                file_time = datetime.datetime.fromtimestamp(os.path.getmtime(file_path))
                if file_time < cutoff:
                    os.remove(file_path)
                    deleted_count += 1

        return deleted_count
    except Exception as e:
        logger.error(f"Ошибка при очистке временных файлов: {e}", exc_info=True)
        return 0