import uuid
import logging
from config import config

logger = logging.getLogger('doc_bot.payment')


def get_yookassa_config():
    """Ленивое получение конфигурации ЮKassa"""
    try:
        # Ленивый импорт config и yookassa
        from config import config
        from yookassa import Configuration

        # Настройка конфигурации
        Configuration.account_id = config.YOOKASSA_SHOP_ID
        Configuration.secret_key = config.YOOKASSA_SECRET_KEY

        return True
    except Exception as e:
        logger.error(f"Ошибка настройки конфигурации ЮKassa: {e}", exc_info=True)
        return False


def create_payment(amount, description, user_id=None):
    """Создает платеж в ЮKassa"""
    try:
        # Устанавливаем минимальную сумму 1 рубль для случаев с 100% скидкой
        payment_amount = max(1.0, amount)

        # Проверяем и настраиваем конфигурацию
        if not get_yookassa_config():
            raise Exception("Не удалось настроить конфигурацию ЮKassa")

        # Ленивый импорт Payment
        from yookassa import Payment

        payment = Payment.create({
            "amount": {
                "value": f"{payment_amount:.2f}",
                "currency": "RUB"
            },
            "confirmation": {
                "type": "redirect",
                "return_url": f"https://t.me/{config.BOT_USERNAME}"
            },
            "capture": True,
            "description": description,
            "metadata": {
                "user_id": str(user_id) if user_id else "",
                "order_id": str(uuid.uuid4()),
                "original_amount": str(amount)
            }
        })

        logger.info(
            f"Payment created: {payment.id}, original amount: {amount}, payment amount: {payment_amount}, user_id: {user_id}")

        return payment
    except Exception as e:
        logger.error(f"Error creating payment: {e}", exc_info=True)
        raise


def check_payment_status(payment_id):
    """Проверяет статус платежа в ЮKassa"""
    try:
        # Проверяем и настраиваем конфигурацию
        if not get_yookassa_config():
            return "unknown"

        # Ленивый импорт Payment
        from yookassa import Payment

        payment = Payment.find_one(payment_id)
        logger.info(f"Payment {payment_id} status: {payment.status}")
        return payment.status
    except Exception as e:
        logger.error(f"Error checking payment status: {e}", exc_info=True)
        return "unknown"