import logging
import os
import json
import re
from pathlib import Path
from datetime import datetime
from config import config
from services.amount_to_words import amount_to_words
from services.pricing import get_template_price, get_autogeneration_price  # <-- ДОБАВЛЕНО

logger = logging.getLogger('doc_bot.document_service')
logger.info("services/document_service.py ЗАГРУЖЕН УСПЕШНО")

templates_cache = {}


def clear_templates_cache():
    """Очищает кэш шаблонов"""
    global templates_cache
    templates_cache = {}
    logger.info("Кэш шаблонов очищен")


def get_template_info(template_name: str, category: str = None) -> dict:
    try:
        # Сначала ищем в папке contracts
        template_dir = Path(config.DOCUMENTS_PATH) / "templates" / "contracts" / template_name

        # Если не найдено в contracts, пробуем найти в website
        if not (template_dir / "metadata.json").exists():
            template_dir = Path(config.DOCUMENTS_PATH) / "templates" / "website" / template_name

        # Если шаблон не найден
        if not (template_dir / "metadata.json").exists():
            logger.warning(f"Шаблон не найден: {template_name}")
            return {
                'id': template_name,
                'name': template_name.replace('_', ' ').title(),
                'category': category or 'unknown',
                'description': 'Описание отсутствует',
                'price': {
                    'template': get_template_price(),
                    'autogen': get_autogeneration_price()
                },
                'template_name': template_name
            }

        metadata_path = template_dir / "metadata.json"

        # Загружаем metadata
        with open(metadata_path, 'r', encoding='utf-8') as f:
            metadata = json.load(f)

        # Добавляем обязательные поля, если их нет
        if 'id' not in metadata:
            metadata['id'] = template_name
        if 'template_name' not in metadata:
            metadata['template_name'] = template_name
        if 'category' not in metadata and category:
            metadata['category'] = category
        if 'price' not in metadata:
            metadata['price'] = {
                'template': get_template_price(),
                'autogen': get_autogeneration_price()
            }

        # Загружаем описание из description.md, если есть
        description_path = template_dir / "description.md"
        if description_path.exists():
            with open(description_path, 'r', encoding='utf-8') as f:
                description_text = f.read().strip()
                if description_text:
                    metadata['description'] = description_text

        logger.info(f"Информация о шаблоне успешно загружена: {metadata}")
        return metadata
    except Exception as e:
        logger.error(f"Ошибка при загрузке информации о шаблоне: {e}", exc_info=True)
        return {
            'id': template_name,
            'name': template_name.replace('_', ' ').title(),
            'category': category or 'unknown',
            'description': 'Ошибка загрузки описания',
            'price': {
                'template': get_template_price(),
                'autogen': get_autogeneration_price()
            },
            'template_name': template_name
        }


def get_templates_from_filesystem(category: str) -> list:
    try:
        # Проверяем кэш
        cache_key = f"templates_{category}"
        if cache_key in templates_cache:
            logger.debug(f"Используем кэшированные шаблоны для категории {category}")
            return templates_cache[cache_key]

        logger.debug(f"Загружаем шаблоны для категории {category} из файловой системы")

        # Определяем путь к папке с шаблонами
        templates_base_path = Path(config.DOCUMENTS_PATH) / "templates"
        logger.info(f"Используем базовый путь к шаблонам: {templates_base_path}")

        # Проверяем существование базовой папки
        if not templates_base_path.exists() or not templates_base_path.is_dir():
            logger.warning(f"Базовая папка шаблонов не найдена: {templates_base_path}")
            return []

        # Ищем шаблоны в подпапках contracts и website
        template_dirs = [
            templates_base_path / "contracts",
            templates_base_path / "website"
        ]

        # Собираем список шаблонов
        templates = []

        for templates_dir in template_dirs:
            # Проверяем существование папки
            if not templates_dir.exists() or not templates_dir.is_dir():
                logger.debug(f"Папка шаблонов не найдена: {templates_dir}")
                continue

            logger.info(f"Ищем шаблоны в: {templates_dir}")

            # Проходим по всем папкам в папке шаблонов
            for item in templates_dir.iterdir():
                if item.is_dir():
                    # Загружаем метаданные
                    metadata_path = item / "metadata.json"
                    if metadata_path.exists():
                        try:
                            with open(metadata_path, "r", encoding="utf-8") as f:
                                metadata = json.load(f)

                                # Проверяем, совпадает ли категория
                                doc_category = str(metadata.get("category", "")).lower()
                                requested_category = category.lower()

                                logger.debug(
                                    f"Проверка шаблона {item.name}: категория в metadata = '{doc_category}', запрошенная категория = '{requested_category}'")

                                if doc_category == requested_category:
                                    # Создаем шаблон в нужном формате
                                    templates.append({
                                        'id': metadata.get("id", item.name),
                                        'name': metadata.get("name", item.name.replace("_", " ").title()),
                                        'category': category,
                                        'description': metadata.get("description", ""),
                                        'template_name': item.name,
                                        'price': metadata.get("price", {
                                            "template": get_template_price(),
                                            "autogen": get_autogeneration_price()
                                        })
                                    })
                        except Exception as e:
                            logger.error(f"Ошибка при загрузке metadata.json для {item.name}: {e}")

        logger.info(f"Найдено {len(templates)} шаблонов в категории {category} (из файловой системы)")

        # Сохраняем в кэш
        templates_cache[cache_key] = templates
        return templates

    except Exception as e:
        logger.error(f"Ошибка при получении шаблонов из файловой системы: {e}", exc_info=True)
        return []


def get_template_by_id_from_filesystem(category: str, template_identifier) -> dict:
    templates = get_templates_from_filesystem(category)
    if isinstance(template_identifier, str):
        for template in templates:
            if template['template_name'] == template_identifier:
                return template
        logger.error(f"Шаблон с именем {template_identifier} не найден в категории {category}")
        return None
    else:
        for template in templates:
            if template['id'] == template_identifier:
                return template
        logger.error(f"Шаблон с ID {template_identifier} не найден в категории {category}")
        return None


def get_template_path(template_name: str, file_type: str = "autogen") -> Path:
    try:
        template_dir = Path(config.DOCUMENTS_PATH) / "templates" / "contracts" / template_name
        if not (template_dir / "metadata.json").exists():
            template_dir = Path(config.DOCUMENTS_PATH) / "templates" / "website" / template_name
            if not (template_dir / "metadata.json").exists():
                logger.error(f"Шаблон не найден: {template_name}")
                return None

        if file_type == "autogen":
            return template_dir / "autogen.html"
        elif file_type == "sample":
            return template_dir / "sample.html"
        elif file_type == "description":
            return template_dir / "description.md"
        elif file_type == "metadata":
            return template_dir / "metadata.json"
        elif file_type == "questions":
            return template_dir / "questions.json"
        else:
            logger.error(f"Неизвестный тип файла: {file_type}")
            return None

    except Exception as e:
        logger.error(f"Ошибка при получении пути к шаблону: {e}", exc_info=True)
        return None


def load_questions(template_name: str) -> list:
    try:
        logger.info(f"Загрузка вопросов для шаблона: {template_name}")
        questions_path = get_template_path(template_name, "questions")
        if not questions_path or not questions_path.exists():
            logger.error(f"Файл questions.json не найден для шаблона: {template_name}")
            return []

        with open(questions_path, 'r', encoding='utf-8') as f:
            questions = json.load(f)

        logger.info(f"Загружено {len(questions)} вопросов для шаблона: {template_name}")
        return questions

    except Exception as e:
        logger.error(f"Ошибка при загрузке вопросов: {e}", exc_info=True)
        return []


def format_contract_amount(amount: float) -> str:
    try:
        amount_text = amount_to_words(amount)
        formatted_amount = "{:,.2f}".format(amount).replace(",", " ").replace(".", ",")
        return f"{formatted_amount} ₽ ({amount_text})"

    except Exception as e:
        logger.error(f"Ошибка при форматировании суммы контракта: {e}", exc_info=True)
        return f"{amount} ₽ (ошибка форматирования)"