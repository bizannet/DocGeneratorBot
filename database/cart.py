"""
База данных для работы с корзиной.

Этот файл содержит функции для:
- Добавления документов в корзину
- Получения элементов корзины
- Очистки корзины
- Управления количеством элементов
- Расчета общей суммы корзины
- Сохранения filled_data для последующей генерации документов
"""

import sqlite3
import logging
import json
from datetime import datetime
from pathlib import Path
from config import config
from services.pricing import get_template_price, get_autogeneration_price
logger = logging.getLogger('doc_bot.db.cart')


def get_connection():
    """Создает и возвращает соединение с базой данных"""
    try:
        db_path = Path(config.DATABASE_PATH) if isinstance(config.DATABASE_PATH, str) else config.DATABASE_PATH
        db_path.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(str(db_path))
        conn.row_factory = sqlite3.Row
        logger.debug(f"Подключение к БД установлено: {db_path}")
        create_tables_if_not_exist(conn)
        return conn
    except Exception as e:
        logger.error(f"Ошибка подключения к базе данных: {e}")
        raise


def create_tables_if_not_exist(conn):
    """Создает таблицу cart_items, если она не существует, с учетом filled_data"""
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='cart_items'")
        table_exists = cursor.fetchone() is not None

        if not table_exists:
            cursor.execute('''
                CREATE TABLE cart_items (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER NOT NULL,
                    cart_item_id TEXT NOT NULL,
                    quantity INTEGER NOT NULL DEFAULT 1,
                    price REAL NOT NULL,
                    doc_id INTEGER NOT NULL,
                    doc_name TEXT NOT NULL,
                    category TEXT NOT NULL,
                    template_name TEXT NOT NULL,
                    price_type TEXT NOT NULL DEFAULT 'template',
                    filled_data TEXT,
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
                )
            ''')
            logger.info("Таблица cart_items создана с колонкой filled_data")
            conn.commit()
        else:
            # Проверяем и добавляем недостающие колонки
            cursor.execute("PRAGMA table_info(cart_items)")
            columns = [info[1] for info in cursor.fetchall()]

            if 'filled_data' not in columns:
                cursor.execute("ALTER TABLE cart_items ADD COLUMN filled_data TEXT")
                logger.info("Добавлена колонка filled_data")
                conn.commit()

            if 'price_type' not in columns:
                cursor.execute("ALTER TABLE cart_items ADD COLUMN price_type TEXT NOT NULL DEFAULT 'template'")
                logger.info("Добавлена колонка price_type")
                conn.commit()

            if 'updated_at' not in columns:
                cursor.execute("ALTER TABLE cart_items ADD COLUMN updated_at DATETIME DEFAULT CURRENT_TIMESTAMP")
                logger.info("Добавлена колонка updated_at")
                conn.commit()

            if 'created_at' not in columns:
                cursor.execute("ALTER TABLE cart_items ADD COLUMN created_at DATETIME DEFAULT CURRENT_TIMESTAMP")
                logger.info("Добавлена колонка created_at")
                conn.commit()

    except Exception as e:
        logger.error(f"Ошибка при создании/обновлении таблиц: {e}")
        conn.rollback()
        raise


def add_to_cart(
    user_id: int,
    cart_item_id: str,
    doc_id: int,
    doc_name: str,
    category: str,
    template_name: str,
    price: float,
    price_type: str = "template",
    filled_data: dict = None
):
    """
    Добавляет документ в корзину.
    Теперь принимает отдельные параметры вместо словаря.
    """
    try:
        conn = get_connection()
        cursor = conn.cursor()

        filled_data_json = json.dumps(filled_data or {}, ensure_ascii=False)

        cursor.execute('''
            SELECT id, quantity FROM cart_items 
            WHERE user_id = ? AND cart_item_id = ?
        ''', (user_id, cart_item_id))
        existing_item = cursor.fetchone()

        if existing_item:
            new_quantity = existing_item['quantity'] + 1
            cursor.execute('''
                UPDATE cart_items 
                SET quantity = ?, price = ?, filled_data = ?, updated_at = CURRENT_TIMESTAMP
                WHERE id = ?
            ''', (new_quantity, price, filled_data_json, existing_item['id']))
            action = "обновлен"
        else:
            cursor.execute('''
                INSERT INTO cart_items (
                    user_id, cart_item_id, quantity, price, doc_id, doc_name,
                    category, template_name, price_type, filled_data,
                    created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
            ''', (
                user_id,
                cart_item_id,
                1,
                price,
                doc_id,
                doc_name,
                category,
                template_name,
                price_type,
                filled_data_json
            ))
            action = "добавлен"

        conn.commit()
        conn.close()
        logger.info(
            f"Документ {cart_item_id} ({doc_name}) {action} в корзину пользователя {user_id} "
            f"по цене {price} ₽ с filled_ {len(filled_data or {})} полей"
        )
        return True
    except Exception as e:
        logger.error(f"Ошибка добавления документа {cart_item_id} в корзину: {e}", exc_info=True)
        return False


def get_cart_items(user_id: int):
    """Получает элементы корзины пользователя."""
    try:
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute('SELECT * FROM cart_items WHERE user_id = ?', (user_id,))
        results = cursor.fetchall()
        conn.close()

        items = []
        for row in results:
            item = dict(row)
            try:
                item['filled_data'] = json.loads(item.get('filled_data', '{}')) if item.get('filled_data') else {}
            except (json.JSONDecodeError, TypeError) as e:
                logger.warning(f"Ошибка парсинга filled_data для item {item.get('id')}: {e}")
                item['filled_data'] = {}
            items.append(item)
        return items
    except Exception as e:
        logger.error(f"Ошибка получения корзины пользователя {user_id}: {e}", exc_info=True)
        return []


def clear_cart(user_id: int):
    """Очищает корзину пользователя"""
    try:
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute('DELETE FROM cart_items WHERE user_id = ?', (user_id,))
        conn.commit()
        conn.close()
        logger.info(f"Корзина пользователя {user_id} очищена")
        return True
    except Exception as e:
        logger.error(f"Ошибка очистки корзины: {e}", exc_info=True)
        return False


def remove_from_cart(user_id: int, cart_item_id: str):
    """Удаляет документ из корзины"""
    try:
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute('DELETE FROM cart_items WHERE user_id = ? AND cart_item_id = ?', (user_id, cart_item_id))
        conn.commit()
        conn.close()
        logger.info(f"Документ {cart_item_id} удален из корзины пользователя {user_id}")
        return True
    except Exception as e:
        logger.error(f"Ошибка удаления документа: {e}", exc_info=True)
        return False


def get_cart_total(user_id: int) -> float:
    """Получает общую сумму корзины"""
    try:
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute('SELECT COALESCE(SUM(quantity * price), 0) FROM cart_items WHERE user_id = ?', (user_id,))
        result = cursor.fetchone()
        conn.close()
        return float(result[0]) if result else 0.0
    except Exception as e:
        logger.error(f"Ошибка получения общей суммы корзины: {e}", exc_info=True)
        return 0.0


def get_cart_item_count(user_id: int) -> int:
    """Получает количество элементов в корзине"""
    try:
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute('SELECT COALESCE(SUM(quantity), 0) FROM cart_items WHERE user_id = ?', (user_id,))
        result = cursor.fetchone()
        conn.close()
        return result[0] if result else 0
    except Exception as e:
        logger.error(f"Ошибка получения количества элементов: {e}", exc_info=True)
        return 0


def get_user_cart(user_id: int) -> dict:
    """Получает полную информацию о корзине пользователя."""
    try:
        items = get_cart_items(user_id)
        total = get_cart_total(user_id)
        item_count = get_cart_item_count(user_id)
        return {
            'items': items,
            'total': total,
            'item_count': item_count
        }
    except Exception as e:
        logger.error(f"Ошибка получения полной информации о корзине: {e}", exc_info=True)
        return {'items': [], 'total': 0.0, 'item_count': 0}


def update_cart_item_quantity(user_id: int, cart_item_id: str, quantity: int):
    """Обновляет количество документа в корзине"""
    try:
        conn = get_connection()
        cursor = conn.cursor()
        if quantity <= 0:
            cursor.execute('DELETE FROM cart_items WHERE user_id = ? AND cart_item_id = ?', (user_id, cart_item_id))
        else:
            cursor.execute('''
                UPDATE cart_items
                SET quantity = ?, updated_at = CURRENT_TIMESTAMP
                WHERE user_id = ? AND cart_item_id = ?
            ''', (quantity, user_id, cart_item_id))
        conn.commit()
        conn.close()
        logger.info(f"Количество документа {cart_item_id} обновлено до {quantity}")
        return True
    except Exception as e:
        logger.error(f"Ошибка обновления количества: {e}", exc_info=True)
        return False