import logging
from aiogram import Router, F
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup
from config import config
from database.users import get_referral_link, get_partner_stats
from texts.messages import PARTNER_PROGRAM_TEXT

logger = logging.getLogger('doc_bot.partners')
router = Router(name="partners_router")


def format_partner_text(user_id: int) -> str:
    referral_link = get_referral_link(user_id)
    return PARTNER_PROGRAM_TEXT.format(referral_link=referral_link)


@router.callback_query(F.data == "partner_program")
async def show_partner_program(callback: CallbackQuery):
    user_id = callback.from_user.id
    logger.info(f"Пользователь {user_id} запросил информацию о партнерской программе")

    try:
        partner_text = format_partner_text(user_id)

        buttons = [
            [
                InlineKeyboardButton(
                    text="🔄 Обновить статистику",
                    callback_data="update_partner_stats"
                )
            ],
            [
                InlineKeyboardButton(
                    text="ℹ️ Как приглашать",
                    callback_data="partner_rules"
                )
            ],
            [
                InlineKeyboardButton(
                    text="👥 Мои рефералы",
                    callback_data="my_referrals"
                )
            ],
            [
                InlineKeyboardButton(
                    text="🏠 Главное меню",
                    callback_data="back_main"
                )
            ]
        ]
        markup = InlineKeyboardMarkup(inline_keyboard=buttons)

        await callback.message.edit_text(
            text=partner_text,
            parse_mode="HTML",
            reply_markup=markup
        )
        await callback.answer()

    except Exception as e:
        logger.error(f"Ошибка при отображении партнерской программы: {e}", exc_info=True)
        await callback.answer("⚠️ Произошла ошибка", show_alert=True)


@router.callback_query(F.data == "update_partner_stats")
async def update_partner_stats(callback: CallbackQuery):
    user_id = callback.from_user.id
    logger.info(f"Пользователь {user_id} обновил статистику партнера")

    try:
        partner_text = format_partner_text(user_id)

        buttons = [
            [
                InlineKeyboardButton(
                    text="🔄 Обновить статистику",
                    callback_data="update_partner_stats"
                )
            ],
            [
                InlineKeyboardButton(
                    text="ℹ️ Как приглашать",
                    callback_data="partner_rules"
                )
            ],
            [
                InlineKeyboardButton(
                    text="👥 Мои рефералы",
                    callback_data="my_referrals"
                )
            ],
            [
                InlineKeyboardButton(
                    text="🏠 Главное меню",
                    callback_data="back_main"
                )
            ]
        ]
        markup = InlineKeyboardMarkup(inline_keyboard=buttons)

        await callback.message.edit_text(
            text=partner_text,
            parse_mode="HTML",
            reply_markup=markup
        )
        await callback.answer("✅ Статистика обновлена")

    except Exception as e:
        logger.error(f"Ошибка при обновлении статистики: {e}", exc_info=True)
        await callback.answer("⚠️ Ошибка обновления", show_alert=True)


@router.callback_query(F.data == "partner_rules")
async def partner_rules(callback: CallbackQuery):
    user_id = callback.from_user.id
    logger.info(f"Пользователь {user_id} запросил правила")

    try:
        rules_text = (
            "ℹ️ <b>Как приглашать друзей и зарабатывать</b>\n\n"
            "✨ <b>Теперь всё проще:</b>\n"
            "• Поделитесь своей ссылкой\n"
            "• Друг получает промокод на заказ за 1₽\n"
            "• Вы тоже получаете промокод на заказ за 1₽\n\n"
            "🎯 Это работает мгновенно — без ожидания заказа!"
        )

        buttons = [
            [InlineKeyboardButton(text="🔙 Назад", callback_data="partner_program")]
        ]
        markup = InlineKeyboardMarkup(inline_keyboard=buttons)

        await callback.message.edit_text(
            text=rules_text,
            parse_mode="HTML",
            reply_markup=markup
        )
        await callback.answer()

    except Exception as e:
        logger.error(f"Ошибка при отображении правил: {e}", exc_info=True)
        await callback.answer("⚠️ Ошибка загрузки правил", show_alert=True)


@router.callback_query(F.data == "my_referrals")
async def my_referrals(callback: CallbackQuery):
    user_id = callback.from_user.id
    logger.info(f"Пользователь {user_id} запросил список рефералов")

    try:
        from database.users import get_user_referrals
        referrals = get_user_referrals(user_id)

        if referrals:
            referrals_text = "👥 <b>Ваши рефералы</b>\n\n"
            for i, referral in enumerate(referrals, 1):
                name = f"{referral['first_name']} {referral['last_name'] or ''}".strip()
                date = referral['registered_at'].split(' ')[0]
                referrals_text += f"{i}. {name}\n   📅 Зарегистрирован: {date}\n\n"
            referrals_text += "🎁 За каждого вы уже получили промокод на 1₽!"
        else:
            referrals_text = (
                "👥 <b>Ваши рефералы</b>\n\n"
                "У вас пока нет приглашенных пользователей.\n\n"
                "Начните делиться ссылкой — и получите свой первый промокод!"
            )

        buttons = [
            [InlineKeyboardButton(text="🔗 Получить ссылку", callback_data="get_referral_link")],
            [InlineKeyboardButton(text="🔙 Назад", callback_data="partner_program")]
        ]
        markup = InlineKeyboardMarkup(inline_keyboard=buttons)

        await callback.message.edit_text(
            text=referrals_text,
            parse_mode="HTML",
            reply_markup=markup
        )
        await callback.answer()

    except Exception as e:
        logger.error(f"Ошибка при отображении рефералов: {e}", exc_info=True)
        await callback.answer("⚠️ Ошибка загрузки рефералов", show_alert=True)


@router.callback_query(F.data == "get_referral_link")
async def get_referral_link_handler(callback: CallbackQuery):
    user_id = callback.from_user.id
    logger.info(f"Пользователь {user_id} запросил реферальную ссылку")

    try:
        referral_link = get_referral_link(user_id)
        link_text = (
            "🔗 <b>Ваша реферальная ссылка</b>\n\n"
            f"<code>{referral_link}</code>\n\n"
            "🎯 Отправьте её другу — и вы оба получите заказ за 1 рубль!"
        )

        buttons = [
            [
                InlineKeyboardButton(
                    text="📱 Поделиться",
                    switch_inline_query=f"Приглашаю в @DocGeneratorBot — заказ за 1₽! {referral_link}"
                )
            ],
            [InlineKeyboardButton(text="🔙 Назад", callback_data="my_referrals")]
        ]
        markup = InlineKeyboardMarkup(inline_keyboard=buttons)

        await callback.message.edit_text(
            text=link_text,
            parse_mode="HTML",
            reply_markup=markup
        )
        await callback.answer()

    except Exception as e:
        logger.error(f"Ошибка при получении ссылки: {e}", exc_info=True)
        await callback.answer("⚠️ Ошибка получения ссылки", show_alert=True)