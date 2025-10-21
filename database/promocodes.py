import logging
import sqlite3
import datetime
from config import config

logger = logging.getLogger('doc_bot.promocodes')
logger.info("database/promocodes.py ЗАГРУЖЕН УСПЕШНО")


def get_all_promocodes() -> list:
    try:
        conn = sqlite3.connect(config.DATABASE_PATH)
        cursor = conn.cursor()

        cursor.execute("""
            SELECT p.*, 
                   (SELECT COUNT(*) FROM promocode_usage WHERE promocode_id = p.id) as usage_count
            FROM promocodes p
            ORDER BY p.created_at DESC
        """)

        promocodes = cursor.fetchall()

        promocodes_list = []
        for promo in promocodes:
            promocodes_list.append({
                'id': promo[0],
                'code': promo[1],
                'discount': promo[2],
                'max_uses': promo[3],
                'used_count': promo[4],
                'expires_at': promo[5],
                'created_at': promo[6],
                'updated_at': promo[7],
                'usage_count': promo[8]
            })

        return promocodes_list

    except Exception as e:
        logger.error(f"Ошибка при получении списка промокодов: {e}", exc_info=True)
        return []
    finally:
        if conn:
            conn.close()


def create_promocode(code: str, discount: int, max_uses: int = 1, expires_at: datetime.datetime = None) -> dict:
    try:
        conn = sqlite3.connect(config.DATABASE_PATH)
        cursor = conn.cursor()
        cursor.execute("SELECT id FROM promocodes WHERE code = ?", (code,))
        existing = cursor.fetchone()

        if existing:
            logger.warning(f"Промокод с кодом {code} уже существует")
            return None
        cursor.execute("""
            INSERT INTO promocodes (
                code, discount, max_uses, used_count, expires_at
            ) VALUES (?, ?, ?, ?, ?)
        """, (code, discount, max_uses, 0, expires_at))

        conn.commit()

        cursor.execute("SELECT * FROM promocodes WHERE id = ?", (cursor.lastrowid,))
        promo = cursor.fetchone()

        return {
            'id': promo[0],
            'code': promo[1],
            'discount': promo[2],
            'max_uses': promo[3],
            'used_count': promo[4],
            'expires_at': promo[5],
            'created_at': promo[6],
            'updated_at': promo[7]
        }

    except Exception as e:
        logger.error(f"Ошибка при создании промокода: {e}", exc_info=True)
        return None
    finally:
        if conn:
            conn.close()


def update_promocode(promo_id: int, **kwargs) -> bool:
    try:
        conn = sqlite3.connect(config.DATABASE_PATH)
        cursor = conn.cursor()

        # Формируем запрос на обновление
        set_clause = []
        values = []

        if 'code' in kwargs:
            set_clause.append("code = ?")
            values.append(kwargs['code'])

        if 'discount' in kwargs:
            set_clause.append("discount = ?")
            values.append(kwargs['discount'])

        if 'max_uses' in kwargs:
            set_clause.append("max_uses = ?")
            values.append(kwargs['max_uses'])

        if 'expires_at' in kwargs:
            set_clause.append("expires_at = ?")
            values.append(kwargs['expires_at'])

        # Добавляем обновление времени
        set_clause.append("updated_at = CURRENT_TIMESTAMP")

        # Формируем финальный запрос
        query = f"UPDATE promocodes SET {', '.join(set_clause)} WHERE id = ?"
        values.append(promo_id)

        # Выполняем запрос
        cursor.execute(query, tuple(values))
        conn.commit()

        return cursor.rowcount > 0

    except Exception as e:
        logger.error(f"Ошибка при обновлении промокода: {e}", exc_info=True)
        return False
    finally:
        if conn:
            conn.close()


def check_promocode(code: str, user_id: int) -> dict:
    try:
        conn = sqlite3.connect(config.DATABASE_PATH)
        cursor = conn.cursor()

        # Получаем промокод
        cursor.execute("SELECT * FROM promocodes WHERE code = ?", (code,))
        promo = cursor.fetchone()

        if not promo:
            logger.warning(f"Промокод {code} не найден")
            return None

        promo_id = promo[0]
        discount = promo[2]
        max_uses = promo[3]
        used_count = promo[4]
        expires_at = promo[5]

        # Проверяем, не истек ли срок действия
        if expires_at:
            try:
                current_time = datetime.datetime.now()
                expires_at_dt = datetime.datetime.strptime(expires_at, "%Y-%m-%d %H:%M:%S")

                if current_time > expires_at_dt:
                    logger.warning(f"Промокод {code} истек")
                    return None
            except (ValueError, TypeError) as e:
                logger.error(f"Ошибка при сравнении даты промокода: {e}")
                return None
        if used_count >= max_uses:
            logger.warning(f"Достигнуто максимальное количество использований промокода {code}")
            return None
        if code != "FRIENDS100" and not code.startswith('1RUB'):
            cursor.execute("""
                SELECT id FROM promocode_usage 
                WHERE promocode_id = ? AND user_id = ?
            """, (promo_id, user_id))

            if cursor.fetchone():
                logger.warning(f"Пользователь {user_id} уже использовал промокод {code}")
                return None
        if code == "WELCOME20":
            cursor.execute("""
                SELECT id FROM orders 
                WHERE user_id = ? AND status IN ('paid', 'completed')
            """, (user_id,))

            if cursor.fetchone():
                logger.warning(f"Пользователь {user_id} уже совершал заказы, промокод WELCOME20 недоступен")
                return None

        return {
            'promo_id': promo_id,
            'code': code,
            'discount': discount,
            'user_id': user_id
        }

    except Exception as e:
        logger.error(f"Ошибка при проверке промокода: {e}", exc_info=True)
        return None
    finally:
        if conn:
            conn.close()


def apply_promocode(code: str, user_id: int, order_id: int) -> dict:
    try:
        conn = sqlite3.connect(config.DATABASE_PATH)
        cursor = conn.cursor()

        # Получаем промокод
        cursor.execute("SELECT * FROM promocodes WHERE code = ?", (code,))
        promo = cursor.fetchone()

        if not promo:
            logger.warning(f"Промокод {code} не найден")
            return None

        promo_id = promo[0]
        discount = promo[2]
        is_ruble_promo = code.startswith('1RUB')

        if not is_ruble_promo:
            cursor.execute("""
                SELECT id FROM promocode_usage 
                WHERE promocode_id = ? AND user_id = ?
            """, (promo_id, user_id))

            if cursor.fetchone():
                logger.warning(f"Пользователь {user_id} уже использовал промокод {code}")
                return None

        # Записываем использование
        cursor.execute("""
            INSERT INTO promocode_usage (promocode_id, user_id, order_id)
            VALUES (?, ?, ?)
        """, (promo_id, user_id, order_id))

        # Обновляем счетчик использований
        cursor.execute("""
            UPDATE promocodes 
            SET used_count = used_count + 1 
            WHERE id = ?
        """, (promo_id,))

        conn.commit()

        return {
            'promo_id': promo_id,
            'code': code,
            'discount': discount,
            'user_id': user_id,
            'order_id': order_id,
            'is_ruble_promo': is_ruble_promo  # Добавляем флаг
        }

    except Exception as e:
        logger.error(f"Ошибка при применении промокода: {e}", exc_info=True)
        return None
    finally:
        if conn:
            conn.close()


def get_promocode_usage(promo_id: int) -> list:
    try:
        conn = sqlite3.connect(config.DATABASE_PATH)
        cursor = conn.cursor()

        cursor.execute("""
            SELECT pu.*, u.username, u.first_name, u.last_name, o.total_price
            FROM promocode_usage pu
            JOIN users u ON pu.user_id = u.id
            JOIN orders o ON pu.order_id = o.id
            WHERE pu.promocode_id = ?
            ORDER BY pu.used_at DESC
        """, (promo_id,))

        usage_records = cursor.fetchall()

        # Формируем список использований
        usage_list = []
        for record in usage_records:
            usage_list.append({
                'id': record[0],
                'promocode_id': record[1],
                'user_id': record[2],
                'order_id': record[3],
                'used_at': record[4],
                'username': record[5],
                'first_name': record[6],
                'last_name': record[7],
                'order_total': record[8]
            })

        return usage_list

    except Exception as e:
        logger.error(f"Ошибка при получении информации об использовании промокода: {e}", exc_info=True)
        return []
    finally:
        if conn:
            conn.close()


def initialize_default_promocodes():
    try:
        create_promocode(
            code="FRIENDS100",
            discount=100,
            max_uses=1000,
            expires_at=None
        )
        create_promocode(
            code="WELCOME20",
            discount=20,
            max_uses=10,
            expires_at=None
        )

        logger.info("Базовые промокоды инициализированы")
    except Exception as e:
        logger.error(f"Ошибка при инициализации базовых промокодов: {e}", exc_info=True)


def create_seasonal_promocode():
    try:
        months = {
            1: "JAN", 2: "FEB", 3: "MAR", 4: "APR", 5: "MAY", 6: "JUN",
            7: "JUL", 8: "AUG", 9: "SEP", 10: "OCT", 11: "NOV", 12: "DEC"
        }

        current_date = datetime.datetime.now()
        current_month = current_date.month
        current_year = current_date.year

        month_abbr = months[current_month]
        code = f"{month_abbr}10"
        next_month = current_month + 1
        next_year = current_year
        if next_month > 12:
            next_month = 1
            next_year += 1

        expires_at = datetime.datetime(next_year, next_month, 1).strftime("%Y-%m-%d %H:%M:%S")
        conn = sqlite3.connect(config.DATABASE_PATH)
        cursor = conn.cursor()
        cursor.execute("SELECT id FROM promocodes WHERE code = ?", (code,))
        existing = cursor.fetchone()
        conn.close()

        if existing:
            logger.info(f"Сезонный промокод {code} уже существует")
            return None

        # Создаем промокод
        promocode = create_promocode(
            code=code,
            discount=10,
            max_uses=100,
            expires_at=expires_at
        )

        if promocode:
            logger.info(f"Создан сезонный промокод: {code}")
            return promocode
        else:
            logger.warning(f"Не удалось создать сезонный промокод: {code}")
            return None

    except Exception as e:
        logger.error(f"Ошибка при создании сезонного промокода: {e}", exc_info=True)
        return None

def get_promocode_by_code(code: str) -> dict:
    try:
        conn = sqlite3.connect(config.DATABASE_PATH)
        cursor = conn.cursor()
        cursor.execute("""
            SELECT p.*, 
                   (SELECT COUNT(*) FROM promocode_usage WHERE promocode_id = p.id) as usage_count,
                   (SELECT SUM(o.total_price) 
                    FROM promocode_usage pu
                    JOIN orders o ON pu.order_id = o.id
                    WHERE pu.promocode_id = p.id) as total_revenue
            FROM promocodes p
            WHERE p.code = ?
        """, (code,))

        promo = cursor.fetchone()

        if not promo:
            logger.warning(f"Промокод {code} не найден в базе данных")
            return None
        promo_info = {
            'id': promo[0],
            'code': promo[1],
            'discount': promo[2],
            'max_uses': promo[3],
            'used_count': promo[4],
            'expires_at': promo[5],
            'created_at': promo[6],
            'updated_at': promo[7],
            'usage_count': promo[8],
            'total_revenue': promo[9] or 0,
            'available_uses': max(0, promo[3] - promo[4]),
            'status': 'активен' if (promo[3] > promo[4] and (
                    not promo[5] or datetime.datetime.now() < datetime.datetime.strptime(promo[5],
                                                                                         "%Y-%m-%d %H:%M:%S"))) else 'неактивен'
        }

        cursor.execute("""
            SELECT u.id, u.username, u.first_name, u.last_name, COUNT(pu.id) as usage_count
            FROM promocode_usage pu
            JOIN users u ON pu.user_id = u.id
            JOIN promocodes p ON pu.promocode_id = p.id
            WHERE p.code = ?
            GROUP BY u.id
            ORDER BY usage_count DESC
            LIMIT 5
        """, (code,))

        top_users = cursor.fetchall()
        promo_info['top_users'] = [{
            'user_id': user[0],
            'username': user[1] or 'не указан',
            'name': f"{user[2] or ''} {user[3] or ''}".strip() or 'Аноним',
            'usage_count': user[4]
        } for user in top_users]

        cursor.execute("""
            SELECT pu.used_at, u.username, o.total_price
            FROM promocode_usage pu
            JOIN users u ON pu.user_id = u.id
            JOIN orders o ON pu.order_id = o.id
            JOIN promocodes p ON pu.promocode_id = p.id
            WHERE p.code = ?
            ORDER BY pu.used_at DESC
            LIMIT 5
        """, (code,))

        recent_uses = cursor.fetchall()
        promo_info['recent_uses'] = [{
            'date': use[0],
            'username': use[1] or 'не указан',
            'order_value': use[2]
        } for use in recent_uses]
        if promo_info['total_revenue'] > 0:
            promo_info['total_savings'] = promo_info['total_revenue'] * promo_info['discount'] / 100
        else:
            promo_info['total_savings'] = 0

        logger.info(f"Получена детальная информация о промокоде {code}")
        return promo_info

    except Exception as e:
        logger.error(f"Ошибка при получении информации о промокоде {code}: {e}", exc_info=True)
        return None
    finally:
        if 'conn' in locals() and conn:
            conn.close()


def add_referral(referrer_id: int, referred_id: int) -> bool:
    try:
        conn = sqlite3.connect(config.DATABASE_PATH)
        cursor = conn.cursor()

        cursor.execute("""
            INSERT OR IGNORE INTO referrals (referrer_id, referred_id)
            VALUES (?, ?)
        """, (referrer_id, referred_id))

        conn.commit()
        return cursor.rowcount > 0
    except Exception as e:
        logger.error(f"Ошибка при добавлении реферала: {e}", exc_info=True)
        return False
    finally:
        if conn:
            conn.close()


def get_referral_count(user_id: int) -> int:
    try:
        conn = sqlite3.connect(config.DATABASE_PATH)
        cursor = conn.cursor()

        cursor.execute("""
            SELECT COUNT(*) FROM referrals 
            WHERE referrer_id = ?
        """, (user_id,))
        count = cursor.fetchone()[0]
        return count

    except Exception as e:
        logger.error(f"Ошибка при получении количества рефералов: {e}", exc_info=True)
        return 0
    finally:
        if conn:
            conn.close()


def create_ruble_promocode(user_id: int) -> str:
    try:
        code = f"1RUB{user_id % 10000:04d}"
        create_promocode(
            code=code,
            discount=100,
            max_uses=1,
            expires_at=None
        )

        return code

    except Exception as e:
        logger.error(f"Ошибка при создании рублевого промокода: {e}", exc_info=True)
        return None


def get_user_ruble_promocodes(user_id: int) -> list:
    try:
        conn = sqlite3.connect(config.DATABASE_PATH)
        cursor = conn.cursor()

        cursor.execute("""
            SELECT p.*, 
                   (SELECT COUNT(*) FROM promocode_usage WHERE promocode_id = p.id) as usage_count
            FROM promocodes p
            WHERE p.code LIKE ? AND p.used_count = 0
        """, (f"1RUB{user_id % 10000:04d}",))

        promocodes = cursor.fetchall()
        promocodes_list = []
        for promo in promocodes:
            promocodes_list.append({
                'id': promo[0],
                'code': promo[1],
                'discount': promo[2],
                'max_uses': promo[3],
                'used_count': promo[4],
                'expires_at': promo[5],
                'created_at': promo[6],
                'updated_at': promo[7],
                'usage_count': promo[8]
            })

        return promocodes_list

    except Exception as e:
        logger.error(f"Ошибка при получении рублевых промокодов пользователя: {e}", exc_info=True)
        return []
    finally:
        if conn:
            conn.close()