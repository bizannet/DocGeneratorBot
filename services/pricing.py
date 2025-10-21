import logging
import random
import string
import re
from datetime import datetime, timedelta
from database import get_connection

logger = logging.getLogger('doc_bot.pricing')

def get_template_price():
    return get_price_from_db('template')

def get_autogeneration_price():
    return get_price_from_db('autogen')

def get_price_from_db(service_type: str) -> float:
    conn = get_connection()
    if not conn:
        logger.error("Не удалось получить соединение с БД для получения цены.")
        return 0.0
    cursor = conn.cursor()
    try:
        cursor.execute("SELECT price FROM prices WHERE service_type = ?", (service_type,))
        result = cursor.fetchone()
        if result:
            return float(result[0])
        else:
            logger.warning(f"Цена для типа услуги '{service_type}' не найдена в БД. Возвращено 0.")
            return 0.0
    except Exception as e:
        logger.error(f"Ошибка при получении цены для '{service_type}' из БД: {e}", exc_info=True)
        return 0
    finally:
        conn.close()

def update_price_in_db(service_type: str, new_price: float):
    if service_type not in ['template', 'autogen']:
        logger.error(f"Неподдерживаемый тип услуги для обновления цены: {service_type}")
        return False

    conn = get_connection()
    if not conn:
        logger.error("Не удалось получить соединение с БД для обновления цены.")
        return False
    cursor = conn.cursor()
    try:
        cursor.execute("""
            INSERT OR REPLACE INTO prices (service_type, price)
            VALUES (?, ?)
        """, (service_type, new_price))
        conn.commit()
        logger.info(f"Цена для '{service_type}' обновлена в БД на {new_price}.")
        return True
    except Exception as e:
        logger.error(f"Ошибка при обновлении цены для '{service_type}' в БД: {e}", exc_info=True)
        return False
    finally:
        conn.close()

MONTHLY_PROMO_PREFIX = "FEEDBACK"

def get_price_for_type(price_type: str) -> float:
    if price_type == 'template':
        return float(get_template_price())
    elif price_type == 'autogen':
        return float(get_autogeneration_price())
    else:
        logger.warning(f"Неизвестный тип цены: {price_type}. Используем цену автогенерации.")
        return float(get_autogeneration_price())

def generate_promo_code(length=8):
    """Генерирует случайный промокод"""
    return ''.join(random.choice("ABCDEFGHJKLMNPQRSTUVWXYZ23456789") for _ in range(length))


def get_current_month_promo():
    """Возвращает промокод текущего месяца"""
    current_date = datetime.now()
    return f"{MONTHLY_PROMO_PREFIX}{current_date.year}{current_date.month:02d}"


def get_next_month_promo():
    """Возвращает промокод следующего месяца"""
    next_month = datetime.now().replace(day=28) + timedelta(days=4)
    return f"{MONTHLY_PROMO_PREFIX}{next_month.year}{next_month.month:02d}"


def is_valid_promo(promo_code: str) -> bool:
    """Проверяет валидность промокода"""
    if not re.match(r'^FEEDBACK\d{6}$', promo_code):
        return False
    try:
        promo_year = int(promo_code[8:12])
        promo_month = int(promo_code[12:14])
    except (ValueError, IndexError):
        return False
    if promo_month < 1 or promo_month > 12:
        return False
    promo_date = datetime(promo_year, promo_month, 1)
    current_date = datetime.now()
    max_valid_date = datetime(current_date.year, current_date.month, 1) + timedelta(days=37)
    return promo_date <= max_valid_date


def calculate_total_price(items: list, promo_code: str = None, user_id: int = None) -> dict:
    if not items:
        return {
            'original_price': 0.0,
            'discounted_price': 0.0,
            'savings': 0.0,
            'discount_percent': 0.0,
            'applied_promo': None
        }

    # Рассчитываем оригинальную стоимость
    original_price = sum(item.get('price', 0) for item in items)

    # Применяем промокоды
    discounted_price = original_price
    applied_promo = None
    discount_percent = 0.0

    if promo_code:
        promo_code = promo_code.strip().upper()
        # Проверяем валидность промокода
        is_valid, message = validate_promo_code(promo_code, user_id, items)
        if is_valid:
            # Ленивый импорт для избежания циклических импортов
            from database.promocodes import get_promocode_by_code

            # Получаем информацию о промокоде
            promo = get_promocode_by_code(promo_code)
            if promo:
                if promo['discount_type'] == 'percent':
                    discount = original_price * (promo['discount'] / 100)
                    discounted_price = max(0, original_price - discount)
                    discount_percent = promo['discount']
                elif promo['discount_type'] == 'fixed':
                    discount = min(promo['discount'], original_price)
                    discounted_price = max(0, original_price - discount)
                    discount_percent = (discount / original_price * 100) if original_price > 0 else 0

                applied_promo = {
                    'code': promo_code,
                    'type': promo['discount_type'],
                    'value': promo['discount']
                }

    savings = original_price - discounted_price
    discounted_price = int(discounted_price)

    return {
        'original_price': round(original_price, 2),
        'discounted_price': round(discounted_price, 2),
        'savings': round(savings, 2),
        'discount_percent': round(discount_percent, 2),
        'applied_promo': applied_promo
    }

def get_simple_total_price(items: list, promo_code: str = None, user_id: int = None) -> float:
    pricing_info = calculate_total_price(items, promo_code, user_id)
    return pricing_info['discounted_price']


def get_price_per_document(items: list, promo_code: str = None, user_id: int = None) -> float:
    pricing_info = calculate_total_price(items, promo_code, user_id)
    item_count = len(items)
    return pricing_info['discounted_price'] / item_count if item_count > 0 else 0.0


def get_savings(items: list, promo_code: str = None, user_id: int = None) -> float:
    pricing_info = calculate_total_price(items, promo_code, user_id)
    return pricing_info['savings']


def is_promocode_valid(promocode_code: str, user_id: int = None) -> tuple:
    try:
        from database.promocodes import get_promocode_by_code
        promo = get_promocode_by_code(promocode_code)
        if not promo:
            logger.warning(f"Промокод {promocode_code} не найден")
            return False, "Промокод не существует"

        promo_id = promo['id']
        discount = promo['discount']
        max_uses = promo['max_uses']
        used_count = promo['used_count']
        expires_at = promo['expires_at']
        if expires_at:
            try:
                current_time = datetime.now()
                expires_at_dt = datetime.strptime(expires_at, "%Y-%m-%d %H:%M:%S")

                if current_time > expires_at_dt:
                    logger.warning(f"Промокод {promocode_code} истек")
                    return False, "Промокод истек"
            except (ValueError, TypeError) as e:
                logger.error(f"Ошибка при сравнении даты промокода: {e}")
                return False, "Ошибка проверки срока действия промокода"
        if used_count >= max_uses:
            logger.warning(f"Достигнуто максимальное количество использований промокода {promocode_code}")
            return False, "Достигнуто максимальное количество использований промокода"
        if user_id:
            from database.promocodes import has_user_used_promocode
            if has_user_used_promocode(promo_id, user_id):
                logger.warning(f"Пользователь {user_id} уже использовал промокод {promocode_code}")
                return False, "Вы уже использовали этот промокод"

        if promocode_code == "WELCOME20":
            from database.orders import get_user_orders
            orders = get_user_orders(user_id)
            if orders:
                logger.warning(f"Пользователь {user_id} уже совершал заказы, промокод WELCOME20 недоступен")
                return False, "Промокод WELCOME20 доступен только для новых пользователей"

        return True, "Промокод валиден"

    except Exception as e:
        logger.error(f"Ошибка при проверке валидности промокода: {e}", exc_info=True)
        return False, "Ошибка проверки промокода"


def validate_promo_code(promo_code: str, user_id: int, items: list) -> tuple:
    if not promo_code:
        return False, "Промокод не указан"

    promo_code = promo_code.strip().upper()
    if not re.match(r'^[A-Z0-9]{4,15}$', promo_code):
        return False, "Неверный формат промокода"
    from database.promocodes import get_promocode_by_code
    promo = get_promocode_by_code(promo_code)
    if not promo:
        return False, "Промокод не существует"
    is_valid, message = is_promocode_valid(promo_code, user_id)
    if not is_valid:
        return False, message

    return True, "Промокод успешно применен"


def generate_monthly_promo_code() -> str:
    current_date = datetime.now()
    return f"{MONTHLY_PROMO_PREFIX}{current_date.year}{current_date.month:02d}"


def create_personal_free_promo(user_id: int) -> str:
    try:
        from database.promocodes import create_free_promocode
        promo_code = create_free_promocode(user_id)
        if promo_code:
            logger.info(f"Создан персональный промокод для пользователя {user_id}: {promo_code}")
            return promo_code
        else:
            logger.error(f"Ошибка создания персонального промокода для пользователя {user_id}")
            return None
    except Exception as e:
        logger.error(f"Ошибка при создании персонального промокода для пользователя {user_id}: {e}", exc_info=True)
        return None


def apply_free_generation_promo(user_id: int) -> dict:
    try:
        promo_code = create_personal_free_promo(user_id)
        if promo_code:
            return {
                'success': True,
                'promo_code': promo_code,
                'message': f"Создан промокод для бесплатной генерации: {promo_code}"
            }
        else:
            return {
                'success': False,
                'promo_code': None,
                'message': "Не удалось создать промокод для бесплатной генерации"
            }
    except Exception as e:
        logger.error(f"Ошибка при применении промокода для бесплатной генерации для пользователя {user_id}: {e}",
                     exc_info=True)
        return {
            'success': False,
            'promo_code': None,
            'message': "Произошла ошибка при создании промокода"
        }

async def send_monthly_promo_notification(bot, admin_ids_list):
    try:
        new_promo_code = generate_monthly_promo_code()
        from database.promocodes import create_promocode
        create_promocode(new_promo_code, "percent", 15.0, 30, 100)  # 15% скидка, 30 дней, 100 использований

        logger.info(f"Сгенерирован ежемесячный промокод: {new_promo_code}")

        from config import config

        message_text = (
            "🎉 <b>Новый ежемесячный промокод!</b>\n\n"
            f"Сгенерирован промокод: <code>{new_promo_code}</code>\n"
            "Скидка: <b>15%</b>\n"
            "Срок действия: <b>30 дней</b>\n"
            "Количество использований: <b>100</b>\n\n"
            "Этот промокод можно использовать для:\n"
            "• Пользователей, оставляющих отзывы\n"
            "• В рекламных целях\n"
            "• Поощрения активных пользователей"
        )

        if not hasattr(config, 'ADMIN_BOT_TOKEN') or not config.ADMIN_BOT_TOKEN:
            logger.warning("ADMIN_BOT_TOKEN не установлен. Используем основной бот для уведомлений.")
            # Отправляем через основной бот
            for admin_id_str in admin_ids_list:
                try:
                    admin_id = int(admin_id_str.strip())
                    await bot.send_message(
                        chat_id=admin_id,
                        text=message_text,
                        parse_mode='HTML'
                    )
                    logger.info(f"Ежемесячный промокод {new_promo_code} отправлен админу {admin_id}")
                except Exception as e_inner:
                    logger.error(f"Ошибка уведомления админа {admin_id_str} через основной бот: {e_inner}")
            return

        from aiogram import Bot
        admin_bot = Bot(token=config.ADMIN_BOT_TOKEN)
        send_success = False

        for admin_id_str in admin_ids_list:
            try:
                admin_id = int(admin_id_str.strip())
                await admin_bot.send_message(chat_id=admin_id, text=message_text, parse_mode='HTML')
                logger.info(f"Ежемесячный промокод {new_promo_code} отправлен админу {admin_id}")
                send_success = True
            except Exception as e_admin:
                logger.error(f"Ошибка отправки промокода админу {admin_id}: {e_admin}")

        await admin_bot.session.close()

        if not send_success:
            logger.error("Не удалось отправить ежемесячный промокод ни одному администратору.")

    except Exception as e:
        logger.error(f"Ошибка при отправке ежемесячного уведомления о промокоде: {e}", exc_info=True)
        try:
            if 'admin_bot' in locals():
                await admin_bot.session.close()
        except:
            pass
        try:
            for admin_id_str in admin_ids_list:
                try:
                    admin_id = int(admin_id_str.strip())
                    await bot.send_message(
                        chat_id=admin_id,
                        text="❌ <b>Критическая ошибка при генерации ежемесячного промокода.</b>\nПожалуйста, проверьте логи.",
                        parse_mode='HTML'
                    )
                except:
                    pass
        except:
            pass


def is_current_month_promo_active() -> bool:
    try:
        current_promo = get_current_month_promo()
        from database.promocodes import get_promocode_by_code

        promo = get_promocode_by_code(current_promo)
        if promo:
            is_valid, _ = is_promocode_valid(current_promo)
            return is_valid
        return False
    except Exception as e:
        logger.error(f"Ошибка при проверке активности промокода текущего месяца: {e}", exc_info=True)
        return False
