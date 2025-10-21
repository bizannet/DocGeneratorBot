import logging
import os
from datetime import datetime
from aiogram import Router, F
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, InputFile
from aiogram.fsm.context import FSMContext
from config import config
from database.orders import get_user_orders, get_order_by_id
from database.templates import get_template_by_id, get_template_by_name
from database.cart import add_to_cart
from database.users import save_user_data, get_user_data
from texts.messages import (
    ORDER_HISTORY_TEXT,
    REVIEW_DATA_TEXT,
    DOCUMENT_DESCRIPTION_TEXT,
    ORDER_DETAILS_TEXT
)
from services.document_generator import generate_document
from services.document_service import get_template_info
from services.file_utils import get_document_path

logger = logging.getLogger('doc_bot.order_history')
router = Router(name="order_history_router")


def format_order_date(date_str):
    try:
        for fmt in ["%Y-%m-%d %H:%M:%S", "%Y-%m-%d"]:
            try:
                date_obj = datetime.strptime(date_str, fmt)
                return date_obj.strftime("%d.%m.%Y")
            except (ValueError, TypeError):
                continue
        return date_str
    except Exception:
        return date_str


def format_order_status(status):
    status_map = {
        'created': 'Создан',
        'pending': 'Ожидает оплаты',
        'paid': 'Оплачен',
        'processing': 'Генерируется',
        'completed': 'Готов',
        'cancelled': 'Отменен',
        'refunded': 'Возврат средств'
    }
    return status_map.get(status, status.capitalize())


def format_order_item(item):
    return f"• {item['doc_name']} — {item['price']} ₽"


def format_order(order):
    order_date = format_order_date(order['created_at'])

    # Форматируем статус
    status = format_order_status(order['status'])

    # Форматируем элементы заказа
    items_text = "\n".join(format_order_item(item) for item in order['items'])

    # Форматируем итоговую сумму
    total = order['total_price']
    if order.get('savings', 0) > 0:
        total_text = f"Итого: <s>{total + order['savings']} ₽</s> <b>{total} ₽</b> (-{order['savings']} ₽)"
    else:
        total_text = f"Итого: <b>{total} ₽</b>"

    # Формируем текст заказа
    order_text = (
        f"📦 <b>Заказ #{order['id']}</b>\n"
        f"📅 Дата: {order_date}\n"
        f"🔄 Статус: {status}\n\n"
        f"{items_text}\n\n"
        f"{total_text}"
    )

    return order_text


@router.callback_query(F.data == "order_history")
async def show_order_history(callback: CallbackQuery):
    """Показывает историю заказов пользователя"""
    user_id = callback.from_user.id
    logger.info(f"Пользователь {user_id} запросил историю заказов")

    try:
        # Получаем заказы пользователя
        orders = get_user_orders(user_id)

        if not orders:
            await callback.message.edit_text(
                "📜 <b>История заказов</b>\n\n"
                "У вас пока нет заказов.\n\n"
                "Начните с выбора документа в каталоге!",
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

        # Формируем текст с историей заказов
        history_text = "📜 <b>История заказов</b>\n\n"

        # Сортируем заказы по дате (новые первыми)
        orders.sort(key=lambda x: x['created_at'], reverse=True)

        # Добавляем последние 10 заказов
        for i, order in enumerate(orders[:10], 1):
            order_date = format_order_date(order['created_at'])
            status = format_order_status(order['status'])
            total = order['total_price']

            history_text += (
                f"{i}. #{order['id']} от {order_date}\n"
                f"   • Статус: {status}\n"
                f"   • Сумма: {total} ₽\n\n"
            )

        if len(orders) > 10:
            history_text += "Показаны последние 10 заказов.\n"

        # Создаем клавиатуру
        buttons = []

        # Добавляем кнопки для каждого заказа
        for order in orders[:5]:  # Только первые 5 заказов для кнопок
            order_date = format_order_date(order['created_at'])
            buttons.append([
                InlineKeyboardButton(
                    text=f"Заказ #{order['id']} от {order_date}",
                    callback_data=f"order_{order['id']}"
                )
            ])

        # Добавляем общие кнопки
        buttons.append([
            InlineKeyboardButton(
                text="🔄 Показать все заказы",
                callback_data="show_all_orders"
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
            text=history_text,
            parse_mode="HTML",
            reply_markup=markup
        )
        await callback.answer()

    except Exception as e:
        logger.error(f"Ошибка при отображении истории заказов: {e}", exc_info=True)
        await callback.answer("⚠️ Произошла ошибка при загрузке истории заказов", show_alert=True)
        await callback.answer()


@router.callback_query(F.data.startswith("order_"))
async def show_order_details(callback: CallbackQuery):
    """Показывает детали конкретного заказа"""
    order_id = int(callback.data.split("_")[1])
    user_id = callback.from_user.id
    logger.info(f"Пользователь {user_id} запросил детали заказа {order_id}")

    try:
        # Получаем заказ
        order = get_order_by_id(order_id)

        if not order or order['user_id'] != user_id:
            await callback.answer("⚠️ Заказ не найден или недоступен", show_alert=True)
            await callback.answer()
            return

        # Форматируем информацию о заказе
        order_date = format_order_date(order['created_at'])
        status = format_order_status(order['status'])
        total = order['total_price']

        # Формируем список документов
        documents_list = ""
        for i, item in enumerate(order['items'], 1):
            documents_list += f"{i}. {item['doc_name']}\n"

        # Форматируем доступные форматы
        formats = "PDF, DOCX"

        # Формируем текст заказа
        order_text = ORDER_DETAILS_TEXT.format(
            order_id=order['id'],
            order_date=order_date,
            status=status,
            formats=formats,
            documents_list=documents_list,
            total_price=total
        )

        # Создаем клавиатуру
        buttons = []

        # Добавляем кнопки для документов
        for i, item in enumerate(order['items'], 1):
            buttons.append([
                InlineKeyboardButton(
                    text=f"📄 {item['doc_name']}",
                    callback_data=f"doc_{item['doc_id']}_order_{order_id}"
                )
            ])

        # Добавляем кнопку повторного заказа (если заказ оплачен)
        if order['status'] == 'completed':
            buttons.append([
                InlineKeyboardButton(
                    text="🔄 Повторить заказ",
                    callback_data=f"reorder_{order_id}"
                )
            ])

        # Добавляем кнопку для скачивания документов
        if order['status'] == 'completed' and len(order['items']) > 0:
            buttons.append([
                InlineKeyboardButton(
                    text="📥 Скачать документы",
                    callback_data=f"download_all_{order_id}"
                )
            ])

        # Добавляем кнопку "Назад"
        buttons.append([
            InlineKeyboardButton(
                text="⬅️ Назад к истории",
                callback_data="order_history"
            )
        ])

        markup = InlineKeyboardMarkup(inline_keyboard=buttons)

        await callback.message.edit_text(
            text=order_text,
            parse_mode="HTML",
            reply_markup=markup
        )
        await callback.answer()

    except Exception as e:
        logger.error(f"Ошибка при отображении деталей заказа: {e}", exc_info=True)
        await callback.answer("⚠️ Произошла ошибка при загрузке деталей заказа", show_alert=True)
        await callback.answer()


@router.callback_query(F.data.startswith("doc_") & F.data.contains("_order_"))
async def show_order_document_options(callback: CallbackQuery):
    """Показывает опции для документа из заказа"""
    try:
        parts = callback.data.split("_")
        doc_id = int(parts[1])
        order_id = int(parts[3])

        # Получаем документ
        doc = get_template_by_id(doc_id)
        order = get_order_by_id(order_id)

        if not doc or not order:
            await callback.answer("⚠️ Документ или заказ не найден", show_alert=True)
            await callback.answer()
            return

        # Находим ответы для этого документа в заказе
        answers = None
        for item in order['items']:
            if item['doc_id'] == doc_id:
                answers = item['filled_data']
                break

        if not answers:
            await callback.answer("⚠️ Данные документа не найдены", show_alert=True)
            await callback.answer()
            return

        # Формируем текст с описанием документа
        document_text = DOCUMENT_DESCRIPTION_TEXT.format(
            doc_name=doc['name'],
            description=doc['description'],
            price=doc['price']
        )

        # Создаем клавиатуру с опциями
        markup = InlineKeyboardMarkup(inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="🔍 Просмотреть заполненные данные",
                    callback_data=f"review_{doc_id}_order_{order_id}"
                )
            ],
            [
                InlineKeyboardButton(
                    text="📥 Скачать документ (PDF)",
                    callback_data=f"download_pdf_{doc_id}_order_{order_id}"
                ),
                InlineKeyboardButton(
                    text="📥 Скачать документ (DOCX)",
                    callback_data=f"download_docx_{doc_id}_order_{order_id}"
                )
            ],
            [
                InlineKeyboardButton(
                    text="🔄 Создать новый документ",
                    callback_data=f"new_doc_{doc_id}"
                )
            ],
            [
                InlineKeyboardButton(
                    text="⬅️ Назад к заказу",
                    callback_data=f"order_{order_id}"
                )
            ]
        ])

        await callback.message.edit_text(
            text=document_text,
            parse_mode="HTML",
            reply_markup=markup
        )
        await callback.answer()

    except Exception as e:
        logger.error(f"Ошибка при показе опций документа из заказа: {e}", exc_info=True)
        await callback.answer("⚠️ Произошла ошибка", show_alert=True)
        await callback.answer()


@router.callback_query(F.data.startswith("review_") & F.data.contains("_order_"))
async def review_order_document(callback: CallbackQuery):
    """Показывает заполненные данные документа из заказа"""
    try:
        parts = callback.data.split("_")
        doc_id = int(parts[1])
        order_id = int(parts[3])

        # Получаем документ и заказ
        doc = get_template_by_id(doc_id)
        order = get_order_by_id(order_id)

        if not doc or not order:
            await callback.answer("⚠️ Документ или заказ не найден", show_alert=True)
            await callback.answer()
            return

        # Находим ответы для этого документа в заказе
        answers = None
        for item in order['items']:
            if item['doc_id'] == doc_id:
                answers = item['filled_data']
                break

        if not answers:
            await callback.answer("⚠️ Данные документа не найдены", show_alert=True)
            await callback.answer()
            return

        # Форматируем ответы для отображения
        formatted_answers = ""
        for key, value in answers.items():
            formatted_answers += f"• {key}: {value}\n"

        # Формируем текст с заполненными данными
        review_text = REVIEW_DATA_TEXT.format(
            doc_name=doc['name'],
            answers=formatted_answers
        )

        # Создаем клавиатуру
        markup = InlineKeyboardMarkup(inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="📥 Скачать документ (PDF)",
                    callback_data=f"download_pdf_{doc_id}_order_{order_id}"
                ),
                InlineKeyboardButton(
                    text="📥 Скачать документ (DOCX)",
                    callback_data=f"download_docx_{doc_id}_order_{order_id}"
                )
            ],
            [
                InlineKeyboardButton(
                    text="🔄 Создать новый документ",
                    callback_data=f"new_doc_{doc_id}"
                )
            ],
            [
                InlineKeyboardButton(
                    text="⬅️ Назад",
                    callback_data=f"doc_{doc_id}_order_{order_id}"
                )
            ]
        ])

        await callback.message.edit_text(
            text=review_text,
            parse_mode="HTML",
            reply_markup=markup
        )
        await callback.answer()

    except Exception as e:
        logger.error(f"Ошибка при просмотре данных документа из заказа: {e}", exc_info=True)
        await callback.answer("⚠️ Произошла ошибка при просмотре данных", show_alert=True)
        await callback.answer()


@router.callback_query(F.data.startswith("download_pdf_") & F.data.contains("_order_"))
async def download_pdf_document(callback: CallbackQuery):
    """Позволяет скачать PDF документ из заказа"""
    await download_order_document(callback, "pdf")


@router.callback_query(F.data.startswith("download_docx_") & F.data.contains("_order_"))
async def download_docx_document(callback: CallbackQuery):
    """Позволяет скачать DOCX документ из заказа"""
    await download_order_document(callback, "docx")


async def download_order_document(callback: CallbackQuery, format_type: str = "pdf"):
    """Позволяет скачать документ из заказа в указанном формате"""
    try:
        # Определяем тип документа из callback_data
        if format_type == "pdf" and "download_pdf_" in callback.data:
            parts = callback.data.replace("download_pdf_", "").split("_")
        elif format_type == "docx" and "download_docx_" in callback.data:
            parts = callback.data.replace("download_docx_", "").split("_")
        else:
            parts = callback.data.split("_")

        doc_id = int(parts[0])
        order_id = int(parts[2])

        # Получаем документ и заказ
        doc = get_template_by_id(doc_id)
        order = get_order_by_id(order_id)

        if not doc or not order:
            await callback.answer("⚠️ Документ или заказ не найден", show_alert=True)
            await callback.answer()
            return

        # Находим ответы для этого документа в заказе
        answers = None
        for item in order['items']:
            if item['doc_id'] == doc_id:
                answers = item['filled_data']
                break

        if not answers:
            await callback.answer("⚠️ Данные документа не найдены", show_alert=True)
            await callback.answer()
            return

        # Проверяем, есть ли уже сгенерированный документ
        document_path = None
        if format_type == "pdf" and order.get('pdf_path'):
            document_path = order['pdf_path']
        elif format_type == "docx" and order.get('docx_path'):
            document_path = order['docx_path']

        # Если документ уже сгенерирован, используем его
        if document_path and os.path.exists(document_path):
            # Отправляем документ
            await callback.message.answer_document(
                document=InputFile(document_path),
                caption=f"Ваш документ: {doc['name']} ({format_type.upper()})"
            )
        else:
            # Генерируем документ
            document_paths = generate_document(
                template_name=doc['template_name'],
                answers=answers
            )

            if not document_paths or not document_paths.get(format_type):
                await callback.answer("⚠️ Не удалось сгенерировать документ", show_alert=True)
                await callback.answer()
                return

            # Отправляем документ
            await callback.message.answer_document(
                document=InputFile(document_paths[format_type]),
                caption=f"Ваш документ: {doc['name']} ({format_type.upper()})"
            )

            # Обновляем путь в заказе
            if format_type == "pdf":
                order['pdf_path'] = document_paths['pdf']
            else:
                order['docx_path'] = document_paths['docx']

        await callback.answer()

    except Exception as e:
        logger.error(f"Ошибка при скачивании документа из заказа: {e}", exc_info=True)
        await callback.answer("⚠️ Произошла ошибка при скачивании документа", show_alert=True)
        await callback.answer()


@router.callback_query(F.data.startswith("download_all_"))
async def download_all_order_documents(callback: CallbackQuery):
    try:
        order_id = int(callback.data.split("_")[2])
        user_id = callback.from_user.id
        order = get_order_by_id(order_id)

        if not order or order['user_id'] != user_id:
            await callback.answer("⚠️ Заказ не найден или недоступен", show_alert=True)
            await callback.answer()
            return

        for item in order['items']:
            doc = get_template_by_id(item['doc_id'])
            if not doc:
                continue

            pdf_path = item.get('pdf_path', '')
            docx_path = item.get('docx_path', '')

            if pdf_path and os.path.exists(pdf_path):
                await callback.message.answer_document(
                    document=InputFile(pdf_path),
                    caption=f"PDF: {doc['name']}"
                )

            if docx_path and os.path.exists(docx_path):
                await callback.message.answer_document(
                    document=InputFile(docx_path),
                    caption=f"DOCX: {doc['name']}"
                )

            if (not pdf_path or not os.path.exists(pdf_path)) and (not docx_path or not os.path.exists(docx_path)):
                # Генерируем документы
                document_paths = generate_document(
                    template_name=doc['template_name'],
                    answers=item['filled_data']
                )

                if document_paths:
                    if document_paths.get('pdf') and os.path.exists(document_paths['pdf']):
                        await callback.message.answer_document(
                            document=InputFile(document_paths['pdf']),
                            caption=f"PDF: {doc['name']}"
                        )

                    if document_paths.get('docx') and os.path.exists(document_paths['docx']):
                        await callback.message.answer_document(
                            document=InputFile(document_paths['docx']),
                            caption=f"DOCX: {doc['name']}"
                        )

        await callback.answer()

    except Exception as e:
        logger.error(f"Ошибка при скачивании всех документов из заказа: {e}", exc_info=True)
        await callback.answer("⚠️ Произошла ошибка при скачивании документов", show_alert=True)
        await callback.answer()


@router.callback_query(F.data.startswith("reorder_"))
async def reorder(callback: CallbackQuery):
    order_id = int(callback.data.split("_")[1])
    user_id = callback.from_user.id
    logger.info(f"Пользователь {user_id} запросил повтор заказа {order_id}")

    try:
        order = get_order_by_id(order_id)

        if not order or order['user_id'] != user_id:
            await callback.answer("⚠️ Заказ не найден или недоступен", show_alert=True)
            await callback.answer()
            return

        for item in order['items']:
            template_info = get_template_info(item['template_name'])
            if template_info and 'price' in template_info and 'autogeneration' in template_info['price']:
                price = template_info['price']['autogeneration']

            # Добавляем в корзину
            add_to_cart(
                user_id=user_id,
                doc_id=item['doc_id'],
                name=item['doc_name'],
                price=price,
                template_name=item['template_name']
            )

            # Сохраняем данные пользователя
            save_user_data(
                user_id=user_id,
                template_name=item['template_name'],
                filled_data=item['filled_data']
            )

        # Формируем сообщение
        success_text = (
            "✅ Заказ добавлен в корзину!\n\n"
            "Вы можете изменить выбор документов или перейти к оформлению заказа."
        )

        # Создаем клавиатуру
        markup = InlineKeyboardMarkup(inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="🛒 Перейти в корзину",
                    callback_data="view_cart"
                )
            ],
            [
                InlineKeyboardButton(
                    text="🛍️ Продолжить покупки",
                    callback_data="catalog"
                )
            ],
            [
                InlineKeyboardButton(
                    text="⬅️ Назад к заказу",
                    callback_data=f"order_{order_id}"
                )
            ]
        ])

        await callback.message.edit_text(
            text=success_text,
            parse_mode="HTML",
            reply_markup=markup
        )
        await callback.answer()

    except Exception as e:
        logger.error(f"Ошибка при повторе заказа: {e}", exc_info=True)
        await callback.answer("⚠️ Произошла ошибка при повторе заказа", show_alert=True)
        await callback.answer()


@router.callback_query(F.data == "show_all_orders")
async def show_all_orders(callback: CallbackQuery):
    """Показывает все заказы пользователя"""
    user_id = callback.from_user.id
    logger.info(f"Пользователь {user_id} запросил все заказы")

    try:
        # Получаем все заказы пользователя
        orders = get_user_orders(user_id)

        if not orders:
            await callback.answer("У вас пока нет заказов", show_alert=True)
            await callback.answer()
            return

        # Формируем текст со всеми заказами
        history_text = "📜 <b>Полная история заказов</b>\n\n"

        # Сортируем заказы по дате (новые первыми)
        orders.sort(key=lambda x: x['created_at'], reverse=True)

        # Добавляем все заказы
        for i, order in enumerate(orders, 1):
            order_date = format_order_date(order['created_at'])
            status = format_order_status(order['status'])
            total = order['total_price']

            history_text += (
                f"{i}. #{order['id']} от {order_date}\n"
                f"   • Статус: {status}\n"
                f"   • Сумма: {total} ₽\n\n"
            )

        # Создаем клавиатуру
        buttons = []

        # Добавляем кнопки для каждого заказа
        for order in orders[:10]:  # Ограничиваем количество кнопок
            order_date = format_order_date(order['created_at'])
            buttons.append([
                InlineKeyboardButton(
                    text=f"Заказ #{order['id']} от {order_date}",
                    callback_data=f"order_{order['id']}"
                )
            ])

        # Добавляем общие кнопки
        buttons.append([
            InlineKeyboardButton(
                text="⬅️ Назад",
                callback_data="order_history"
            )
        ])

        markup = InlineKeyboardMarkup(inline_keyboard=buttons)

        await callback.message.edit_text(
            text=history_text,
            parse_mode="HTML",
            reply_markup=markup
        )
        await callback.answer()

    except Exception as e:
        logger.error(f"Ошибка при отображении всех заказов: {e}", exc_info=True)
        await callback.answer("⚠️ Произошла ошибка при загрузке истории заказов", show_alert=True)
        await callback.answer()