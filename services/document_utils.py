import logging
import re
import json
from pathlib import Path

logger = logging.getLogger('doc_bot.document_utils')

def clean_document_name(name: str) -> str:
    """Удаляет цену из названия документа"""
    # Удаляем цену в конце названия
    name = re.sub(r'\s*[-—]\s*\d+\s*₽', '', name)
    name = re.sub(r'\s*\(\d+\s*руб\.\)', '', name)
    name = re.sub(r'\s*\d+\s*₽', '', name)
    name = re.sub(r'\s*-\s*\d+\s*рублей', '', name)

    # Удаляем лишние пробелы
    name = re.sub(r'\s+', ' ', name).strip()

    return name


def get_doc_description(category: str, template_name: str) -> str:
    file_path = Path(__file__).parent.parent / "documents" / "templates" / category / template_name / "description.md"
    try:
        return file_path.read_text(encoding="utf-8")
    except (FileNotFoundError, IOError):
        return ""


def load_document_questions(doc_id: int):
    from database.templates import get_template_by_id
    doc = get_template_by_id(doc_id)
    if not doc:
        logger.error(f"Документ с ID {doc_id} не найден")
        return None
    config_file = "website_questions.json" if doc["category"] == "website" else "contracts_questions.json"
    config_path = Path(__file__).parent.parent / "configs" / config_file

    try:
        if config_path.exists():
            with open(config_path, "r", encoding="utf-8") as f:
                config_data = json.load(f)
                for doc_id_key, doc_config in config_data.items():
                    if doc_config.get("template_name") == doc["template_name"]:
                        return doc_config.get("questions", [])
        return None
    except Exception as e:
        logger.error(f"Ошибка при загрузке вопросов для документа {doc_id}: {e}", exc_info=True)
        return None