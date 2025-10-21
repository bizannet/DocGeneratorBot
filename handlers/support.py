import logging
from aiogram import Router, F
from aiogram.types import Message
from aiogram.exceptions import (
    TelegramForbiddenError,
    TelegramRetryAfter,
    TelegramBadRequest
)
from config import config

logger = logging.getLogger('doc_bot.support')
router = Router(name="support_router")


@router.message(F.chat.id == config.SUPPORT_CHAT_ID)
async def handle_admin_support_reply(message: Message):
    if not message.text or ":" not in message.text:
        await message.reply(
            "⚠️ Неверный формат.\n\n"
            "Пожалуйста, отправьте ответ в формате:\n"
            "<code>123456789: Ваш ответ здесь</code>",
            parse_mode="HTML"
        )
        return

    try:
        user_id_part, reply_text = message.text.split(":", 1)
        user_id = int(user_id_part.strip())
        text = reply_text.strip()

        if not text:
            raise ValueError("Текст ответа пуст")

        await message.bot.send_message(
            chat_id=user_id,
            text=f"📬 <b>Ответ от поддержки:</b>\n\n{text}",
            parse_mode="HTML"
        )

        logger.info(f"Ответ от поддержки отправлен пользователю {user_id}")
        await message.reply("✅ Ответ успешно отправлен!")

    except ValueError as e:
        logger.warning(f"Неверный формат ID или пустой текст: {e}")
        await message.reply("❌ Неверный ID или пустое сообщение. Убедитесь, что формат: <code>ID: текст</code>",
                            parse_mode="HTML")

    except TelegramForbiddenError:
        logger.warning(f"Не удалось отправить сообщение пользователю {user_id}: бот заблокирован")
        await message.reply("❌ Пользователь заблокировал бота или удалил чат.")

    except TelegramRetryAfter as e:
        logger.warning(f"Ограничение Telegram: повтор через {e.retry_after} сек")
        await message.reply(f"⏳ Telegram временно ограничил отправку. Повторите через {e.retry_after} сек.")

    except TelegramBadRequest as e:
        logger.error(f"Ошибка Telegram при отправке: {e}")
        await message.reply(
            "❌ Не удалось отправить сообщение. Возможно, пользователь не существует или бот не может писать первым.")

    except Exception as e:
        logger.error(f"Неожиданная ошибка при отправке ответа: {e}", exc_info=True)
        await message.reply("❌ Произошла внутренняя ошибка. Обратитесь к разработчику.")