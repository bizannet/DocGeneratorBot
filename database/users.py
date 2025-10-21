import logging
import sqlite3
import json
from datetime import datetime, timedelta
from config import config

logger = logging.getLogger('doc_bot.users')
logger.info("database/users.py ЗАГРУЖЕН УСПЕШНО")

def get_or_create_user(user_id: str, username: str, first_name: str, last_name: str, language_code: str, referrer_id: int = None) -> int:
    try:
        conn = sqlite3.connect(config.DATABASE_PATH)
        cursor = conn.cursor()

        # Проверяем, существует ли пользователь
        cursor.execute("SELECT id FROM users WHERE id = ?", (user_id,))
        existing_user = cursor.fetchone()

        if existing_user:
            # Обновляем данные пользователя
            cursor.execute("""
                UPDATE users SET 
                    username = ?, 
                    first_name = ?, 
                    last_name = ?, 
                    language_code = ?
                WHERE id = ?
            """, (username, first_name, last_name, language_code, user_id))
            conn.commit()
            return int(user_id)
        else:
            # Создаем нового пользователя
            cursor.execute("""
                INSERT INTO users (
                    id, username, first_name, last_name, language_code, referrer_id
                ) VALUES (?, ?, ?, ?, ?, ?)
            """, (user_id, username, first_name, last_name, language_code, referrer_id))

            conn.commit()

            # Если есть реферер, начисляем ему баллы за приглашение
            if referrer_id:
                add_partner_points(
                    referrer_id,
                    10.0,
                    None,
                    "Приглашение нового пользователя"
                )

            return cursor.lastrowid

    except Exception as e:
        logger.error(f"Ошибка при получении/создании пользователя: {e}", exc_info=True)
        return None
    finally:
        if conn:
            conn.close()


def get_user_by_id(user_id: int) -> dict:
    try:
        conn = sqlite3.connect(config.DATABASE_PATH)
        cursor = conn.cursor()

        cursor.execute("SELECT * FROM users WHERE id = ?", (user_id,))
        user = cursor.fetchone()

        if not user:
            return None

        # Получаем количество приглашенных пользователей
        cursor.execute("SELECT COUNT(*) FROM users WHERE referrer_id = ?", (user_id,))
        referrals_count = cursor.fetchone()[0]

        # Получаем общее количество баллов
        cursor.execute("SELECT SUM(points) FROM partner_points WHERE user_id = ?", (user_id,))
        total_points = cursor.fetchone()[0] or 0.0

        # Получаем доступные баллы (не использованные)
        cursor.execute("""
            SELECT COALESCE(SUM(points), 0) - COALESCE((
                SELECT SUM(points) FROM partner_points 
                WHERE user_id = ? AND points < 0
            ), 0) 
            FROM partner_points 
            WHERE user_id = ? AND points > 0
        """, (user_id, user_id))
        available_points = cursor.fetchone()[0] or 0.0

        # Получаем количество отзывов
        review_count = get_user_reviews_count(user_id)

        # Формируем ответ
        user_data = {
            'id': user[0],
            'username': user[1],
            'first_name': user[2],
            'last_name': user[3],
            'language_code': user[4],
            'registered_at': user[5],
            'referrer_id': user[6],
            'partner_points': user[7],
            'is_subscribed': user[8],
            'invited_count': referrals_count,
            'total_points': total_points,
            'available_points': available_points,
            'review_count': review_count
        }

        return user_data

    except Exception as e:
        logger.error(f"Ошибка при получении пользователя по ID: {e}", exc_info=True)
        return None
    finally:
        if conn:
            conn.close()


def get_user_balance(user_id: int) -> float:

    try:
        conn = sqlite3.connect(config.DATABASE_PATH)
        cursor = conn.cursor()

        cursor.execute("""
            SELECT balance FROM users WHERE id = ?
        """, (user_id,))

        result = cursor.fetchone()

        if result:
            return float(result[0]) if result[0] else 0.0
        else:
            return 0.0

    except Exception as e:
        logger.error(f"Ошибка получения баланса пользователя {user_id}: {e}")
        return 0.0
    finally:
        if conn:
            conn.close()


def update_user_balance(user_id: int, new_balance: float) -> bool:
    try:
        conn = sqlite3.connect(config.DATABASE_PATH)
        cursor = conn.cursor()

        cursor.execute("""
            UPDATE users SET balance = ? WHERE id = ?
        """, (new_balance, user_id))

        conn.commit()
        logger.info(f"Баланс пользователя {user_id} обновлен на {new_balance}")
        return True

    except Exception as e:
        logger.error(f"Ошибка обновления баланса пользователя {user_id}: {e}")
        return False
    finally:
        if conn:
            conn.close()

def get_all_users() -> list:
    try:
        conn = sqlite3.connect(config.DATABASE_PATH)
        cursor = conn.cursor()

        cursor.execute("SELECT * FROM users ORDER BY registered_at DESC")
        users = cursor.fetchall()

        # Формируем список пользователей
        users_list = []
        for user in users:
            # Получаем количество приглашенных
            cursor.execute("SELECT COUNT(*) FROM users WHERE referrer_id = ?", (user[0],))
            referrals_count = cursor.fetchone()[0]

            # Получаем общее количество баллов
            cursor.execute("SELECT SUM(points) FROM partner_points WHERE user_id = ?", (user[0],))
            total_points = cursor.fetchone()[0] or 0.0

            # Получаем количество отзывов
            review_count = get_user_reviews_count(user[0])

            users_list.append({
                'id': user[0],
                'username': user[1],
                'first_name': user[2],
                'last_name': user[3],
                'language_code': user[4],
                'registered_at': user[5],
                'referrer_id': user[6],
                'partner_points': user[7],
                'is_subscribed': user[8],
                'invited_count': referrals_count,
                'total_points': total_points,
                'review_count': review_count
            })

        return users_list

    except Exception as e:
        logger.error(f"Ошибка при получении списка пользователей: {e}", exc_info=True)
        return []
    finally:
        if conn:
            conn.close()


def get_partner_stats(user_id: int) -> dict:
    try:
        conn = sqlite3.connect(config.DATABASE_PATH)
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM users WHERE referrer_id = ?", (user_id,))
        invited = cursor.fetchone()[0]
        cursor.execute("SELECT SUM(points) FROM partner_points WHERE user_id = ?", (user_id,))
        total_points = cursor.fetchone()[0] or 0.0
        cursor.execute("""
            SELECT COALESCE(SUM(points), 0) - COALESCE((
                SELECT SUM(points) FROM partner_points 
                WHERE user_id = ? AND points < 0
            ), 0) 
            FROM partner_points 
            WHERE user_id = ? AND points > 0
        """, (user_id, user_id))
        available_points = cursor.fetchone()[0] or 0.0

        return {
            'invited': invited,
            'total_points': round(total_points, 2),
            'available_points': round(available_points, 2),
            'user_id': user_id
        }
    except Exception as e:
        logger.error(f"Ошибка при получении статистики партнера: {e}", exc_info=True)
        return {
            'invited': 0,
            'total_points': 0.0,
            'available_points': 0.0,
            'user_id': user_id
        }
    finally:
        if conn:
            conn.close()


def use_partner_points(user_id: int, points: float, order_id: int, description: str = None) -> bool:
    try:
        conn = sqlite3.connect(config.DATABASE_PATH)
        cursor = conn.cursor()
        stats = get_partner_stats(user_id)
        if stats['available_points'] < points:
            return False
        cursor.execute("""
            INSERT INTO partner_points (user_id, points, order_id, description)
            VALUES (?, ?, ?, ?)
        """, (user_id, -points, order_id, description or f"Списание {points} баллов"))

        conn.commit()
        return True

    except Exception as e:
        logger.error(f"Ошибка при списании партнерских баллов: {e}", exc_info=True)
        return False
    finally:
        if conn:
            conn.close()


def add_partner_points(user_id: int, points: float, order_id: int, description: str = None) -> bool:
    try:
        conn = sqlite3.connect(config.DATABASE_PATH)
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO partner_points (user_id, points, order_id, description)
            VALUES (?, ?, ?, ?)
        """, (user_id, points, order_id, description or f"Начисление {points} баллов"))

        conn.commit()
        return True

    except Exception as e:
        logger.error(f"Ошибка при начислении партнерских баллов: {e}", exc_info=True)
        return False
    finally:
        if conn:
            conn.close()


def get_user_referrals(user_id: int) -> list:
    try:
        conn = sqlite3.connect(config.DATABASE_PATH)
        cursor = conn.cursor()

        cursor.execute("""
            SELECT * FROM users 
            WHERE referrer_id = ? 
            ORDER BY registered_at DESC
        """, (user_id,))

        referrals = cursor.fetchall()
        referrals_list = []
        for referral in referrals:
            referrals_list.append({
                'id': referral[0],
                'username': referral[1],
                'first_name': referral[2],
                'last_name': referral[3],
                'language_code': referral[4],
                'registered_at': referral[5]
            })

        return referrals_list

    except Exception as e:
        logger.error(f"Ошибка при получении рефералов: {e}", exc_info=True)
        return []
    finally:
        if conn:
            conn.close()


def get_referral_link(user_id: int) -> str:
    return f"https://t.me/{config.BOT_USERNAME}?start=ref{user_id}"


def get_referrer_id(user_id: int) -> int:
    try:
        conn = sqlite3.connect(config.DATABASE_PATH)
        cursor = conn.cursor()

        cursor.execute("SELECT referrer_id FROM users WHERE id = ?", (user_id,))
        referrer_id = cursor.fetchone()

        if referrer_id and referrer_id[0]:
            return referrer_id[0]
        return None

    except Exception as e:
        logger.error(f"Ошибка при получении ID пригласившего пользователя: {e}", exc_info=True)
        return None
    finally:
        if conn:
            conn.close()


def add_news_subscriber(user_id: int) -> bool:
    try:
        conn = sqlite3.connect(config.DATABASE_PATH)
        cursor = conn.cursor()

        # Проверяем, существует ли подписка
        cursor.execute("SELECT user_id FROM news_subscribers WHERE user_id = ?", (user_id,))
        existing = cursor.fetchone()

        if existing:
            # Обновляем подписку
            cursor.execute("""
                UPDATE news_subscribers 
                SET subscribed_at = CURRENT_TIMESTAMP 
                WHERE user_id = ?
            """, (user_id,))
        else:
            # Добавляем новую подписку
            cursor.execute("""
                INSERT INTO news_subscribers (user_id) 
                VALUES (?)
            """, (user_id,))

        # Обновляем пользователя
        cursor.execute("""
            UPDATE users 
            SET is_subscribed = 1 
            WHERE id = ?
        """, (user_id,))

        conn.commit()
        return True

    except Exception as e:
        logger.error(f"Ошибка при добавлении подписчика: {e}", exc_info=True)
        return False
    finally:
        if conn:
            conn.close()


def remove_news_subscriber(user_id: int) -> bool:
    try:
        conn = sqlite3.connect(config.DATABASE_PATH)
        cursor = conn.cursor()

        # Удаляем из таблицы подписчиков
        cursor.execute("DELETE FROM news_subscribers WHERE user_id = ?", (user_id,))

        # Обновляем пользователя
        cursor.execute("""
            UPDATE users 
            SET is_subscribed = 0 
            WHERE id = ?
        """, (user_id,))

        conn.commit()
        return True

    except Exception as e:
        logger.error(f"Ошибка при удалении подписчика: {e}", exc_info=True)
        return False
    finally:
        if conn:
            conn.close()


def get_news_subscribers() -> list:
    try:
        conn = sqlite3.connect(config.DATABASE_PATH)
        cursor = conn.cursor()

        cursor.execute("SELECT user_id FROM news_subscribers")
        subscribers = cursor.fetchall()

        return [subscriber[0] for subscriber in subscribers]

    except Exception as e:
        logger.error(f"Ошибка при получении списка подписчиков: {e}", exc_info=True)
        return []
    finally:
        if conn:
            conn.close()


def get_new_users_count(days: int = 7) -> int:
    try:
        conn = sqlite3.connect(config.DATABASE_PATH)
        cursor = conn.cursor()

        # Вычисляем дату начала периода
        period_start = datetime.now() - timedelta(days=days)
        period_start_str = period_start.strftime("%Y-%m-%d %H:%M:%S")

        # Получаем количество новых пользователей
        cursor.execute("""
            SELECT COUNT(*) 
            FROM users 
            WHERE registered_at >= ?
        """, (period_start_str,))

        count = cursor.fetchone()[0]

        return count

    except Exception as e:
        logger.error(f"Ошибка при получении количества новых пользователей: {e}", exc_info=True)
        return 0
    finally:
        if conn:
            conn.close()

def get_user_reviews_count(user_id: int) -> int:
    return 0

def save_user_data(user_id: int, template_name: str, filled_data: dict) -> bool:
    try:
        conn = sqlite3.connect(config.DATABASE_PATH)
        cursor = conn.cursor()

        # Проверяем, существует ли уже запись
        cursor.execute("""
            SELECT id FROM user_data 
            WHERE user_id = ? AND template_name = ?
        """, (user_id, template_name))

        existing = cursor.fetchone()

        if existing:
            # Обновляем существующие данные
            cursor.execute("""
                UPDATE user_data 
                SET filled_data = ?, updated_at = CURRENT_TIMESTAMP 
                WHERE user_id = ? AND template_name = ?
            """, (json.dumps(filled_data), user_id, template_name))
        else:
            # Добавляем новые данные
            cursor.execute("""
                INSERT INTO user_data (user_id, template_name, filled_data)
                VALUES (?, ?, ?)
            """, (user_id, template_name, json.dumps(filled_data)))

        conn.commit()
        return True

    except Exception as e:
        logger.error(f"Ошибка при сохранении данных пользователя: {e}", exc_info=True)
        return False
    finally:
        if conn:
            conn.close()


def get_user_data(user_id: int, template_name: str = None) -> dict:
    try:
        conn = sqlite3.connect(config.DATABASE_PATH)
        cursor = conn.cursor()

        if template_name:
            # Получаем данные для конкретного шаблона
            cursor.execute("""
                SELECT * FROM user_data 
                WHERE user_id = ? AND template_name = ?
                ORDER BY updated_at DESC
                LIMIT 1
            """, (user_id, template_name))
        else:
            # Получаем все данные пользователя
            cursor.execute("""
                SELECT * FROM user_data 
                WHERE user_id = ?
                ORDER BY updated_at DESC
            """, (user_id,))

        data = cursor.fetchone()

        if not data:
            return None

        # Возвращаем данные в формате словаря
        return {
            'id': data[0],
            'user_id': data[1],
            'template_name': data[2],
            'filled_data': json.loads(data[3]) if isinstance(data[3], str) else data[3],
            'created_at': data[4],
            'updated_at': data[5]
        }

    except Exception as e:
        logger.error(f"Ошибка при получении данных пользователя: {e}", exc_info=True)
        return None
    finally:
        if conn:
            conn.close()