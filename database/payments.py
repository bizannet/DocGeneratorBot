import sqlite3
import logging
from datetime import datetime
from config import config

logger = logging.getLogger('doc_bot.db.payments')

def get_connection():
    try:
        db_path = config.DATABASE_PATH
        db_path.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(str(db_path))
        conn.row_factory = sqlite3.Row
        logger.debug(f"Подключение к БД установлено: {db_path}")
        return conn
    except Exception as e:
        logger.error(f"Ошибка подключения к базе данных: {e}")
        raise

def create_payment(user_id: int, order_id: int, amount: float, payment_system: str, status: str = 'pending'):
    try:
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute('''
            INSERT INTO payments (user_id, order_id, amount, payment_system, status, created_at)
            VALUES (?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
        ''', (user_id, order_id, amount, payment_system, status))
        payment_id = cursor.lastrowid
        conn.commit()
        conn.close()
        logger.info(f"Платеж {payment_id} для пользователя {user_id} создан")
        return payment_id
    except Exception as e:
        logger.error(f"Ошибка создания платежа для пользователя {user_id}: {e}", exc_info=True)
        return None

def update_payment_status(payment_id: int, status: str):
    try:
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute('''
            UPDATE payments
            SET status = ?, updated_at = CURRENT_TIMESTAMP
            WHERE id = ?
        ''', (status, payment_id))
        conn.commit()
        conn.close()
        logger.info(f"Статус платежа {payment_id} обновлен на {status}")
        return True
    except Exception as e:
        logger.error(f"Ошибка обновления статуса платежа {payment_id}: {e}", exc_info=True)
        return False

def get_payment_by_id(payment_id: int):
    try:
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute('''
            SELECT * FROM payments
            WHERE id = ?
        ''', (payment_id,))
        result = cursor.fetchone()
        conn.close()
        if result:
            columns = [description[0] for description in cursor.description]
            return dict(zip(columns, result))
        return None
    except Exception as e:
        logger.error(f"Ошибка получения платежа по ID {payment_id}: {e}", exc_info=True)
        return None

def get_payments_by_user(user_id: int):
    try:
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute('''
            SELECT * FROM payments
            WHERE user_id = ?
            ORDER BY created_at DESC
        ''', (user_id,))
        results = cursor.fetchall()
        conn.close()
        if results:
            columns = [description[0] for description in cursor.description]
            return [dict(zip(columns, row)) for row in results]
        return []
    except Exception as e:
        logger.error(f"Ошибка получения платежей пользователя {user_id}: {e}", exc_info=True)
        return []