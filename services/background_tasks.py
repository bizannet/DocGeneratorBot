import asyncio
import logging
from datetime import datetime, timedelta
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from config import config
from services.notifications import send_daily_stats_report, send_monthly_stats_report, send_yearly_stats_report

logger = logging.getLogger('doc_bot.background_tasks')


async def clean_expired_drafts_once():
    logger.info("Запущена однократная очистка просроченных черновиков")

    try:
        from database.drafts import get_expired_drafts, delete_draft
        expired_drafts = get_expired_drafts()

        if expired_drafts:
            deleted_count = 0
            for draft in expired_drafts:
                if delete_draft(draft['user_id'], draft['template_id']):
                    deleted_count += 1

            if deleted_count > 0:
                logger.info(f"✅ Очищено {deleted_count} просроченных черновиков")
            return deleted_count
        else:
            logger.debug("Нет просроченных черновиков для удаления")
            return 0
    except Exception as e:
        logger.error(f"❌ Ошибка при однократной очистке черновиков: {e}", exc_info=True)
        return 0


async def clean_expired_drafts():
    logger.info("Запущена фоновая задача очистки черновиков")

    while True:
        try:
            await clean_expired_drafts_once()
            logger.debug("⏳ Ожидание 24 часов перед следующей проверкой черновиков...")
            await asyncio.sleep(86400)
        except Exception as e:
            logger.error(f"❌ Критическая ошибка при очистке черновиков: {e}", exc_info=True)
            await asyncio.sleep(3600)


async def send_draft_reminders(bot):
    logger.info("Запущена фоновая задача напоминаний о черновиках")

    while True:
        try:
            from database.drafts import get_connection
            from database.templates import get_template_by_id

            conn = get_connection()
            cursor = conn.cursor()
            now = datetime.now()
            two_hours_later = now + timedelta(hours=2)
            cursor.execute("""
                SELECT user_id, template_id, expires_at 
                FROM drafts 
                WHERE expires_at > ? AND expires_at <= ?
            """, (now, two_hours_later))
            drafts = cursor.fetchall()
            conn.close()

            logger.info(f"Найдено {len(drafts)} черновиков для отправки напоминаний")

            for draft in drafts:
                user_id = draft[0]
                template_id = draft[1]
                expires_at = draft[2]

                # Отправляем напоминание
                try:
                    # Получаем информацию о документе
                    doc = get_template_by_id(template_id)
                    doc_name = doc['name'] if doc else "документ"

                    # Отправляем сообщение
                    await bot.send_message(
                        user_id,
                        f"⏰ <b>Внимание!</b> У вас есть неоконченное заполнение документа\n\n"
                        f"<b>'{doc_name}'</b>\n\n"
                        f"Черновик будет автоматически удален через 2 часа. "
                        f"Не теряйте свою работу — завершите заполнение прямо сейчас!",
                        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                            [InlineKeyboardButton(text="📝 Продолжить заполнение",
                                                  callback_data=f"draft_{template_id}")],
                            [InlineKeyboardButton(text="🗑️ Удалить черновик",
                                                  callback_data=f"delete_draft_{template_id}")]
                        ]),
                        parse_mode="HTML"
                    )
                    logger.info(f"✅ Отправлено напоминание о черновике пользователю {user_id}")
                except Exception as e:
                    logger.error(f"❌ Ошибка отправки напоминания пользователю {user_id}: {e}")

            # Проверяем каждые 30 минут
            logger.debug("⏳ Ожидание 30 минут перед следующей проверкой напоминаний...")
            await asyncio.sleep(1800)
        except Exception as e:
            logger.error(f"❌ Ошибка при отправке напоминаний о черновиках: {e}", exc_info=True)
            # Ждем 15 минут перед повторной попыткой
            await asyncio.sleep(900)


async def send_daily_stats():
    logger.info("Запущена фоновая задача отправки статистики")

    while True:
        try:
            now = datetime.now()
            hour, minute = map(int, config.STATS_NOTIFICATION_TIME.split(":"))
            next_run = now.replace(hour=hour, minute=minute, second=0, microsecond=0)

            if now >= next_run:
                next_run += timedelta(days=1)

            sleep_seconds = (next_run - now).total_seconds()
            logger.info(f"Следующая отправка статистики через {sleep_seconds} секунд")
            await asyncio.sleep(sleep_seconds)

            await send_daily_stats_report()
            logger.info("✅ Ежедневная статистика отправлена")

            if datetime.now().day == 1:
                await send_monthly_stats_report()
                logger.info("✅ Ежемесячная статистика отправлена")

            if datetime.now().month == 1 and datetime.now().day == 1:
                await send_yearly_stats_report()
                logger.info("✅ Годовая статистика отправлена")

        except Exception as e:
            logger.error(f"❌ Ошибка при отправке статистики: {e}", exc_info=True)
            await asyncio.sleep(3600)