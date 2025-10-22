import logging
import asyncio
import sys
import datetime
from aiogram import Bot, Dispatcher
from aiogram.fsm.storage.memory import MemoryStorage
from config import config
from database import init_db
from handlers import (
    base,
    catalog,
    filling,
    payment,
    order_history,
    admin,
    feedback,
    partners,
    templates,
    drafts,
    support,
    utils
)
from database.promocodes import initialize_default_promocodes, create_seasonal_promocode
from services.notifications import notify_support_about_new_promocode
from services.background_tasks import send_daily_stats

# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    stream=sys.stdout
)
logger = logging.getLogger('doc_bot')


async def main():
    """Основная функция запуска бота"""
    try:
        # Инициализация базы данных
        init_db()
        logger.info("База данных инициализирована")

        # Инициализация промокодов
        initialize_default_promocodes()
        logger.info("Базовые промокоды инициализированы")

        # Проверяем, не начался ли новый месяц
        today = datetime.datetime.now()
        if today.day == 1:
            logger.info("Сегодня первое число месяца, создаем новый сезонный промокод")
            seasonal_promo = create_seasonal_promocode()
            if seasonal_promo:
                # Уведомляем администраторов
                await notify_support_about_new_promocode(seasonal_promo['code'], seasonal_promo['discount'])
        else:
            logger.info("Сегодня не первое число месяца, сезонный промокод не создается")

        # Создание бота и диспетчера
        bot = Bot(token=config.BOT_TOKEN)
        storage = MemoryStorage()
        dp = Dispatcher(storage=storage)

        # Сохраняем бота в глобальную переменную для использования в других модулях
        sys.modules['bot'] = type('bot', (), {'bot': bot})()

        # Регистрация роутеров
        dp.include_router(base.router)
        dp.include_router(catalog.router)
        dp.include_router(filling.router)
        dp.include_router(payment.router)
        dp.include_router(order_history.router)
        dp.include_router(admin.router)
        dp.include_router(feedback.router)
        dp.include_router(partners.router)
        dp.include_router(templates.router)
        dp.include_router(drafts.router)
        dp.include_router(support.router)
        dp.include_router(utils.router)

        # Запуск фоновых задач
        logger.info("Запуск фоновых задач...")
        asyncio.create_task(send_daily_stats())

        # Запуск бота
        logger.info("Запуск бота...")
        await bot.delete_webhook(drop_pending_updates=True)
        await dp.start_polling(bot, allowed_updates=dp.resolve_used_update_types())

    except Exception as e:
        logger.critical(f"Критическая ошибка при запуске бота: {e}", exc_info=True)
        sys.exit(1)


if __name__ == "__main__":
    try:
        logger.info("Запуск приложения...")
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        logger.info("Бот остановлен")