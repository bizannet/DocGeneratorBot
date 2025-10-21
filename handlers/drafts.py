import logging
from datetime import datetime
from aiogram import Router, F
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup
from aiogram.fsm.context import FSMContext
from config import config
from database.drafts import (
    get_user_drafts,
    get_draft,
    delete_draft,
    clear_expired_drafts
)
from texts.messages import (
    DRAFTS_LIST_TEXT,
    DRAFT_NOT_FOUND_TEXT
)
from handlers.filling import ask_question_callback

logger = logging.getLogger('doc_bot.drafts')
router = Router(name="drafts_router")


@router.callback_query(F.data == "drafts")
async def show_drafts(callback: CallbackQuery):
    user_id = callback.from_user.id
    logger.info(f"Пользователь {user_id} запросил список черновиков")

    try:
        clear_expired_drafts()
        drafts = get_user_drafts(user_id)

        if not drafts:
            await callback.message.edit_text(
                DRAFT_NOT_FOUND_TEXT,
                parse_mode="HTML",
                reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                    [
                        InlineKeyboardButton(
                            text="🛍️ Перейти в каталог",
                            callback_data="catalog"
                        )
                    ],
                    [
                        InlineKeyboardButton(
                            text="🏠 Главное меню",
                            callback_data="back_main"
                        )
                    ]
                ])
            )
            await callback.answer()
            return

        # Формируем текст
        drafts_text = DRAFTS_LIST_TEXT

        for i, draft in enumerate(drafts, 1):
            expires_at = datetime.strptime(draft['expires_at'], '%Y-%m-%d %H:%M:%S')
            time_left = expires_at - datetime.now()
            hours_left = int(time_left.total_seconds() // 3600)

            drafts_text += (
                f"{i}. <b>{draft['document_name']}</b>\n"
                f"   • Прогресс: {draft['current_index'] + 1}/{draft['total_questions']}\n"
                f"   • Действителен: {hours_left} час(ов)\n\n"
            )

        buttons = []

        for draft in drafts[:5]:
            buttons.append([
                InlineKeyboardButton(
                    text=f"📝 {draft['document_name']}",
                    callback_data=f"draft_{draft['id']}"
                )
            ])

        buttons.append([
            InlineKeyboardButton(
                text="🗑 Очистить все",
                callback_data="clear_drafts"
            )
        ])
        buttons.append([
            InlineKeyboardButton(
                text="🔄 Обновить",
                callback_data="drafts"
            )
        ])
        buttons.append([
            InlineKeyboardButton(
                text="🏠 Главное меню",
                callback_data="back_main"
            )
        ])

        markup = InlineKeyboardMarkup(inline_keyboard=buttons)

        await callback.message.edit_text(
            text=drafts_text,
            parse_mode="HTML",
            reply_markup=markup
        )
        await callback.answer()

    except Exception as e:
        logger.error(f"Ошибка при отображении черновиков: {e}", exc_info=True)
        await callback.answer("⚠️ Произошла ошибка при загрузке черновиков", show_alert=True)
        await callback.answer()


@router.callback_query(F.data.startswith("draft_"))
async def continue_draft(callback: CallbackQuery, state: FSMContext):
    draft_id = int(callback.data.split("_")[1])
    user_id = callback.from_user.id
    logger.info(f"Пользователь {user_id} продолжает заполнение из черновика {draft_id}")

    try:
        draft = get_draft(user_id, draft_id=draft_id)

        if not draft:
            await callback.answer("⚠️ Черновик не найден", show_alert=True)
            await callback.answer()
            return

        await state.update_data(
            filling_document={
                'id': draft['template_id'],
                'name': draft['document_name'],
            },
            answers=draft['answers'],
            current_question=draft['current_index']
        )
        await ask_question_callback(callback, state)

    except Exception as e:
        logger.error(f"Ошибка при продолжении черновика: {e}", exc_info=True)
        await callback.answer("⚠️ Произошла ошибка при загрузке черновика", show_alert=True)
        await callback.answer()


@router.callback_query(F.data == "clear_drafts")
async def clear_drafts(callback: CallbackQuery):
    user_id = callback.from_user.id
    logger.info(f"Пользователь {user_id} очищает все черновики")

    try:
        await callback.answer("✅ Все черновики успешно удалены!", show_alert=True)
        await show_drafts(callback)

    except Exception as e:
        logger.error(f"Ошибка при очистке черновиков: {e}", exc_info=True)
        await callback.answer("⚠️ Произошла ошибка при очистке черновиков", show_alert=True)
        await callback.answer()


@router.callback_query(F.data.startswith("delete_draft_"))
async def delete_single_draft(callback: CallbackQuery):
    draft_id = int(callback.data.split("_")[2])
    user_id = callback.from_user.id
    logger.info(f"Пользователь {user_id} удаляет черновик {draft_id}")
    try:
        success = delete_draft(user_id, draft_id=draft_id)

        if success:
            await callback.answer("✅ Черновик успешно удален!", show_alert=True)
        else:
            await callback.answer("⚠️ Не удалось удалить черновик", show_alert=True)
        await show_drafts(callback)

    except Exception as e:
        logger.error(f"Ошибка при удалении черновика: {e}", exc_info=True)
        await callback.answer("⚠️ Произошла ошибка при удалении черновика", show_alert=True)
        await callback.answer()
