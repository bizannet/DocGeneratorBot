# handlers/payment.py
import logging
import os
from datetime import datetime
from typing import List
from aiogram import Router, F, Bot
from aiogram.types import (
    CallbackQuery, Message, InlineKeyboardButton, InlineKeyboardMarkup,
    PreCheckoutQuery, FSInputFile
)
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup

from config import config
from database.orders import (
    create_order, add_order_item, update_order_status, get_order_by_id,
    get_user_orders
)
from database.cart import get_user_cart, clear_cart, get_cart_total
from database.users import get_partner_stats
from database.payments import create_payment, update_payment_status
from database.promocodes import apply_promocode, check_promocode
from payment.yookassa_integration import (
    create_payment,
    check_payment_status
)
from services.document_generator import generate_document
from services.notifications import notify_support_about_new_order
from texts.messages import (
    CHECKOUT_TEXT,
    PAYMENT_SUCCESS_TEXT,
    CART_EMPTY_TEXT,
    PROMOCODE_APPLIED_TEXT,
    PROMOCODE_ERROR_TEXT,
    YOOKASSA_PAYMENT_TEXT,
    CHECK_PAYMENT_TEXT
)

logger = logging.getLogger('doc_bot.payment')
router = Router(name="payment_router")


class PaymentStates(StatesGroup):
    CHECKING_PAYMENT = State()


class PromocodeStates(StatesGroup):
    WAITING_FOR_PROMOCODE = State()


@router.callback_query(F.data == "checkout")
async def start_checkout(callback: CallbackQuery, state: FSMContext):
    user_id = callback.from_user.id
    logger.info(f"Пользователь {user_id} начал оформление заказа")

    try:
        cart = get_user_cart(user_id)
        if not cart['items']:
            logger.info(f"Корзина пользователя {user_id} пуста")
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

        total_price = get_cart_total(user_id)
        promocode_data = await state.get_data()
        applied_promocode = promocode_data.get('applied_promocode')
        discount = promocode_data.get('discount', 0)
        discounted_price = total_price * (1 - discount / 100) if discount > 0 else total_price

        await state.update_data(
            cart_items=cart['items'],
            total_price=total_price,
            discounted_price=discounted_price,
            item_count=cart['item_count'],
            promocode=applied_promocode
        )

        promocode_text = ""
        if applied_promocode:
            promocode_text = f"\nПрименен промокод <b>{applied_promocode}</b> ({discount}% скидка)"

        checkout_text = CHECKOUT_TEXT.format(
            item_count=cart['item_count'],
            total_price=total_price,
            discounted_price=discounted_price,
            promocode_info=promocode_text
        )

        buttons = []
        partner_stats = get_partner_stats(user_id)
        available_points = partner_stats['available_points'] if partner_stats else 0
        if available_points > 0:
            buttons.append([
                InlineKeyboardButton(
                    text=f"💰 Оплатить баллами (доступно {available_points} ₽)",
                    callback_data="pay_with_points"
                )
            ])
        buttons.append([
            InlineKeyboardButton(text="💳 Оплатить через ЮKassa", callback_data="pay_with_yookassa")
        ])
        buttons.append([
            InlineKeyboardButton(text="🎟 Ввести промокод", callback_data="enter_promocode")
        ])
        buttons.append([
            InlineKeyboardButton(text="⬅️ Назад в корзину", callback_data="view_cart")
        ])

        markup = InlineKeyboardMarkup(inline_keyboard=buttons)
        await callback.message.edit_text(text=checkout_text, parse_mode="HTML", reply_markup=markup)
        await callback.answer()

    except Exception as e:
        logger.error(f"Ошибка при оформлении заказа для пользователя {user_id}: {e}", exc_info=True)
        await callback.answer("⚠️ Произошла ошибка при оформлении заказа", show_alert=True)


@router.callback_query(F.data == "enter_promocode")
async def enter_promocode(callback: CallbackQuery, state: FSMContext):
    await callback.message.edit_text(
        "Введите промокод:",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="⬅️ Назад", callback_data="checkout")]
        ])
    )
    await state.set_state(PromocodeStates.WAITING_FOR_PROMOCODE)
    await callback.answer()


@router.message(PromocodeStates.WAITING_FOR_PROMOCODE)
async def process_promocode(message: Message, state: FSMContext):
    user_id = message.from_user.id
    promocode = message.text.strip().upper()
    logger.info(f"Пользователь {user_id} ввел промокод: {promocode}")

    data = await state.get_data()
    total_price = data.get('total_price', 0)
    result = check_promocode(promocode, user_id)

    if result:
        discount = result['discount']
        discounted_price = total_price * (1 - discount / 100)
        await state.update_data(
            applied_promocode=promocode,
            discount=discount,
            discounted_price=discounted_price
        )

        display_price = discounted_price
        payment_note = ""
        if discounted_price <= 0:
            display_price = 0.0
            payment_note = (
                "\nℹ️ Минимальная сумма оплаты в системе — 1 ₽. "
                "Вы будете оплачивать символический платёж в 1 рубль."
            )

        promo_applied_text = (
            f"✅ Промокод применен!\n"
            f"Ваша итоговая стоимость: {display_price:.2f} ₽"
            f"{payment_note}"
        )

        promocode_text = f"\nПрименен промокод <b>{promocode}</b> ({discount}% скидка)"
        checkout_text = CHECKOUT_TEXT.format(
            item_count=data['item_count'],
            total_price=total_price,
            discounted_price=discounted_price,
            promocode_info=promocode_text
        )

        buttons = [
            [InlineKeyboardButton(text="💳 Оплатить через ЮKassa", callback_data="pay_with_yookassa")],
            [InlineKeyboardButton(text="🎟 Ввести другой промокод", callback_data="enter_promocode")],
            [InlineKeyboardButton(text="⬅️ Назад в корзину", callback_data="view_cart")]
        ]
        markup = InlineKeyboardMarkup(inline_keyboard=buttons)

        await message.answer(text=promo_applied_text, parse_mode="HTML")
        await message.answer(text=checkout_text, parse_mode="HTML", reply_markup=markup)
        await state.set_state(None)
    else:
        await message.answer(
            PROMOCODE_ERROR_TEXT,
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="⬅️ Назад", callback_data="checkout")]
            ])
        )


@router.callback_query(F.data == "pay_with_yookassa")
async def pay_with_yookassa(callback: CallbackQuery, state: FSMContext):
    user_id = callback.from_user.id
    logger.info(f"Пользователь {user_id} выбрал оплату через ЮKassa")

    try:
        data = await state.get_data()
        logger.debug(f"pay_with_yookassa: Полученные данные из state для user {user_id}: {data}")

        if 'item_count' not in data:
            logger.error(f"pay_with_yookassa: Ключ 'item_count' отсутствует в state для user {user_id}. Данные: {data}")
            await callback.answer("Ошибка данных заказа. Вернитесь в корзину.", show_alert=True)
            return

        if 'cart_items' not in data or not data['cart_items']:
            logger.error(f"pay_with_yookassa: cart_items отсутствуют или пусты для user {user_id}. Данные: {data}")
            await callback.answer("Ошибка данных заказа. Вернитесь в корзину.", show_alert=True)
            return

        total_price = data.get('total_price', 0)
        discounted_price = data.get('discounted_price', total_price)
        promocode = data.get('applied_promocode')
        discount = data.get('discount', 0)
        item_count = data['item_count']
        cart_items = data['cart_items']
        savings = total_price - discounted_price

        order_id = create_order(
            user_id=user_id,
            total_price=total_price,
            discounted_price=discounted_price,
            promocode=promocode,
            item_count=item_count,
            savings=savings
        )

        if not order_id:
            logger.error(f"Не удалось создать заказ для пользователя {user_id}")
            await callback.answer("⚠️ Не удалось создать заказ", show_alert=True)
            return

        for item in cart_items:
            add_order_item(
                order_id=order_id,
                doc_id=item.get('doc_id', item.get('id', 0)),
                doc_name=item.get('doc_name', item.get('name', 'Неизвестный документ')),
                price=item.get('price', 0),
                filled_data=item.get('filled_data', {}),
                price_type=item.get('price_type', "template")
            )

        if promocode:
            apply_promocode(promocode, user_id, order_id)

        payment_id = create_payment(
            user_id=user_id,
            order_id=order_id,
            amount=discounted_price,
            payment_system="yookassa",
            status="pending"
        )

        if not payment_id:
            logger.error(f"Не удалось создать платеж для заказа {order_id} пользователя {user_id}")
            await callback.answer("⚠️ Не удалось создать платеж", show_alert=True)
            return

        payment = create_payment(
            amount=discounted_price,
            description=f"Оплата заказа #{order_id}",
            user_id=user_id
        )

        if not payment:
            logger.error(f"Не удалось создать платеж в ЮKassa для заказа {order_id} пользователя {user_id}")
            await callback.answer("⚠️ Не удалось создать платеж в ЮKassa", show_alert=True)
            return

        await state.update_data(yookassa_payment_id=payment.id, order_id=order_id)

        payment_text = YOOKASSA_PAYMENT_TEXT.format(total_price=discounted_price)
        markup = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="💳 Перейти к оплате", url=payment.confirmation.confirmation_url)],
            [InlineKeyboardButton(text="🔄 Проверить оплату", callback_data="check_payment")],
            [InlineKeyboardButton(text="🏠 Главное меню", callback_data="back_main")]
        ])

        await callback.message.edit_text(text=payment_text, parse_mode="HTML", reply_markup=markup)
        await state.set_state(PaymentStates.CHECKING_PAYMENT)
        await callback.answer()

    except Exception as e:
        logger.critical(f"Критическая ошибка в pay_with_yookassa для пользователя {user_id}: {e}", exc_info=True)
        await callback.answer("⚠️ Критическая ошибка при начале оплаты. Обратитесь в поддержку.", show_alert=True)


@router.callback_query(F.data == "check_payment")
async def check_payment(callback: CallbackQuery, state: FSMContext):
    user_id = callback.from_user.id
    logger.info(f"Пользователь {user_id} проверяет статус платежа")

    try:
        data = await state.get_data()
        yookassa_payment_id = data.get('yookassa_payment_id')
        order_id = data.get('order_id')

        if not yookassa_payment_id or not order_id:
            logger.warning(f"Не удалось найти платеж или заказ для пользователя {user_id}")
            await callback.answer("⚠️ Не удалось найти платеж", show_alert=True)
            return

        status = check_payment_status(yookassa_payment_id)
        logger.info(f"Статус платежа {yookassa_payment_id} для заказа {order_id}: {status}")

        if status == "succeeded":
            update_payment_status(yookassa_payment_id, "succeeded")
            update_order_status(order_id, "paid")
            clear_cart(user_id)

            bot = callback.bot
            success = await process_successful_payment(
                bot=bot,
                user_id=user_id,
                order_id=order_id,
                cart_items=data.get('cart_items', [])
            )

            if success:
                await callback.message.edit_text(
                    text=PAYMENT_SUCCESS_TEXT,
                    parse_mode="HTML",
                    reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                        [InlineKeyboardButton(text="🏠 Главное меню", callback_data="back_main")]
                    ])
                )
            else:
                await callback.message.edit_text(
                    text="⚠️ Оплата прошла, но возникли проблемы с генерацией документов. Обратитесь в поддержку: @biz_annet",
                    parse_mode="HTML",
                    reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                        [InlineKeyboardButton(text="🏠 Главное меню", callback_data="back_main")]
                    ])
                )
            await state.clear()

        elif status == "canceled":
            update_payment_status(yookassa_payment_id, "canceled")
            update_order_status(order_id, "cancelled")
            await callback.message.edit_text(
                "❌ Оплата была отменена.\nВы можете оформить заказ заново.",
                parse_mode="HTML",
                reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                    [InlineKeyboardButton(text="🛍️ Перейти в каталог", callback_data="catalog")],
                    [InlineKeyboardButton(text="🏠 Главное меню", callback_data="back_main")]
                ])
            )
            await state.clear()

        elif status == "waiting_for_capture":
            await callback.answer("⏳ Платеж ожидает подтверждения", show_alert=True)
        else:
            await callback.answer(f"ℹ️ Текущий статус платежа: {status}", show_alert=True)

        await callback.answer()

    except Exception as e:
        logger.error(f"Ошибка при проверке платежа для пользователя {user_id}: {e}", exc_info=True)
        await callback.answer("⚠️ Ошибка при проверке платежа", show_alert=True)


@router.pre_checkout_query()
async def pre_checkout_query(pre_checkout_q: PreCheckoutQuery):
    logger.info(f"Получен предварительный запрос на оплату от {pre_checkout_q.from_user.id}")
    try:
        await pre_checkout_q.answer(ok=True)
    except Exception as e:
        logger.error(f"Ошибка при обработке предварительного запроса: {e}", exc_info=True)
        await pre_checkout_q.answer(ok=False, error_message="⚠️ Ошибка при обработке платежа")


@router.message(F.content_type == "successful_payment")
async def successful_payment(message: Message, state: FSMContext):
    user_id = message.from_user.id
    logger.info(f"Пользователь {user_id} успешно оплатил заказ")

    try:
        data = await state.get_data()
        order_id = data.get('order_id')

        if not order_id:
            orders = get_user_orders(user_id)
            if orders:
                order_id = orders[0]['id']

        if not order_id:
            logger.warning(f"Не удалось найти заказ для пользователя {user_id} после оплаты")
            await message.answer("⚠️ Не удалось найти ваш заказ", reply_markup=None)
            return

        update_order_status(order_id, "paid")
        clear_cart(user_id)

        order = get_order_by_id(order_id)
        cart_items = order['items'] if order and 'items' in order else []

        bot = message.bot
        success = await process_successful_payment(bot=bot, user_id=user_id, order_id=order_id, cart_items=cart_items)

        if success:
            await message.answer(
                text=PAYMENT_SUCCESS_TEXT,
                parse_mode="HTML",
                reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                    [InlineKeyboardButton(text="🏠 Главное меню", callback_data="back_main")]
                ])
            )
        else:
            await message.answer(
                text="⚠️ Оплата прошла, но возникли проблемы с генерацией документов. Обратитесь в поддержку: @biz_annet",
                parse_mode="HTML",
                reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                    [InlineKeyboardButton(text="🏠 Главное меню", callback_data="back_main")]
                ])
            )
        await state.clear()

    except Exception as e:
        logger.error(f"Ошибка при обработке успешной оплаты для пользователя {user_id}: {e}", exc_info=True)
        await message.answer("⚠️ Ошибка при обработке оплаты", reply_markup=None)


async def process_successful_payment(bot: Bot, user_id: int, order_id: int, cart_items: list):
    try:
        logger.info(f"🚀 Обработка успешной оплаты для пользователя {user_id}, заказ {order_id}")
        documents = []
        generation_errors = []

        for item in cart_items:
            template_name = item.get('template_name', '')
            price_type = item.get('price_type', 'template')
            doc_name = item.get('doc_name', 'Документ')
            logger.info(f"📄 Генерация документа: шаблон={template_name}, тип={price_type}")

            if price_type == "template":
                file_type = "sample"
                filled_data = {}
            else:
                file_type = "autogen"
                filled_data = item.get('filled_data', {})
                if not filled_data:
                    logger.error(f"❌ filled_data для шаблона {template_name} не найдены. Пропускаем генерацию.")
                    generation_errors.append(f"Данные для {doc_name} не найдены.")
                    continue

            document_paths = generate_document(
                template_name=template_name,
                answers=filled_data,
                user_id=user_id,
                file_type=file_type
            )

            if document_paths:
                update_order_status(
                    order_id,
                    "paid",
                    pdf_path=document_paths.get('pdf'),
                    docx_path=document_paths.get('docx')
                )
                documents.append({
                    'pdf': document_paths.get('pdf'),
                    'docx': document_paths.get('docx'),
                    'name': doc_name
                })
                logger.info(f"✅ Документ успешно сгенерирован: {doc_name}")
            else:
                error_msg = f"Ошибка генерации документа: {doc_name}"
                logger.error(error_msg)
                generation_errors.append(error_msg)

        if not documents:
            logger.error("❌ Не удалось сгенерировать ни одного документа")
            update_order_status(order_id, "failed")
            error_text = "⚠️ <b>Ошибка генерации документов</b>\n"
            if generation_errors:
                error_text += "Причины:\n" + "\n".join(f"• {err}" for err in generation_errors)
            error_text += "\nОбратитесь в поддержку: @biz_annet"
            await bot.send_message(chat_id=user_id, text=error_text, parse_mode="HTML")
            return False

        success = await send_generated_documents(bot, user_id, documents, order_id)
        if success:
            # ✅ Отправка уведомления через notifications.py
            order = get_order_by_id(order_id)
            total_price = order['total_price'] if order else sum(item.get('price', 0) for item in cart_items)
            discounted_price = order['discounted_price'] if order else total_price
            promocode = order['promocode'] if order else None

            await notify_support_about_new_order(
                bot=bot,
                order_id=order_id,
                user_id=user_id,
                cart_items=cart_items,
                total_price=total_price,
                discounted_price=discounted_price,
                promocode=promocode
            )

            # Отправка управления документами
            buttons = [[InlineKeyboardButton(text="⭐ Оставить отзыв", callback_data="reviews")]]
            for i, doc in enumerate(documents, 1):
                if doc.get('pdf'):
                    buttons.append([InlineKeyboardButton(text=f"🔄 {doc['name']} (PDF)", callback_data=f"download_pdf_{i}")])
                if doc.get('docx'):
                    buttons.append([InlineKeyboardButton(text=f"🔄 {doc['name']} (DOCX)", callback_data=f"download_docx_{i}")])
            buttons.append([InlineKeyboardButton(text="📤 Отправить все документы повторно", callback_data="send_all_documents")])
            buttons.append([InlineKeyboardButton(text="🏠 Главное меню", callback_data="back_main")])
            markup = InlineKeyboardMarkup(inline_keyboard=buttons)

            await bot.send_message(
                chat_id=user_id,
                text=(
                    "📋 <b>Управление документами</b>\n"
                    "Здесь вы можете скачать документы заново.\n\n"
                    "<b>Поделитесь впечатлением - оставьте отзыв! 👇😊</b>"
                ),
                parse_mode="HTML",
                reply_markup=markup
            )
        return success

    except Exception as e:
        logger.error(f"Ошибка при обработке успешной оплаты: {e}", exc_info=True)
        return False


async def send_generated_documents(bot: Bot, user_id: int, documents: list, order_id: int = None):
    try:
        logger.info(f"Начинаем отправку документов пользователю {user_id}")
        if not documents:
            logger.warning("Нет документов для отправки")
            return False

        sent_count = 0
        for i, doc in enumerate(documents, 1):
            doc_name = doc.get('name', f'Документ {i}')
            if doc.get('pdf') and os.path.exists(doc['pdf']):
                try:
                    await bot.send_document(
                        chat_id=user_id,
                        document=FSInputFile(path=doc['pdf'], filename=f"{doc_name}.pdf"),
                        caption=f"📄 {doc_name} (PDF)"
                    )
                    sent_count += 1
                except Exception as e:
                    logger.error(f"Ошибка отправки PDF: {e}")
            if doc.get('docx') and os.path.exists(doc['docx']):
                try:
                    await bot.send_document(
                        chat_id=user_id,
                        document=FSInputFile(path=doc['docx'], filename=f"{doc_name}.docx"),
                        caption=f"📄 {doc_name} (DOCX)"
                    )
                    sent_count += 1
                except Exception as e:
                    logger.error(f"Ошибка отправки DOCX: {e}")

        if sent_count > 0:
            await bot.send_message(
                chat_id=user_id,
                text=f"✅ <b>Документы доставлены!</b>\n"
                     f"Отправлено файлов: {sent_count}\n"
                     f"Заказ №{order_id or 'N/A'}\n"
                     f"Если у вас есть вопросы, обращайтесь в поддержку: @biz_annet",
                parse_mode="HTML"
            )
            logger.info(f"Отправлено {sent_count} документов пользователю {user_id}")
            return True
        else:
            logger.error("Не удалось отправить ни одного документа")
            await bot.send_message(chat_id=user_id, text="⚠️ Не удалось отправить документы. Обратитесь в поддержку: @biz_annet")
            return False
    except Exception as e:
        logger.error(f"Ошибка при отправке документов: {e}", exc_info=True)
        return False