import sqlite3
import json
import logging
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Any, Optional
from config import config

logger = logging.getLogger('doc_bot.db.orders')


def get_connection():
    """Создает и возвращает соединение с базой данных"""
    try:
        db_path = Path(config.DATABASE_PATH) if isinstance(config.DATABASE_PATH, str) else config.DATABASE_PATH
        db_path.parent.mkdir(parents=True, exist_ok=True)

        conn = sqlite3.connect(str(db_path))
        conn.row_factory = sqlite3.Row
        logger.debug(f"Подключение к БД установлено: {db_path}")
        create_tables_if_not_exists(conn)
        return conn
    except Exception as e:
        logger.error(f"Ошибка подключения к базе данных: {e}")
        raise


def safe_get_row_value(row: sqlite3.Row, column: str, default=None):
    try:
        if column in row.keys():
            return row[column]
        return default
    except (IndexError, KeyError):
        return default


def create_tables_if_not_exists(conn):
    """Создает таблицы, если они не существуют"""
    try:
        cursor = conn.cursor()

        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='orders'")
        if not cursor.fetchone():
            cursor.execute('''
                CREATE TABLE orders (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER NOT NULL,
                    total_price REAL NOT NULL,
                    item_count INTEGER NOT NULL,
                    savings REAL DEFAULT 0,
                    promocode TEXT,
                    discounted_price REAL,
                    status TEXT NOT NULL DEFAULT 'created',
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                    payment_id TEXT,
                    payment_data TEXT
                )
            ''')
            logger.info("Таблица orders создана (с поддержкой промокодов)")
        else:
            cursor.execute("PRAGMA table_info(orders)")
            columns = [column[1] for column in cursor.fetchall()]

            if 'savings' not in columns:
                try:
                    cursor.execute("ALTER TABLE orders ADD COLUMN savings REAL DEFAULT 0")
                    logger.info("Добавлена колонка savings")
                except sqlite3.OperationalError:
                    pass

            if 'promocode' not in columns:
                try:
                    cursor.execute("ALTER TABLE orders ADD COLUMN promocode TEXT")
                    logger.info("Добавлена колонка promocode")
                except sqlite3.OperationalError:
                    pass

            if 'discounted_price' not in columns:
                try:
                    cursor.execute("ALTER TABLE orders ADD COLUMN discounted_price REAL")
                    logger.info("Добавлена колонка discounted_price")
                except sqlite3.OperationalError:
                    pass

            if 'payment_id' not in columns:
                try:
                    cursor.execute("ALTER TABLE orders ADD COLUMN payment_id TEXT")
                    logger.info("Добавлена колонка payment_id")
                except sqlite3.OperationalError:
                    pass

            if 'payment_data' not in columns:
                try:
                    cursor.execute("ALTER TABLE orders ADD COLUMN payment_data TEXT")
                    logger.info("Добавлена колонка payment_data")
                except sqlite3.OperationalError:
                    pass

        # Проверяем и создаем таблицу order_items
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='order_items'")
        if not cursor.fetchone():
            cursor.execute('''
                CREATE TABLE order_items (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    order_id INTEGER NOT NULL,
                    doc_id INTEGER NOT NULL,
                    doc_name TEXT NOT NULL,
                    price REAL NOT NULL,
                    filled_data TEXT NOT NULL,
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (order_id) REFERENCES orders(id)
                )
            ''')
            logger.info("Таблица order_items создана")

        # Проверяем и создаем таблицу cart_items
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='cart_items'")
        if not cursor.fetchone():
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
            logger.info("Таблица cart_items создана")

        conn.commit()
    except Exception as e:
        logger.error(f"Ошибка при создании таблиц: {e}", exc_info=True)
        conn.rollback()
        raise


def create_order(user_id: int, total_price: float, item_count: int,
                 promocode: str = None, savings: float = 0,
                 discounted_price: float = None) -> int:
    try:
        conn = get_connection()
        cursor = conn.cursor()


        if discounted_price is None:
            discounted_price = total_price

        cursor.execute("""
            INSERT INTO orders (
                user_id, total_price, item_count, savings, promocode, discounted_price, status
            ) VALUES (?, ?, ?, ?, ?, ?, 'pending')
        """, (user_id, total_price, item_count, savings, promocode, discounted_price))

        conn.commit()
        order_id = cursor.lastrowid

        logger.info(f"Создан заказ #{order_id} для пользователя {user_id}")
        return order_id

    except Exception as e:
        logger.error(f"Ошибка при создании заказа: {e}", exc_info=True)
        return None
    finally:
        if conn:
            conn.close()


def add_order_item(order_id: int, doc_id: int, doc_name: str, price: float, filled_data: dict,
                   price_type: str = "template") -> bool:
    try:
        conn = get_connection()
        cursor = conn.cursor()

        cursor.execute("""
            INSERT INTO order_items (
                order_id, doc_id, doc_name, price, filled_data
            ) VALUES (?, ?, ?, ?, ?)
        """, (order_id, doc_id, doc_name, price, json.dumps(filled_data, ensure_ascii=False)))

        conn.commit()
        conn.close()

        logger.info(f"Позиция '{doc_name}' добавлена в заказ {order_id}")
        return True

    except Exception as e:
        logger.error(f"Ошибка при добавлении позиции в заказ: {e}", exc_info=True)
        return False


def update_order_status(order_id: int, status: str, pdf_path: str = None, docx_path: str = None) -> bool:
    valid_statuses = ['created', 'pending', 'paid', 'processing', 'document_generated', 'generation_error', 'sent', 'delivered', 'cancelled']
    if status not in valid_statuses:
        logger.warning(f"Попытка установить недопустимый статус '{status}' для заказа {order_id}")
        return False

    try:
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute("""
            UPDATE orders 
            SET status = ?, updated_at = CURRENT_TIMESTAMP
            WHERE id = ?
        """, (status, order_id))

        conn.commit()
        rows_affected = cursor.rowcount
        conn.close()

        if rows_affected > 0:
            logger.info(f"Статус заказа {order_id} обновлен на '{status}'")
            if pdf_path or docx_path:
                logger.debug(f"Пути к файлам проигнорированы для совместимости: pdf={pdf_path}, docx={docx_path}")
            return True
        else:
            logger.warning(f"Заказ {order_id} не найден для обновления статуса")
            return False

    except Exception as e:
        logger.error(f"Ошибка при обновлении статуса заказа: {e}", exc_info=True)
        return False


def get_all_orders(limit: int = 20, offset: int = 0) -> list:
    try:
        conn = get_connection()
        if not conn:
            logger.error("Не удалось получить соединение с БД для получения заказов.")
            return []
        cursor = conn.cursor()
        cursor.execute("""
            SELECT id, user_id, total_price, discounted_price, status, created_at, promocode, savings
            FROM orders
            ORDER BY created_at DESC
            LIMIT ? OFFSET ?
        """, (limit, offset))
        rows = cursor.fetchall()
        orders = []
        for row in rows:
            orders.append({
                'id': row[0],
                'user_id': row[1],
                'total_price': row[2],
                'discounted_price': row[3] if row[3] is not None else row[2],
                'status': row[4],
                'created_at': row[5],
                'promocode': row[6],
                'savings': row[7] or 0.0
            })
        conn.close()
        return orders
    except Exception as e:
        logger.error(f"Ошибка при получении списка заказов: {e}", exc_info=True)
        return []


def get_order_by_id(order_id: int) -> Optional[dict]:
    try:
        conn = get_connection()
        if not conn:
            logger.error(f"Не удалось получить соединение с БД для получения заказа {order_id}.")
            return None
        cursor = conn.cursor()
        cursor.execute("""
            SELECT id, user_id, total_price, discounted_price, status, created_at, promocode, savings
            FROM orders
            WHERE id = ?
        """, (order_id,))
        row = cursor.fetchone()
        conn.close()
        if row:
            return {
                'id': row[0],
                'user_id': row[1],
                'total_price': row[2],
                'discounted_price': row[3] if row[3] is not None else row[2],
                'status': row[4],
                'created_at': row[5],
                'promocode': row[6],
                'savings': row[7] or 0.0
            }
        return None
    except Exception as e:
        logger.error(f"Ошибка при получении заказа {order_id}: {e}", exc_info=True)
        return None


def get_all_orders_full() -> list:
    try:
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute("""
            SELECT * FROM orders 
            ORDER BY created_at DESC
        """)
        orders = cursor.fetchall()

        result = []
        for order in orders:
            cursor.execute("""
                SELECT * FROM order_items 
                WHERE order_id = ?
            """, (order['id'],))
            items = cursor.fetchall()

            items_list = []
            for item in items:
                try:
                    filled_data = json.loads(item['filled_data'])
                except (json.JSONDecodeError, TypeError):
                    filled_data = {}
                    logger.warning(f"Не удалось декодировать filled_data для позиции {item['id']}")

                items_list.append({
                    'id': item['id'],
                    'doc_id': item['doc_id'],
                    'doc_name': item['doc_name'],
                    'price': item['price'],
                    'filled_data': filled_data,
                    'pdf_path': None,
                    'docx_path': None,
                    'created_at': item['created_at']
                })

            result.append({
                'id': order['id'],
                'user_id': order['user_id'],
                'total_price': order['total_price'],
                'discounted_price': order['discounted_price'] or order['total_price'],
                'item_count': order['item_count'],
                'savings': order['savings'] or 0,
                'promocode': order['promocode'],
                'status': order['status'],
                'created_at': order['created_at'],
                'updated_at': order['updated_at'],
                'pdf_path': None,
                'docx_path': None,
                'payment_id': safe_get_row_value(order, 'payment_id'),
                'payment_data': safe_get_row_value(order, 'payment_data'),
                'items': items_list
            })

        conn.close()
        return result

    except Exception as e:
        logger.error(f"Ошибка при получении всех заказов: {e}", exc_info=True)
        return []


def get_recent_orders(limit: int = 10) -> list:
    try:
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute("""
            SELECT * FROM orders 
            ORDER BY created_at DESC
            LIMIT ?
        """, (limit,))
        orders = cursor.fetchall()

        result = []
        for order in orders:
            cursor.execute("""
                SELECT * FROM order_items 
                WHERE order_id = ?
            """, (order['id'],))
            items = cursor.fetchall()

            items_list = []
            for item in items:
                try:
                    filled_data = json.loads(item['filled_data'])
                except (json.JSONDecodeError, TypeError):
                    filled_data = {}
                    logger.warning(f"Не удалось декодировать filled_data для позиции {item['id']}")

                items_list.append({
                    'id': item['id'],
                    'doc_id': item['doc_id'],
                    'doc_name': item['doc_name'],
                    'price': item['price'],
                    'filled_data': filled_data,
                    'pdf_path': None,
                    'docx_path': None,
                    'created_at': item['created_at']
                })

            result.append({
                'id': order['id'],
                'user_id': order['user_id'],
                'total_price': order['total_price'],
                'discounted_price': order['discounted_price'] or order['total_price'],
                'item_count': order['item_count'],
                'savings': order['savings'] or 0,
                'promocode': order['promocode'],
                'status': order['status'],
                'created_at': order['created_at'],
                'updated_at': order['updated_at'],
                'pdf_path': None,
                'docx_path': None,
                'payment_id': safe_get_row_value(order, 'payment_id'),
                'payment_data': safe_get_row_value(order, 'payment_data'),
                'items': items_list
            })

        conn.close()
        return result

    except Exception as e:
        logger.error(f"Ошибка при получении недавних заказов: {e}", exc_info=True)
        return []


def get_user_orders(user_id: int) -> list:
    try:
        conn = get_connection()
        cursor = conn.cursor()

        cursor.execute("""
            SELECT * FROM orders 
            WHERE user_id = ?
            ORDER BY created_at DESC
        """, (user_id,))
        orders = cursor.fetchall()

        result = []
        for order in orders:
            cursor.execute("""
                SELECT * FROM order_items 
                WHERE order_id = ?
            """, (order['id'],))
            items = cursor.fetchall()

            items_list = []
            for item in items:
                try:
                    filled_data = json.loads(item['filled_data'])
                except (json.JSONDecodeError, TypeError):
                    filled_data = {}
                    logger.warning(f"Не удалось декодировать filled_data для позиции {item['id']}")

                items_list.append({
                    'id': item['id'],
                    'doc_id': item['doc_id'],
                    'doc_name': item['doc_name'],
                    'price': item['price'],
                    'filled_data': filled_data,
                    'pdf_path': None,
                    'docx_path': None,
                    'created_at': item['created_at']
                })

            result.append({
                'id': order['id'],
                'user_id': order['user_id'],
                'total_price': order['total_price'],
                'discounted_price': order['discounted_price'] or order['total_price'],
                'item_count': order['item_count'],
                'savings': order['savings'] or 0,
                'promocode': order['promocode'],
                'status': order['status'],
                'created_at': order['created_at'],
                'updated_at': order['updated_at'],
                'pdf_path': None,
                'docx_path': None,
                'payment_id': safe_get_row_value(order, 'payment_id'),
                'payment_data': safe_get_row_value(order, 'payment_data'),
                'items': items_list
            })

        conn.close()
        return result

    except Exception as e:
        logger.error(f"Ошибка при получении заказов пользователя: {e}", exc_info=True)
        return []


def get_order_by_id_full(order_id: int) -> Optional[dict]:
    try:
        conn = get_connection()
        cursor = conn.cursor()

        cursor.execute("""
            SELECT * FROM orders 
            WHERE id = ?
        """, (order_id,))
        order = cursor.fetchone()

        if not order:
            logger.warning(f"Заказ {order_id} не найден")
            conn.close()
            return None

        cursor.execute("""
            SELECT * FROM order_items 
            WHERE order_id = ?
        """, (order_id,))
        items = cursor.fetchall()

        items_list = []
        for item in items:
            try:
                filled_data = json.loads(item['filled_data'])
            except (json.JSONDecodeError, TypeError):
                filled_data = {}
                logger.warning(f"Не удалось декодировать filled_data для позиции {item['id']}")

            items_list.append({
                'id': item['id'],
                'doc_id': item['doc_id'],
                'doc_name': item['doc_name'],
                'price': item['price'],
                'filled_data': filled_data,
                'pdf_path': None,
                'docx_path': None,
                'created_at': item['created_at']
            })

        result = {
            'id': order['id'],
            'user_id': order['user_id'],
            'total_price': order['total_price'],
            'discounted_price': order['discounted_price'] or order['total_price'],
            'item_count': order['item_count'],
            'savings': order['savings'] or 0,
            'promocode': order['promocode'],
            'status': order['status'],
            'created_at': order['created_at'],
            'updated_at': order['updated_at'],
            'pdf_path': None,
            'docx_path': None,
            'payment_id': safe_get_row_value(order, 'payment_id'),
            'payment_data': safe_get_row_value(order, 'payment_data'),
            'items': items_list
        }

        conn.close()
        return result

    except Exception as e:
        logger.error(f"Ошибка при получении заказа по ID: {e}", exc_info=True)
        return None


def get_order_pdf_path(order_id: int) -> Optional[str]:
    logger.debug(f"get_order_pdf_path вызвана для заказа {order_id}, возвращаем None для совместимости")
    return None


def update_order_item_files(item_id: int, pdf_path: str = None, docx_path: str = None) -> bool:
    logger.debug(f"update_order_item_files вызвана для позиции {item_id}, игнорируем для совместимости")
    return True


def delete_order(order_id: int) -> bool:
    try:
        conn = get_connection()
        cursor = conn.cursor()

        cursor.execute("""
            DELETE FROM order_items 
            WHERE order_id = ?
        """, (order_id,))

        cursor.execute("""
            DELETE FROM orders 
            WHERE id = ?
        """, (order_id,))

        conn.commit()
        rows_affected = cursor.rowcount
        conn.close()

        if rows_affected > 0:
            logger.info(f"Заказ {order_id} удален успешно")
            return True
        else:
            logger.warning(f"Заказ {order_id} не найден для удаления")
            return False

    except Exception as e:
        logger.error(f"Ошибка при удалении заказа: {e}", exc_info=True)
        return False


def get_orders_stats() -> dict:
    try:
        conn = get_connection()
        cursor = conn.cursor()

        cursor.execute("SELECT COUNT(*) as total FROM orders")
        total_orders = cursor.fetchone()['total']

        cursor.execute("""
            SELECT status, COUNT(*) as count 
            FROM orders 
            GROUP BY status
        """)
        orders_by_status = {row['status']: row['count'] for row in cursor.fetchall()}

        cursor.execute("SELECT SUM(total_price) as total_revenue FROM orders WHERE status = 'paid'")
        total_revenue = cursor.fetchone()['total_revenue'] or 0

        conn.close()

        return {
            'total_orders': total_orders,
            'orders_by_status': orders_by_status,
            'total_revenue': total_revenue
        }

    except Exception as e:
        logger.error(f"Ошибка при получении статистики заказов: {e}", exc_info=True)
        return {
            'total_orders': 0,
            'orders_by_status': {},
            'total_revenue': 0
        }

def update_order_payment(order_id: int, payment_id: str, payment_data: dict = None) -> bool:
    try:
        conn = get_connection()
        cursor = conn.cursor()

        cursor.execute("""
            UPDATE orders 
            SET payment_id = ?, payment_data = ?, updated_at = CURRENT_TIMESTAMP
            WHERE id = ?
        """, (payment_id, json.dumps(payment_data, ensure_ascii=False) if payment_data else None, order_id))

        conn.commit()
        rows_affected = cursor.rowcount
        conn.close()

        if rows_affected > 0:
            logger.info(f"Данные платежа для заказа {order_id} обновлены")
            return True
        else:
            logger.warning(f"Заказ {order_id} не найден для обновления платежа")
            return False

    except Exception as e:
        logger.error(f"Ошибка при обновлении данных платежа: {e}", exc_info=True)
        return False


def get_order_items(order_id: int):
    try:
        conn = get_connection()
        cursor = conn.cursor()

        cursor.execute("""
            SELECT 
                id, order_id, doc_id, doc_name, price, 
                filled_data, created_at
            FROM order_items 
            WHERE order_id = ?
        """, (order_id,))

        items = cursor.fetchall()
        conn.close()

        return items

    except Exception as e:
        logger.error(f"Ошибка получения элементов заказа {order_id}: {e}")
        return []


def get_order_by_payment_id(payment_id: str) -> Optional[dict]:
    try:
        conn = get_connection()
        cursor = conn.cursor()

        cursor.execute("""
            SELECT id FROM orders 
            WHERE payment_id = ?
        """, (payment_id,))

        result = cursor.fetchone()
        conn.close()

        if result:
            return get_order_by_id_full(result['id'])
        return None

    except Exception as e:
        logger.error(f"Ошибка при получении заказа по payment_id: {e}", exc_info=True)
        return None
def update_order_status(order_id: int, status: str, pdf_path: str = None, docx_path: str = None) -> bool:
    #список статусов
    valid_statuses = ['created', 'pending', 'paid', 'processing', 'document_generated', 'generation_error', 'sent', 'delivered', 'cancelled']
    if status not in valid_statuses:
        logger.warning(f"Попытка установить недопустимый статус '{status}' для заказа {order_id}")
        return False

    try:
        conn = get_connection()
        cursor = conn.cursor()

        cursor.execute("""
            UPDATE orders 
            SET status = ?, updated_at = CURRENT_TIMESTAMP
            WHERE id = ?
        """, (status, order_id))

        conn.commit()
        rows_affected = cursor.rowcount
        conn.close()

        if rows_affected > 0:
            logger.info(f"Статус заказа {order_id} обновлен на '{status}'")
            if pdf_path or docx_path:
                logger.debug(f"Пути к файлам проигнорированы для совместимости: pdf={pdf_path}, docx={docx_path}")
            return True
        else:
            logger.warning(f"Заказ {order_id} не найден для обновления статуса")
            return False

    except Exception as e:
        logger.error(f"Ошибка при обновлении статуса заказа: {e}", exc_info=True)
        return False

def get_daily_stats():
    try:
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute("""
            SELECT COUNT(*), SUM(total_price), COUNT(DISTINCT user_id)
            FROM orders
            WHERE date(created_at) = date('now')
        """)
        orders_count, total_amount, unique_users = cursor.fetchone()

        cursor.execute("""
            SELECT COUNT(*)
            FROM orders
            WHERE date(created_at) = date('now') AND promocode IS NOT NULL
        """)
        promocodes_used = cursor.fetchone()[0] or 0

        cursor.execute("""
            SELECT COUNT(*)
            FROM order_items oi
            JOIN orders o ON oi.order_id = o.id
            WHERE date(o.created_at) = date('now')
        """)
        templates_used = cursor.fetchone()[0] or 0

        cursor.execute("""
            SELECT SUM(savings)
            FROM orders
            WHERE date(created_at) = date('now')
        """)
        total_savings = cursor.fetchone()[0] or 0

        conn.close()

        return {
            'orders_count': orders_count or 0,
            'total_amount': total_amount or 0,
            'unique_users': unique_users or 0,
            'promocodes_used': promocodes_used,
            'templates_used': templates_used,
            'total_savings': total_savings
        }
    except Exception as e:
        logger.error(f"Ошибка при получении ежедневной статистики: {e}", exc_info=True)
        return {
            'orders_count': 0,
            'total_amount': 0,
            'unique_users': 0,
            'promocodes_used': 0,
            'templates_used': 0,
            'total_savings': 0
        }

def get_monthly_stats():
    try:
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute("""
            SELECT COUNT(*), SUM(total_price), COUNT(DISTINCT user_id)
            FROM orders
            WHERE strftime('%Y-%m', created_at) = strftime('%Y-%m', 'now')
        """)
        orders_count, total_amount, unique_users = cursor.fetchone()

        cursor.execute("""
            SELECT COUNT(*)
            FROM orders
            WHERE strftime('%Y-%m', created_at) = strftime('%Y-%m', 'now') AND promocode IS NOT NULL
        """)
        promocodes_used = cursor.fetchone()[0] or 0
        cursor.execute("""
            SELECT COUNT(*)
            FROM order_items oi
            JOIN orders o ON oi.order_id = o.id
            WHERE strftime('%Y-%m', o.created_at) = strftime('%Y-%m', 'now')
        """)
        templates_used = cursor.fetchone()[0] or 0

        cursor.execute("""
            SELECT SUM(savings)
            FROM orders
            WHERE strftime('%Y-%m', created_at) = strftime('%Y-%m', 'now')
        """)
        total_savings = cursor.fetchone()[0] or 0

        conn.close()

        return {
            'orders_count': orders_count or 0,
            'total_amount': total_amount or 0,
            'unique_users': unique_users or 0,
            'promocodes_used': promocodes_used,
            'templates_used': templates_used,
            'total_savings': total_savings
        }
    except Exception as e:
        logger.error(f"Ошибка при получении ежемесячной статистики: {e}", exc_info=True)
        return {
            'orders_count': 0,
            'total_amount': 0,
            'unique_users': 0,
            'promocodes_used': 0,
            'templates_used': 0,
            'total_savings': 0
        }


def get_yearly_stats():
    try:
        conn = get_connection()
        cursor = conn.cursor()

        current_year = datetime.now().year
        previous_year = current_year - 1
        cursor.execute("""
            SELECT COUNT(*), SUM(total_price), COUNT(DISTINCT user_id)
            FROM orders
            WHERE strftime('%Y', created_at) = ?
        """, (str(current_year),))
        orders_count, total_amount, unique_users = cursor.fetchone()

        cursor.execute("""
            SELECT COUNT(*), SUM(total_price), COUNT(DISTINCT user_id)
            FROM orders
            WHERE strftime('%Y', created_at) = ?
        """, (str(previous_year),))
        prev_orders_count, prev_total_amount, prev_unique_users = cursor.fetchone()

        cursor.execute("""
            SELECT COUNT(*)
            FROM orders
            WHERE strftime('%Y', created_at) = ? AND promocode IS NOT NULL
        """, (str(current_year),))
        promocodes_used = cursor.fetchone()[0] or 0

        cursor.execute("""
            SELECT COUNT(*)
            FROM order_items oi
            JOIN orders o ON oi.order_id = o.id
            WHERE strftime('%Y', o.created_at) = ?
        """, (str(current_year),))
        templates_used = cursor.fetchone()[0] or 0

        cursor.execute("""
            SELECT SUM(savings)
            FROM orders
            WHERE strftime('%Y', created_at) = ?
        """, (str(current_year),))
        total_savings = cursor.fetchone()[0] or 0

        growth_orders = ((orders_count - prev_orders_count) / prev_orders_count * 100) if prev_orders_count else 100
        growth_revenue = ((total_amount - prev_total_amount) / prev_total_amount * 100) if prev_total_amount else 100

        conn.close()

        return {
            'orders_count': orders_count or 0,
            'total_amount': total_amount or 0,
            'unique_users': unique_users or 0,
            'promocodes_used': promocodes_used,
            'templates_used': templates_used,
            'total_savings': total_savings,
            'growth_orders': round(growth_orders, 1),
            'growth_revenue': round(growth_revenue, 1)
        }
    except Exception as e:
        logger.error(f"Ошибка при получении годовой статистики: {e}", exc_info=True)
        return {
            'orders_count': 0,
            'total_amount': 0,
            'unique_users': 0,
            'promocodes_used': 0,
            'templates_used': 0,
            'total_savings': 0,
            'growth_orders': 0,
            'growth_revenue': 0
        }
