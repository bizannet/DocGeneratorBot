import logging
import sqlite3
import os
import json
from pathlib import Path
from config import config

logger = logging.getLogger('doc_bot.templates')
logger.info("database/templates.py ЗАГРУЖЕН УСПЕШНО")

def get_templates() -> list:
    try:
        conn = sqlite3.connect(config.DATABASE_PATH)
        cursor = conn.cursor()

        cursor.execute("SELECT id, name, category, description, template_name, created_at FROM templates ORDER BY category, name")
        templates = cursor.fetchall()
        templates_list = []
        for template in templates:
            templates_list.append({
                'id': template[0],
                'name': template[1],
                'category': template[2],
                'description': template[3],
                'template_name': template[4],
                'created_at': template[5]
            })

        return templates_list

    except Exception as e:
        logger.error(f"Ошибка при получении списка шаблонов: {e}", exc_info=True)
        return []
    finally:
        if conn:
            conn.close()


def get_template_by_id(template_id: int) -> dict:
    try:
        conn = sqlite3.connect(config.DATABASE_PATH)
        cursor = conn.cursor()

        cursor.execute("SELECT id, name, category, description, template_name, created_at FROM templates WHERE id = ?", (template_id,))
        template = cursor.fetchone()

        if not template:
            return None

        return {
            'id': template[0],
            'name': template[1],
            'category': template[2],
            'description': template[3],
            'template_name': template[4],
            'created_at': template[5]
        }

    except Exception as e:
        logger.error(f"Ошибка при получении шаблона по ID: {e}", exc_info=True)
        return None
    finally:
        if conn:
            conn.close()


def get_templates_by_category(category: str) -> list:
    try:
        conn = sqlite3.connect(config.DATABASE_PATH)
        cursor = conn.cursor()
        valid_categories = ["business", "realestate", "logistics", "website"]
        if category not in valid_categories and category != "all":
            logger.warning(f"Недопустимая категория: {category}")
            return []

        if category == "all":
            cursor.execute("SELECT id, name, category, description, template_name, created_at FROM templates ORDER BY category, name")
        else:
            cursor.execute("SELECT id, name, category, description, template_name, created_at FROM templates WHERE category = ? ORDER BY name", (category,))

        templates = cursor.fetchall()

        logger.info(f"Raw результат запроса для категории {category}: {templates}")

        # Формируем список шаблонов
        templates_list = []
        for template in templates:
            template_dict = {
                'id': template[0],
                'name': template[1],
                'category': template[2],
                'description': template[3],
                'template_name': template[4],
                'created_at': template[5]
            }
            templates_list.append(template_dict)
            logger.info(f"Добавлен шаблон: {template_dict['name']} (ID: {template_dict['id']})")

        logger.info(f"Найдено шаблонов для категории {category}: {len(templates_list)}")
        return templates_list

    except Exception as e:
        logger.error(f"Ошибка при получении шаблонов по категории: {e}", exc_info=True)
        return []
    finally:
        if conn:
            conn.close()


def create_template(name: str, category: str, description: str, template_name: str) -> int:
    try:
        valid_categories = ["business", "realestate", "logistics", "website"]
        if category not in valid_categories:
            logger.error(f"Недопустимая категория: {category}. Допустимые категории: {valid_categories}")
            return None

        conn = sqlite3.connect(config.DATABASE_PATH)
        cursor = conn.cursor()

        cursor.execute("""
            INSERT INTO templates (
                name, category, description, template_name
            ) VALUES (?, ?, ?, ?)
        """, (name, category, description, template_name))

        conn.commit()
        return cursor.lastrowid

    except Exception as e:
        logger.error(f"Ошибка при создании шаблона: {e}", exc_info=True)
        return None
    finally:
        if conn:
            conn.close()


def update_template(template_id: int, name: str = None, category: str = None,
                    description: str = None, template_name: str = None) -> bool:
    try:
        template = get_template_by_id(template_id)
        if not template:
            logger.error(f"Шаблон с ID {template_id} не найден")
            return False
        if category:
            valid_categories = ["business", "realestate", "logistics", "website"]
            if category not in valid_categories:
                logger.error(f"Недопустимая категория: {category}. Допустимые категории: {valid_categories}")
                return False

        conn = sqlite3.connect(config.DATABASE_PATH)
        cursor = conn.cursor()
        set_clause = []
        values = []

        if name:
            set_clause.append("name = ?")
            values.append(name)

        if category:
            set_clause.append("category = ?")
            values.append(category)

        if description:
            set_clause.append("description = ?")
            values.append(description)

        if template_name:
            set_clause.append("template_name = ?")
            values.append(template_name)

        if set_clause:
            query = f"UPDATE templates SET {', '.join(set_clause)} WHERE id = ?"
            values.append(template_id)

            # Выполняем запрос
            cursor.execute(query, tuple(values))
            conn.commit()

            return cursor.rowcount > 0

        return False

    except Exception as e:
        logger.error(f"Ошибка при обновлении шаблона: {e}", exc_info=True)
        return False
    finally:
        if conn:
            conn.close()


def get_user_templates(user_id: int) -> list:
    try:
        conn = sqlite3.connect(config.DATABASE_PATH)
        cursor = conn.cursor()

        cursor.execute("""
            SELECT * FROM user_templates 
            WHERE user_id = ? 
            ORDER BY created_at DESC
        """, (user_id,))

        templates = cursor.fetchall()

        # Формируем список шаблонов
        templates_list = []
        for template in templates:
            try:
                templates_list.append({
                    'id': template[0],
                    'user_id': template[1],
                    'name': template[2],
                    'document_type': template[3],
                    'data': eval(template[4]),
                    'created_at': template[5],
                    'updated_at': template[6]
                })
            except Exception as e:
                logger.error(f"Ошибка при обработке шаблона пользователя: {e}", exc_info=True)

        return templates_list

    except Exception as e:
        logger.error(f"Ошибка при получении шаблонов пользователя: {e}", exc_info=True)
        return []
    finally:
        if conn:
            conn.close()


def create_user_template(user_id: int, name: str, document_type: str, data: dict) -> int:
    try:
        conn = sqlite3.connect(config.DATABASE_PATH)
        cursor = conn.cursor()
        data_str = str(data)

        cursor.execute("""
            INSERT INTO user_templates (
                user_id, name, document_type, data
            ) VALUES (?, ?, ?, ?)
        """, (user_id, name, document_type, data_str))

        conn.commit()

        return cursor.lastrowid

    except Exception as e:
        logger.error(f"Ошибка при создании шаблона пользователя: {e}", exc_info=True)
        return None
    finally:
        if conn:
            conn.close()


def get_user_template_by_id(user_id: int, template_id: int) -> dict:
    try:
        conn = sqlite3.connect(config.DATABASE_PATH)
        cursor = conn.cursor()

        cursor.execute("""
            SELECT * FROM user_templates 
            WHERE id = ? AND user_id = ?
        """, (template_id, user_id))

        template = cursor.fetchone()

        if not template:
            return None

        try:
            return {
                'id': template[0],
                'user_id': template[1],
                'name': template[2],
                'document_type': template[3],
                'data': eval(template[4]),
                'created_at': template[5],
                'updated_at': template[6]
            }
        except Exception as e:
            logger.error(f"Ошибка при обработке данных шаблона: {e}", exc_info=True)
            return None

    except Exception as e:
        logger.error(f"Ошибка при получении шаблона пользователя по ID: {e}", exc_info=True)
        return None
    finally:
        if conn:
            conn.close()


def update_user_template(template_id: int, data: dict) -> bool:
    try:
        conn = sqlite3.connect(config.DATABASE_PATH)
        cursor = conn.cursor()
        data_str = str(data)

        cursor.execute("""
            UPDATE user_templates 
            SET data = ?, updated_at = CURRENT_TIMESTAMP 
            WHERE id = ?
        """, (data_str, template_id))

        conn.commit()

        return cursor.rowcount > 0

    except Exception as e:
        logger.error(f"Ошибка при обновлении шаблона пользователя: {e}", exc_info=True)
        return False
    finally:
        if conn:
            conn.close()


def delete_user_template(user_id: int, template_id: int) -> bool:
    try:
        conn = sqlite3.connect(config.DATABASE_PATH)
        cursor = conn.cursor()

        cursor.execute("""
            DELETE FROM user_templates 
            WHERE id = ? AND user_id = ?
        """, (template_id, user_id))

        conn.commit()

        return cursor.rowcount > 0

    except Exception as e:
        logger.error(f"Ошибка при удалении шаблона пользователя: {e}", exc_info=True)
        return False
    finally:
        if conn:
            conn.close()


def get_template_by_name(template_name: str) -> dict:
    try:
        conn = sqlite3.connect(config.DATABASE_PATH)
        cursor = conn.cursor()

        cursor.execute("SELECT id, name, category, description, template_name, created_at FROM templates WHERE template_name = ?", (template_name,))
        template = cursor.fetchone()

        if not template:
            return None

        return {
            'id': template[0],
            'name': template[1],
            'category': template[2],
            'description': template[3],
            'template_name': template[4],
            'created_at': template[5]
        }

    except Exception as e:
        logger.error(f"Ошибка при получении шаблона по имени: {e}", exc_info=True)
        return None
    finally:
        if conn:
            conn.close()


def get_all_templates() -> list:
    try:
        conn = sqlite3.connect(config.DATABASE_PATH)
        cursor = conn.cursor()

        cursor.execute("SELECT id, name, category, description, template_name, created_at FROM templates ORDER BY category, name")
        templates = cursor.fetchall()

        # Формируем список шаблонов
        templates_list = []
        for template in templates:
            templates_list.append({
                'id': template[0],
                'name': template[1],
                'category': template[2],
                'description': template[3],
                'template_name': template[4],
                'created_at': template[5]
            })

        return templates_list

    except Exception as e:
        logger.error(f"Ошибка при получении списка всех шаблонов: {e}", exc_info=True)
        return []
    finally:
        if conn:
            conn.close()


def get_template_by_id_from_filesystem(category: str, template_id: int) -> dict:
    try:
        all_templates = get_all_templates()
        for template in all_templates:
            if template['id'] == template_id and template['category'] == category:
                return template

        return None

    except Exception as e:
        logger.error(f"Ошибка при получении шаблона из файловой системы: {e}", exc_info=True)
        return None


def seed_templates():
    logger.info("Заполнение базы данных тестовыми шаблонами...")
    def template_exists(template_name, category):
        try:
            if category == "website":
                template_dir = Path(config.DOCUMENTS_PATH) / "templates" / category / template_name
            else:
                template_dir = Path(config.DOCUMENTS_PATH) / "templates" / "contracts" / template_name
            description_path = template_dir / "description.md"
            return description_path.exists()
        except Exception as e:
            logger.error(f"Ошибка при проверке существования шаблона {template_name}: {e}")
            return False

    # Документы для бизнеса
    business_templates = [
        ("Договор оказания онлайн-услуг", "business", "", "service_contract_online_2025"),
        ("Договор подряда", "business", "", "subcontract_2025"),
        ("Договор поставки", "business", "", "supply_contract_2025"),
        ("Акт приема-передачи выполненных работ", "business", "", "work_acceptance_2025"),
        ("Смета работ", "business", "", "work_estimate_2025"),
        ("Техническое задание", "business", "", "work_technical_task_2025")
    ]

    # Документы для логистики
    logistics_templates = [
        ("Договор грузоперевозки", "logistics", "", "cargo_transport_2025"),
        ("Товарно-транспортная накладная (ТТН)", "logistics", "", "cargo_transport_waybill_2025"),
        ("Доверенность на получение груза (М-2)", "logistics", "", "cargo_power_of_attorney_2025"),
        ("Акт приема-передачи груза", "logistics", "", "cargo_acceptance_2025"),
        ("Спецификация груза", "logistics", "", "cargo_specification_2025")
    ]

    # Документы для недвижимости
    realestate_templates = [
        ("Договор аренды нежилого помещения", "realestate", "", "commercial_rental_2025"),
        ("Акт приема-передачи нежилого помещения", "realestate", "", "commercial_property_transfer_2025"),
        ("Опись имущества", "realestate", "", "inventory_2025"),
        ("Договор долгосрочной аренды жилья", "realestate", "", "rental_contract_2025"),
        ("Акт приема-передачи квартиры", "realestate", "", "residential_property_transfer_2025")
    ]

    # Документы для сайта
    website_templates = [
        ("Согласие на обработку персональных данных", "website", "", "consent_2025"),
        ("Политика конфиденциальности", "website", "", "privacy_policy_2025"),
        ("Политика использования cookie", "website", "", "cookie_policy_2025"),
        ("Согласие на рекламные рассылки", "website", "", "marketing_consent_2025"),
        ("Уведомление в Роскомнадзор", "website", "", "notification_2025")
    ]

    try:
        conn = sqlite3.connect(config.DATABASE_PATH)
        cursor = conn.cursor()

        # Проверяем, есть ли уже шаблоны в базе данных
        cursor.execute("SELECT COUNT(*) FROM templates")
        count = cursor.fetchone()[0]

        if count > 0:
            logger.info(f"В базе данных уже есть {count} шаблонов. Пропускаем заполнение.")
            return

        # Добавляем шаблоны
        all_templates = business_templates + logistics_templates + realestate_templates + website_templates

        # Фильтруем шаблоны, которые существуют в файловой системе
        valid_templates = []
        for template in all_templates:
            if template_exists(template[3], template[1]):
                valid_templates.append(template)
            else:
                logger.warning(f"Пропускаем шаблон {template[3]}, так как он не найден в файловой системе")

        if not valid_templates:
            logger.error("Не найдено ни одного шаблона в файловой системе. Проверьте структуру проекта.")
            return

        for template in valid_templates:
            logger.info(f"Добавление шаблона: {template[0]} (категория: {template[1]})")
            cursor.execute("""
                INSERT INTO templates (
                    name, category, description, template_name
                ) VALUES (?, ?, ?, ?)
            """, template)

        conn.commit()
        logger.info(f"Успешно добавлено {len(valid_templates)} тестовых шаблонов документов")

    except Exception as e:
        logger.error(f"Ошибка при заполнении базы данных тестовыми шаблонами: {e}", exc_info=True)
    finally:
        if conn:
            conn.close()