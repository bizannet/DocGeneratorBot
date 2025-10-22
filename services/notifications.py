import logging
from datetime import datetime
from config import config
from aiogram import Bot

logger = logging.getLogger('doc_bot.notifications')


async def notify_support_about_new_order(
    bot: Bot,
    order_id: int,
    user_id: int,
    cart_items: list,
    total_price: float,
    discounted_price: float,
    promocode: str = None
):
    if not config.SUPPORT_CHAT_ID:
        logger.error("SUPPORT_CHAT_ID не установлен в конфигурации")
        return

    order_details = f"Заказ #{order_id}\n"
    order_details += f"Пользователь: {user_id}\n"
    order_details += f"Дата: {datetime.now().strftime('%d.%m.%Y %H:%M')}\n\n"
    order_details += "Документы в заказе:\n"

    for item in cart_items:
        doc_type = "автогенерация" if item.get('price_type') == 'autogen' else "шаблон"
        order_details += f"- {item['doc_name']} ({doc_type}) - {item['price']} ₽\n"

    if promocode:
        discount_pct = ((total_price - discounted_price) / total_price * 100) if total_price > 0 else 100
        order_details += f"\nПрименен промокод: {promocode}\n"
        order_details += f"Скидка: {discount_pct:.0f}%\n"
        order_details += f"Экономия: {total_price - discounted_price:.2f} ₽\n"

    order_details += f"\nИтоговая стоимость: {discounted_price:.2f} ₽"
    if promocode:
        order_details += f" (с учетом скидки {total_price - discounted_price:.2f} ₽)"
    order_details += f"\nОплачено: {total_price:.2f} ₽"

    message = "🛒 <b>Новый заказ</b>\n\n" + order_details

    try:
        await bot.send_message(
            chat_id=config.SUPPORT_CHAT_ID,
            text=message,
            parse_mode="HTML"
        )
        logger.info(f"Уведомление о заказе {order_id} отправлено в группу {config.SUPPORT_CHAT_ID}")
    except Exception as e:
        logger.error(f"Ошибка отправки уведомления о заказе: {e}")


async def notify_support_about_support_request(bot: Bot, user_id: int, message_text: str):
    if not config.SUPPORT_CHAT_ID:
        logger.error("SUPPORT_CHAT_ID не установлен")
        return

    reply_id = f"reply_{user_id}_{int(datetime.now().timestamp())}"
    text = (
        f"🆘 <b>Новый запрос в поддержку!</b>\n\n"
        f"👤 Пользователь: <code>{user_id}</code>\n\n"
        f"📝 Сообщение:\n<i>{message_text}</i>"
    )

    try:
        await bot.send_message(
            chat_id=config.SUPPORT_CHAT_ID,
            text=text,
            parse_mode="HTML"
        )
        logger.info("Уведомление о запросе поддержки отправлено")
    except Exception as e:
        logger.error(f"Ошибка отправки запроса поддержки: {e}")


async def send_daily_stats_report(bot: Bot):
    from database.orders import get_daily_stats

    if not config.SUPPORT_CHAT_ID:
        return

    stats = get_daily_stats()
    message = (
        f"📊 <b>Ежедневная статистика за {datetime.now().strftime('%d.%m.%Y')}</b>\n\n"
        f"🛒 Заказы: <b>{stats['orders_count']}</b>\n"
        f"💰 Общая сумма: <b>{stats['total_amount']} ₽</b>\n"
        f"👥 Уникальные пользователи: <b>{stats['unique_users']}</b>\n"
        f"🏷 Промокодов: <b>{stats['promocodes_used']}</b>\n"
        f"📄 Шаблонов: <b>{stats['templates_used']}</b>"
    )

    try:
        await bot.send_message(chat_id=config.SUPPORT_CHAT_ID, text=message, parse_mode="HTML")
        logger.info("Ежедневная статистика отправлена")
    except Exception as e:
        logger.error(f"Ошибка отправки ежедневной статистики: {e}")


async def send_monthly_stats_report(bot: Bot):
    from database.orders import get_monthly_stats

    if not config.SUPPORT_CHAT_ID:
        return

    stats = get_monthly_stats()
    message = (
        f"📈 <b>Ежемесячная статистика за {datetime.now().strftime('%B %Y')}</b>\n\n"
        f"🛒 Заказы: <b>{stats['orders_count']}</b>\n"
        f"💰 Общая сумма: <b>{stats['total_amount']} ₽</b>\n"
        f"👥 Уникальные пользователи: <b>{stats['unique_users']}</b>\n"
        f"🏷 Промокодов: <b>{stats['promocodes_used']}</b>\n"
        f"📄 Шаблонов: <b>{stats['templates_used']}</b>\n"
        f"💸 Экономия: <b>{stats['total_savings']} ₽</b>"
    )

    try:
        await bot.send_message(chat_id=config.SUPPORT_CHAT_ID, text=message, parse_mode="HTML")
        logger.info("Ежемесячная статистика отправлена")
    except Exception as e:
        logger.error(f"Ошибка отправки ежемесячной статистики: {e}")


async def send_yearly_stats_report(bot: Bot):
    from database.orders import get_yearly_stats

    if not config.SUPPORT_CHAT_ID:
        return

    stats = get_yearly_stats()
    message = (
        f"🌍 <b>Годовая статистика за {datetime.now().strftime('%Y')}</b>\n\n"
        f"🛒 Заказы: <b>{stats['orders_count']}</b>\n"
        f"💰 Общая сумма: <b>{stats['total_amount']} ₽</b>\n"
        f"👥 Уникальные пользователи: <b>{stats['unique_users']}</b>\n"
        f"🏷 Промокодов: <b>{stats['promocodes_used']}</b>\n"
        f"📄 Шаблонов: <b>{stats['templates_used']}</b>\n"
        f"💸 Экономия: <b>{stats['total_savings']} ₽</b>\n\n"
        f"📈 <b>Рост по сравнению с прошлым годом:</b>\n"
        f"• Заказы: {stats['growth_orders']}%\n"
        f"• Выручка: {stats['growth_revenue']}%"
    )

    try:
        await bot.send_message(chat_id=config.SUPPORT_CHAT_ID, text=message, parse_mode="HTML")
        logger.info("Годовая статистика отправлена")
    except Exception as e:
        logger.error(f"Ошибка отправки годовой статистики: {e}")


async def notify_support_about_new_promocode(bot: Bot, promocode_code: str, discount: int):
    month_abbr = promocode_code[:3].upper()
    months = {
        "JAN": "января", "FEB": "февраля", "MAR": "марта", "APR": "апреля",
        "MAY": "мая", "JUN": "июня", "JUL": "июля", "AUG": "августа",
        "SEP": "сентября", "OCT": "октября", "NOV": "ноября", "DEC": "декабря"
    }
    month_name = months.get(month_abbr, "месяца")

    message = (
        f"🎉 <b>Новый сезонный промокод!</b>\n\n"
        f"С {month_name} действует новый промокод: <code>{promocode_code}</code>\n"
        f"Скидка: {discount}%\n\n"
        f"Этот промокод автоматически создан системой и действует до 1 числа следующего месяца.\n"
        f"Вы можете использовать его для рекламных акций."
    )

    try:
        await bot.send_message(chat_id=config.SUPPORT_CHAT_ID, text=message, parse_mode="HTML")
        logger.info(f"Уведомление о промокоде {promocode_code} отправлено")
    except Exception as e:
        logger.error(f"Ошибка отправки уведомления о промокоде: {e}")


async def send_newsletter_to_all(bot: Bot, message_text: str) -> dict:
    from database.users import get_all_users

    users = get_all_users()
    sent_count = 0
    failed_count = 0

    for user in users:
        try:
            await bot.send_message(
                chat_id=user['id'],
                text=message_text,
                parse_mode="HTML"
            )
            sent_count += 1
        except Exception as e:
            failed_count += 1
            logger.warning(f"Не удалось отправить сообщение пользователю {user['id']}: {e}")

    result = {
        'sent': sent_count,
        'failed': failed_count,
        'total': len(users)
    }
    logger.info(f"Рассылка завершена: {sent_count} успешно, {failed_count} ошибок из {len(users)} пользователей")
    return result