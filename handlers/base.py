import logging
from aiogram import Router, F
from aiogram.types import Message, CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.filters import Command, CommandObject

from texts.messages import (
    MAIN_MENU_TEXT,
    ABOUT_TEXT,
    SUPPORT_TEXT,
    CART_TEXT,
    CART_EMPTY_TEXT
)
from database.users import get_or_create_user
from database.cart import get_user_cart, clear_cart
from database.promocodes import add_referral, create_ruble_promocode
from services.notifications import notify_support_about_support_request
from config import config

logger = logging.getLogger('doc_bot.base')
router = Router(name="base_router")


class ContactSupport(StatesGroup):
    waiting_for_message = State()


def format_item_count(count: int) -> str:
    if count % 10 == 1 and count % 100 != 11:
        return f"{count} документ"
    elif 2 <= count % 10 <= 4 and (count % 100 < 10 or count % 100 >= 20):
        return f"{count} документа"
    else:
        return f"{count} документов"


def format_cart_items(items: list) -> str:
    items_list = ""
    for i, item in enumerate(items, 1):
        doc_type = "шаблон"
        if '_autogen' in item.get('cart_item_id', ''):
            doc_type = "автогенерация"
        price = item['price']
        items_list += f"{i}. {item['doc_name']} ({doc_type}) - {price} ₽\n"
    return items_list


@router.message(Command("start"))
async def cmd_start(message: Message, command: CommandObject, state: FSMContext):
    user_id = message.from_user.id
    logger.info(f"Пользователь {user_id} запустил бота")

    try:
        await state.clear()

        get_or_create_user(
            user_id=str(user_id),
            username=message.from_user.username,
            first_name=message.from_user.first_name,
            last_name=message.from_user.last_name,
            language_code=message.from_user.language_code
        )

        if command.args and command.args.startswith("ref"):
            try:
                referrer_id = int(command.args[3:])
                if referrer_id != user_id:
                    if add_referral(referrer_id, user_id):
                        logger.info(f"Пользователь {user_id} добавлен как реферал для {referrer_id}")

                        promo_newbie = create_ruble_promocode(user_id)
                        if promo_newbie:
                            await message.answer(
                                f"🎉 Приветствуем! Вы перешли по реферальной ссылке.\n\n"
                                f"Ваш промокод на <b>1 бесплатный заказ</b>: <code>{promo_newbie}</code>\n"
                                f"Промокод действует 1 раз. Используйте его при оформлении заказа!",
                                parse_mode="HTML"
                            )

                        promo_referrer = create_ruble_promocode(referrer_id)
                        if promo_referrer:
                            try:
                                await message.bot.send_message(
                                    chat_id=referrer_id,
                                    text=f"🎁 Отлично! Пользователь перешёл по вашей ссылке.\n\n"
                                         f"Ваш бонус — промокод на <b>1 бесплатный заказ</b>: <code>{promo_referrer}</code>",
                                    parse_mode="HTML"
                                )
                                logger.info(f"Промокод отправлен рефереру {referrer_id}")
                            except Exception as e:
                                logger.warning(f"Не удалось отправить промокод рефереру {referrer_id}: {e}")
                        else:
                            logger.error(f"Не удалось создать промокод для реферера {referrer_id}")
                    else:
                        logger.info(f"Реферал {user_id} уже существует (дубль)")
                else:
                    logger.warning(f"Пользователь {user_id} попытался использовать свою ссылку")

            except (ValueError, TypeError):
                logger.warning(f"Неверный формат реферала: {command.args}")

        # Основное меню
        cart = get_user_cart(user_id)
        cart_badge = f" ({cart['item_count']})" if cart['item_count'] > 0 else ""

        buttons = [
            [InlineKeyboardButton(text="📁 Каталог документов", callback_data="catalog")],
            [InlineKeyboardButton(text="🤝 Партнерская программа", callback_data="partner_program")],
            [InlineKeyboardButton(text=f"🛒 Корзина{cart_badge}", callback_data="view_cart")],
            [InlineKeyboardButton(text="📦 История заказов", callback_data="order_history")],
            [InlineKeyboardButton(text="⭐ Отзывы", callback_data="reviews")],
            [InlineKeyboardButton(text="❓ О боте", callback_data="about")],
            [InlineKeyboardButton(text="🆘 Поддержка", callback_data="support")]
        ]

        if user_id in config.ADMIN_IDS:
            buttons.append([InlineKeyboardButton(text="⚙️ Админ-панель", callback_data="admin_panel")])

        markup = InlineKeyboardMarkup(inline_keyboard=buttons)

        await message.answer(
            MAIN_MENU_TEXT,
            reply_markup=markup,
            parse_mode="HTML"
        )

    except Exception as e:
        logger.error(f"Ошибка в обработчике /start: {e}", exc_info=True)
        await message.answer(
            "❌ Произошла ошибка при обработке команды.\n\n"
            "Пожалуйста, попробуйте позже или обратитесь в поддержку: @biz_annet",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="🏠 Главное меню", callback_data="back_main")]
            ])
        )


@router.callback_query(F.data == "back_main")
async def back_to_main(callback: CallbackQuery, state: FSMContext):
    logger.info(f"Пользователь {callback.from_user.id} вернулся в главное меню")
    await state.clear()
    await cmd_start(callback.message, CommandObject(), state)
    await callback.answer()


@router.callback_query(F.data == "view_cart")
async def view_cart(callback: CallbackQuery):
    user_id = callback.from_user.id
    logger.info(f"Пользователь {user_id} просмотрел корзину")

    try:
        cart = get_user_cart(user_id)

        if not cart['items']:
            await callback.message.edit_text(
                CART_EMPTY_TEXT,
                parse_mode="HTML",
                reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                    [InlineKeyboardButton(text="🛍️ Перейти в каталог", callback_data="catalog")],
                    [InlineKeyboardButton(text="🏠 Главное меню", callback_data="back_main")]
                ])
            )
            await callback.answer()
            return

        items_list = format_cart_items(cart['items'])
        item_count_str = format_item_count(cart['item_count'])
        cart_text = (
            "🛒 <b>Ваша корзина</b>\n\n"
            f"{items_list}\n"
            f"В корзине: {item_count_str}\n"
            f"Общая стоимость: <b>{cart['total']} ₽</b>\n\n"
            "Вы можете продолжить покупки или оформить заказ."
        )

        buttons = [
            [InlineKeyboardButton(text="✅ Оформить заказ", callback_data="checkout")],
            [InlineKeyboardButton(text="🛍️ Продолжить покупки", callback_data="catalog")],
            [InlineKeyboardButton(text="🗑 Очистить корзину", callback_data="clear_cart")],
            [InlineKeyboardButton(text="🏠 Главное меню", callback_data="back_main")]
        ]
        markup = InlineKeyboardMarkup(inline_keyboard=buttons)

        await callback.message.edit_text(
            text=cart_text,
            parse_mode="HTML",
            reply_markup=markup
        )
        await callback.answer()

    except Exception as e:
        logger.error(f"Ошибка при отображении корзины: {e}", exc_info=True)
        await callback.answer("⚠️ Произошла ошибка при отображении корзины", show_alert=True)


@router.callback_query(F.data == "clear_cart")
async def clear_cart_handler(callback: CallbackQuery):
    user_id = callback.from_user.id
    logger.info(f"Пользователь {user_id} начал очистку корзины")

    try:
        success = clear_cart(user_id)
        if success:
            await callback.answer("✅ Корзина очищена", show_alert=True)
            cart = get_user_cart(user_id)
            if not cart['items']:
                await callback.message.edit_text(
                    CART_EMPTY_TEXT,
                    parse_mode="HTML",
                    reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                        [InlineKeyboardButton(text="🛍️ Перейти в каталог", callback_data="catalog")],
                        [InlineKeyboardButton(text="🏠 Главное меню", callback_data="back_main")]
                    ])
                )
            else:
                await view_cart(callback)
        else:
            await callback.answer("⚠️ Не удалось очистить корзину", show_alert=True)

    except Exception as e:
        logger.error(f"Ошибка при очистке корзины: {e}", exc_info=True)
        await callback.answer("⚠️ Произошла ошибка при очистке корзины", show_alert=True)


@router.callback_query(F.data == "about")
async def show_about(callback: CallbackQuery):
    logger.info(f"Пользователь {callback.from_user.id} запросил информацию 'О боте'")

    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔍 Посмотреть отзывы", url="https://t.me/docgenerator")],
        [InlineKeyboardButton(text="💎 Присоединиться к сообществу", url="https://t.me/bizhack_annet")],
        [InlineKeyboardButton(text="⬅️ Назад", callback_data="back_main")]
    ])

    await callback.message.edit_text(
        ABOUT_TEXT,
        parse_mode="HTML",
        reply_markup=keyboard,
        disable_web_page_preview=True
    )
    await callback.answer()


@router.callback_query(F.data == "support")
async def handle_support(callback: CallbackQuery):
    logger.info(f"Пользователь {callback.from_user.id} запросил информацию о поддержке")

    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="💬 Написать в поддержку", callback_data="contact_support")],
        [InlineKeyboardButton(text="⬅️ Назад", callback_data="back_main")]
    ])

    await callback.message.edit_text(
        SUPPORT_TEXT,
        parse_mode="HTML",
        reply_markup=keyboard
    )
    await callback.answer()


@router.callback_query(F.data == "contact_support")
async def contact_support(callback: CallbackQuery, state: FSMContext):
    logger.info(f"Пользователь {callback.from_user.id} перешел в режим поддержки")

    await callback.message.edit_text(
        "💬 Напишите ваше сообщение в поддержку.\n\n"
        "Опишите проблему или задайте вопрос, и мы ответим в ближайшее время.",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="⬅️ Назад", callback_data="back_main")]
        ])
    )
    await state.set_state(ContactSupport.waiting_for_message)
    await callback.answer()


@router.message(ContactSupport.waiting_for_message)
async def process_support_message(message: Message, state: FSMContext):
    logger.info(f"Получено сообщение в поддержку от пользователя {message.from_user.id}")

    try:
        await notify_support_about_support_request(message.from_user.id, message.text)

        await message.answer(
            "✅ Ваше сообщение отправлено в поддержку!\n\n"
            "Мы ответим вам в ближайшее время.",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="🏠 Главное меню", callback_data="back_main")]
            ])
        )
        await state.clear()
    except Exception as e:
        logger.error(f"Ошибка обработки сообщения в поддержку: {e}", exc_info=True)
        await message.answer(
            "❌ Произошла ошибка при отправке сообщения.\n\n"
            "Попробуйте позже или напишите напрямую: @biz_annet",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="🏠 Главное меню", callback_data="back_main")]
            ])
        )
        await state.clear()