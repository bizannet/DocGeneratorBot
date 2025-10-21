import logging
import os
import uuid
import json
import sqlite3
from datetime import datetime, timedelta
from typing import Dict, Any, Optional, List
from database.promocodes import apply_promocode
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
from database.cart import get_user_cart, clear_cart, get_cart_total, get_cart_items
from database.users import get_user_by_id, get_partner_stats, use_partner_points
from database.payments import create_payment, update_payment_status
from payment.yookassa_integration import (
    create_payment as create_yookassa_payment,
    check_payment_status
)
from services.document_generator import generate_document
from texts.messages import (
    CHECKOUT_TEXT,
    PAYMENT_SUCCESS_TEXT,
    PARTIAL_PAYMENT_TEXT,
    FULL_PAYMENT_TEXT,
    YOOKASSA_PAYMENT_TEXT,
    CHECK_PAYMENT_TEXT,
    CART_EMPTY_TEXT,
    PROMOCODE_APPLIED_TEXT,
    PROMOCODE_ERROR_TEXT
)
from services.pricing import get_simple_total_price
logger = logging.getLogger('doc_bot.payment')
router = Router(name="payment_router")
class PaymentStates(StatesGroup):
    WAITING_FOR_PAYMENT = State()
    PARTIAL_PAYMENT = State()
    CONFIRM_PARTIAL_PAYMENT = State()
    CHECKING_PAYMENT = State()
class PromocodeStates(StatesGroup):
    WAITING_FOR_PROMOCODE = State()
def safe_get_row_value(row, key: str, default=None):
    """Безопасное получение значения из sqlite3.Row"""
    try:
        if hasattr(row, key):
            return getattr(row, key)
        elif hasattr(row, 'keys') and key in row.keys():
            return row[key]
        else:
            return default
    except (KeyError, AttributeError):
        return default
# ========== ДИАГНОСТИЧЕСКИЕ ФУНКЦИИ ==========
def get_db_connection():
    """Получает соединение с базой данных"""
    try:
        conn = sqlite3.connect(str(config.DATABASE_PATH))
        conn.row_factory = sqlite3.Row
        return conn
    except Exception as e:
        logger.error(f"Ошибка подключения к БД: {e}")
        return None
def get_table_columns(table_name: str) -> List[str]:
    """Получает список колонок таблицы"""
    try:
        conn = get_db_connection()
        if not conn:
            return []
        cursor = conn.cursor()
        cursor.execute(f"PRAGMA table_info({table_name})")
        columns = [row[1] for row in cursor.fetchall()]
        conn.close()
        logger.info(f"Колонки таблицы {table_name}: {columns}")
        return columns
    except Exception as e:
        logger.error(f"Ошибка получения колонок таблицы {table_name}: {e}")
        return []
def table_exists(table_name: str) -> bool:
    """Проверяет существование таблицы"""
    try:
        conn = get_db_connection()
        if not conn:
            return False
        cursor = conn.cursor()
        cursor.execute("""
            SELECT name FROM sqlite_master 
            WHERE type='table' AND name=?
        """, (table_name,))
        result = cursor.fetchone()
        conn.close()
        exists = result is not None
        logger.info(f"Таблица {table_name} {'существует' if exists else 'не существует'}")
        return exists
    except Exception as e:
        logger.error(f"Ошибка проверки таблицы {table_name}: {e}")
        return False
# ========== АДАПТИВНЫЕ ФУНКЦИИ ==========
def get_order_items_adaptive(order_id: int):
    """
    АДАПТИВНАЯ ФУНКЦИЯ: Работает с любой структурой БД
    """
    try:
        conn = get_db_connection()
        if not conn:
            return []
        cursor = conn.cursor()
        # Проверяем существование таблицы order_items
        if table_exists('order_items'):
            # Получаем структуру таблицы order_items
            columns = get_table_columns('order_items')
            # Формируем запрос на основе доступных колонок
            select_fields = ['id', 'order_id']
            # Добавляем поля, если они есть
            for field in ['doc_id', 'doc_name', 'name', 'price', 'filled_data', 'template_name', 'created_at']:
                if field in columns:
                    select_fields.append(field)
            query = f"SELECT {', '.join(select_fields)} FROM order_items WHERE order_id = ?"
            logger.info(f"Запрос к order_items: {query}")
            cursor.execute(query, (order_id,))
            items = cursor.fetchall()
            logger.info(f"Найдено {len(items)} элементов в order_items для заказа {order_id}")
        else:
            # Таблица order_items не существует, используем cart_items
            logger.warning("Таблица order_items не найдена")
            items = []
        conn.close()
        return items
    except Exception as e:
        logger.error(f"Ошибка получения элементов заказа {order_id}: {e}")
        return []
def get_cart_items_adaptive(user_id: int, template_name: str = None) -> List:

    try:
        conn = get_db_connection()
        if not conn:
            return []
        cursor = conn.cursor()
        if not table_exists('cart_items'):
            logger.error("Таблица cart_items не существует")
            return []
        columns = get_table_columns('cart_items')
        logger.info(f"Доступные колонки в cart_items: {columns}")
        select_fields = ['id', 'user_id']
        field_mapping = {
            'doc_name': 'doc_name',
            'name': 'doc_name',
            'filled_data': 'filled_data',
            'answers': 'filled_data',
            'template_name': 'template_name',
            'template': 'template_name',
            'price': 'price',
            'created_at': 'created_at'
        }
        available_fields = {}
        for db_field, logical_field in field_mapping.items():
            if db_field in columns:
                select_fields.append(f"{db_field} as {logical_field}")
                available_fields[logical_field] = db_field
        # Формируем WHERE условие
        where_parts = ["user_id = ?"]
        params = [user_id]
        if template_name and 'template_name' in available_fields:
            where_parts.append(f"{available_fields['template_name']} = ?")
            params.append(template_name)
        query = f"SELECT {', '.join(select_fields)} FROM cart_items WHERE {' AND '.join(where_parts)} ORDER BY created_at DESC"
        logger.info(f"Запрос к cart_items: {query} с параметрами: {params}")
        cursor.execute(query, params)
        items = cursor.fetchall()
        logger.info(f"Найдено {len(items)} элементов в cart_items")
        conn.close()
        return items
    except Exception as e:
        logger.error(f"Ошибка получения элементов корзины: {e}")
        return []
async def get_filled_data_from_cart_adaptive(user_id: int, template_name: str) -> Dict[str, Any]:

    try:
        items = get_cart_items_adaptive(user_id, template_name)
        if not items:
            logger.warning(f"Нет элементов в корзине для пользователя {user_id} и шаблона {template_name}")
            return {}
        item = items[0]
        filled_data_raw = safe_get_row_value(item, 'filled_data')
        if not filled_data_raw:
            filled_data_raw = safe_get_row_value(item, 'answers')
        if not filled_data_raw:
            logger.warning(f"filled_data не найдены в корзине для {template_name}")
            return {}
        if isinstance(filled_data_raw, str):
            try:
                filled_data = json.loads(filled_data_raw)
            except json.JSONDecodeError as e:
                logger.error(f"Ошибка парсинга JSON: {e}")
                return {}
        else:
            filled_data = filled_data_raw
        logger.info(f"✅ Данные восстановлены из корзины для {template_name}: {len(filled_data)} полей")
        return filled_data
    except Exception as e:
        logger.error(f"Ошибка восстановления из корзины: {e}")
        return {}
async def get_filled_data_from_order_adaptive(order_id: int) -> Dict[str, Any]:
    try:
        items = get_order_items_adaptive(order_id)
        if not items:
            logger.warning(f"Нет элементов в заказе {order_id}")
            return {}
        for item in items:
            filled_data_raw = safe_get_row_value(item, 'filled_data')
            if not filled_data_raw:
                filled_data_raw = safe_get_row_value(item, 'answers')
            if filled_data_raw:
                if isinstance(filled_data_raw, str):
                    try:
                        filled_data = json.loads(filled_data_raw)
                        logger.info(f"✅ Данные восстановлены из заказа {order_id}: {len(filled_data)} полей")
                        return filled_data
                    except json.JSONDecodeError as e:
                        logger.error(f"Ошибка парсинга JSON: {e}")
                        continue
                else:
                    logger.info(f"✅ Данные восстановлены из заказа {order_id}: {len(filled_data_raw)} полей")
                    return filled_data_raw
        logger.warning(f"filled_data не найдены в заказе {order_id}")
        return {}
    except Exception as e:
        logger.error(f"Ошибка получения filled_data из заказа {order_id}: {e}")
        return {}
async def get_filled_data_ultimate(user_id: int, order_id: int, template_name: str) -> Dict[str, Any]:
    logger.info(f"🔍 Начинаем поиск данных для пользователя {user_id}, заказа {order_id}, шаблона {template_name}")
    filled_data = await get_filled_data_from_order_adaptive(order_id)
    if filled_data:
        logger.info("✅ Данные найдены в заказе")
        return filled_data
    filled_data = await get_filled_data_from_cart_adaptive(user_id, template_name)
    if filled_data:
        logger.info("✅ Данные найдены в корзине по шаблону")
        return filled_data
    items = get_cart_items_adaptive(user_id)
    for item in items:
        filled_data_raw = safe_get_row_value(item, 'filled_data') or safe_get_row_value(item, 'answers')
        if filled_data_raw:
            try:
                if isinstance(filled_data_raw, str):
                    filled_data = json.loads(filled_data_raw)
                else:
                    filled_data = filled_data_raw
                if filled_data:
                    logger.info("✅ Данные найдены в последних элементах корзины")
                    return filled_data
            except:
                continue
    try:
        conn = get_db_connection()
        if conn:
            cursor = conn.cursor()
            tables_to_check = ['cart_items', 'order_items', 'user_data', 'form_data']
            for table in tables_to_check:
                if table_exists(table):
                    try:
                        cursor.execute(f"SELECT * FROM {table} WHERE user_id = ? ORDER BY created_at DESC LIMIT 5",
                                       (user_id,))
                        rows = cursor.fetchall()
                        for row in rows:
                            for column in row.keys():
                                if 'data' in column.lower() or 'answer' in column.lower():
                                    data_raw = row[column]
                                    if data_raw:
                                        try:
                                            if isinstance(data_raw, str):
                                                filled_data = json.loads(data_raw)
                                            else:
                                                filled_data = data_raw
                                            if filled_data and len(filled_data) > 0:
                                                logger.info(f"✅ Данные найдены в таблице {table}, колонке {column}")
                                                conn.close()
                                                return filled_data
                                        except:
                                            continue
                    except:
                        continue
            conn.close()
    except Exception as e:
        logger.error(f"Ошибка при глубоком поиске: {e}")
    logger.error("❌ Данные не найдены нигде")
    return {}
def get_user_balance_alt(user_id: int) -> float:
    try:
        partner_stats = get_partner_stats(user_id)
        if partner_stats and 'available_points' in partner_stats:
            balance = partner_stats['available_points']
            logger.info(f"Баланс пользователя {user_id} получен через partner_stats: {balance}")
            return float(balance)
        conn = get_db_connection()
        if not conn:
            return 0.0
        cursor = conn.cursor()
        for balance_field in ['balance', 'points', 'available_points']:
            try:
                cursor.execute(f"SELECT {balance_field} FROM users WHERE id = ?", (user_id,))
                result = cursor.fetchone()
                if result and result[0] is not None:
                    balance = float(result[0])
                    logger.info(f"Баланс пользователя {user_id} найден в поле {balance_field}: {balance}")
                    conn.close()
                    return balance
            except sqlite3.OperationalError:
                continue
        conn.close()
        logger.warning(f"Баланс пользователя {user_id} не найден, возвращаем 0")
        return 0.0
    except Exception as e:
        logger.error(f"Ошибка получения баланса пользователя {user_id}: {e}")
        return 0.0
def update_user_balance_alt(user_id: int, new_balance: float) -> bool:
    try:
        conn = get_db_connection()
        if not conn:
            return False
        cursor = conn.cursor()
        for balance_field in ['balance', 'points', 'available_points']:
            try:
                cursor.execute(f"UPDATE users SET {balance_field} = ? WHERE id = ?", (new_balance, user_id))
                if cursor.rowcount > 0:
                    conn.commit()
                    conn.close()
                    logger.info(f"Баланс пользователя {user_id} обновлен в поле {balance_field}: {new_balance}")
                    return True
            except sqlite3.OperationalError:
                continue
        conn.close()
        logger.error(f"Не удалось обновить баланс пользователя {user_id} - поле не найдено")
        return False
    except Exception as e:
        logger.error(f"Ошибка обновления баланса пользователя {user_id}: {e}")
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
            # Отправляем PDF
            if doc.get('pdf') and os.path.exists(doc['pdf']):
                try:
                    await bot.send_document(
                        chat_id=user_id,
                        document=FSInputFile(
                            path=doc['pdf'],
                            filename=f"{doc_name}.pdf"
                        ),
                        caption=f"📄 {doc_name} (PDF)"
                    )
                    sent_count += 1
                    logger.info(f"PDF документ отправлен: {doc['pdf']}")
                except Exception as e:
                    logger.error(f"Ошибка отправки PDF: {e}")
            # Отправляем DOCX
            if doc.get('docx') and os.path.exists(doc['docx']):
                try:
                    await bot.send_document(
                        chat_id=user_id,
                        document=FSInputFile(
                            path=doc['docx'],
                            filename=f"{doc_name}.docx"
                        ),
                        caption=f"📄 {doc_name} (DOCX)"
                    )
                    sent_count += 1
                    logger.info(f"DOCX документ отправлен: {doc['docx']}")
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
            await bot.send_message(
                chat_id=user_id,
                text="⚠️ Не удалось отправить документы. Обратитесь в поддержку: @biz_annet"
            )
            return False
    except Exception as e:
        logger.error(f"Ошибка при отправке документов: {e}", exc_info=True)
        return False

async def process_successful_payment(bot: Bot, user_id: int, order_id: int, cart_items: list):
    try:
        logger.info(f"🚀 Обработка успешной оплаты для пользователя {user_id}, заказ {order_id}")
        documents = []
        generation_errors = []
        for item in cart_items:
            template_name = item.get('template_name', '')
            price_type = item.get('price_type', 'template')
            filled_data = item.get('filled_data', {})
            doc_name = item.get('doc_name', 'Документ')
            logger.info(
                f"📄 Генерация документа: шаблон={template_name}, тип={price_type}, данные={len(filled_data)} полей")
            if price_type == "template":
                logger.info(f"ℹ️ Шаблон {template_name} — простой шаблон (без данных)")
                file_type = "sample"
                filled_data = {}
            else:
                file_type = "autogen"
                if not filled_data:
                    logger.warning(f"⚠️ filled_data пустые для шаблона {template_name}")
                    filled_data = await get_filled_data_ultimate(user_id, order_id, template_name)
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
            if config.SUPPORT_CHAT_ID:
                try:
                    items_list = "\n".join([
                        f"• {item.get('doc_name', 'Документ')} — {item.get('price', 0)} ₽"
                        for item in cart_items
                    ])
                    order = get_order_by_id(order_id)
                    if order:
                        total_price = order['total_price']
                        discounted_price = order['discounted_price'] or total_price
                        savings = order['savings'] or 0
                        promocode = order['promocode']
                    else:
                        total_price = sum(item.get('price', 0) for item in cart_items)
                        discounted_price = total_price
                        savings = 0
                        promocode = None
                    promo_info = f"\n🎟 Промокод: {promocode}" if promocode else ""
                    admin_msg = (
                        f"✅ <b>ОПЛАТА УСПЕШНА!</b>\n\n"
                        f"👤 Пользователь: <a href='tg://user?id={user_id}'>{user_id}</a>\n"
                        f"📦 Заказ №{order_id}\n"
                        f"🛒 Товары:\n{items_list}\n"
                        f"💰 Итого: {total_price} ₽\n"
                        f"💸 Скидка: {savings} ₽{promo_info}\n"
                        f"✅ Оплачено: {discounted_price} ₽"
                    )
                    await bot.send_message(
                        chat_id=config.SUPPORT_CHAT_ID,
                        text=admin_msg,
                        parse_mode="HTML"
                    )
                except Exception as e:
                    logger.error(f"Не удалось отправить уведомление об оплате в админ-чат: {e}")

            buttons = [
                [InlineKeyboardButton(text="⭐ Оставить отзыв", callback_data="reviews")]
            ]
            for i, doc in enumerate(documents, 1):
                if doc.get('pdf'):
                    buttons.append([
                        InlineKeyboardButton(
                            text=f"🔄 {doc['name']} (PDF)",
                            callback_data=f"download_pdf_{i}"
                        )
                    ])
                if doc.get('docx'):
                    buttons.append([
                        InlineKeyboardButton(
                            text=f"🔄 {doc['name']} (DOCX)",
                            callback_data=f"download_docx_{i}"
                        )
                    ])
            buttons.append([
                InlineKeyboardButton(
                    text="📤 Отправить все документы повторно",
                    callback_data="send_all_documents"
                )
            ])
            buttons.append([
                InlineKeyboardButton(
                    text="🏠 Главное меню",
                    callback_data="back_main"
                )
            ])
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

@router.callback_query(F.data == "checkout")
async def start_checkout(callback: CallbackQuery, state: FSMContext):
    """Начинает процесс оформления заказа"""
    user_id = callback.from_user.id
    logger.info(f"Пользователь {user_id} начал оформление заказа")
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
        total_price = get_cart_total(user_id)
        # Проверяем, есть ли примененный промокод
        promocode_data = await state.get_data()
        applied_promocode = promocode_data.get('applied_promocode')
        discount = promocode_data.get('discount', 0)
        # Рассчитываем итоговую стоимость с учетом скидки
        discounted_price = total_price * (1 - discount / 100) if discount > 0 else total_price
        await state.update_data(
            cart_items=cart['items'],
            total_price=total_price,
            discounted_price=discounted_price,
            item_count=cart['item_count'],
            promocode=applied_promocode
        )
        # Формируем текст с информацией о промокоде
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
            InlineKeyboardButton(
                text="💳 Оплатить через ЮKassa",
                callback_data="pay_with_yookassa"
            )
        ])
        # Добавляем кнопку для ввода промокода
        buttons.append([
            InlineKeyboardButton(
                text="🎟 Ввести промокод",
                callback_data="enter_promocode"
            )
        ])
        buttons.append([
            InlineKeyboardButton(
                text="⬅️ Назад в корзину",
                callback_data="view_cart"
            )
        ])
        markup = InlineKeyboardMarkup(inline_keyboard=buttons)
        await callback.message.edit_text(
            text=checkout_text,
            parse_mode="HTML",
            reply_markup=markup
        )
        await callback.answer()
    except Exception as e:
        logger.error(f"Ошибка при оформлении заказа: {e}", exc_info=True)
        await callback.answer("⚠️ Произошла ошибка при оформлении заказа", show_alert=True)
@router.callback_query(F.data == "enter_promocode")
async def enter_promocode(callback: CallbackQuery, state: FSMContext):
    """Запрашивает у пользователя ввод промокода"""
    await callback.message.edit_text(
        "Введите промокод:",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="⬅️ Назад",
                    callback_data="checkout"
                )
            ]
        ])
    )
    await state.set_state(PromocodeStates.WAITING_FOR_PROMOCODE)
    await callback.answer()
@router.message(PromocodeStates.WAITING_FOR_PROMOCODE)
async def process_promocode(message: Message, state: FSMContext):
    """Обрабатывает введенный промокод"""
    user_id = message.from_user.id
    promocode = message.text.strip().upper()
    logger.info(f"Пользователь {user_id} ввел промокод: {promocode}")
    data = await state.get_data()
    total_price = data.get('total_price', 0)
    from database.promocodes import check_promocode
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
            [
                InlineKeyboardButton(
                    text="💳 Оплатить через ЮKassa",
                    callback_data="pay_with_yookassa"
                )
            ],
            [
                InlineKeyboardButton(
                    text="🎟 Ввести другой промокод",
                    callback_data="enter_promocode"
                )
            ],
            [
                InlineKeyboardButton(
                    text="⬅️ Назад в корзину",
                    callback_data="view_cart"
                )
            ]
        ]
        markup = InlineKeyboardMarkup(inline_keyboard=buttons)
        await message.answer(
            text=promo_applied_text,
            parse_mode="HTML"
        )
        await message.answer(
            text=checkout_text,
            parse_mode="HTML",
            reply_markup=markup
        )
        await state.set_state(None)
    else:
        await message.answer(
            PROMOCODE_ERROR_TEXT,
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [
                    InlineKeyboardButton(
                        text="⬅️ Назад",
                        callback_data="checkout"
                    )
                ]
            ])
        )
@router.callback_query(F.data == "pay_with_yookassa")
async def pay_with_yookassa(callback: CallbackQuery, state: FSMContext):
    user_id = callback.from_user.id
    logger.info(f"Пользователь {user_id} выбрал оплату через ЮKassa")
    try:
        data = await state.get_data()
        total_price = data.get('total_price', 0)
        discounted_price = data.get('discounted_price', total_price)
        promocode = data.get('applied_promocode')
        discount = data.get('discount', 0)
        # Рассчитываем экономию
        savings = total_price - discounted_price
        order_id = create_order(
            user_id=user_id,
            total_price=total_price,
            discounted_price=discounted_price,
            promocode=promocode,
            item_count=data['item_count'],
            savings=savings
        )
        if not order_id:
            await callback.answer("⚠️ Не удалось создать заказ", show_alert=True)
            return

        # Добавляем элементы заказа
        for item in data['cart_items']:
            doc_id = item.get('doc_id', item.get('id', 0))
            doc_name = item.get('doc_name', item.get('name', 'Неизвестный документ'))
            price = item.get('price', 0)
            # Сохраняем price_type в заказе
            add_order_item(
                order_id=order_id,
                doc_id=doc_id,
                doc_name=doc_name,
                price=price,
                filled_data=item.get('filled_data', {}),
                price_type=item.get('price_type', "template")
            )
        # Если был применен промокод, записываем его использование
        if promocode:
            apply_promocode(promocode, user_id, order_id)
        payment_id = create_payment(
            user_id=user_id,
            order_id=order_id,
            amount=discounted_price,  # Используем цену со скидкой
            payment_system="yookassa",
            status="pending"
        )
        if not payment_id:
            await callback.answer("⚠️ Не удалось создать платеж", show_alert=True)
            return
        description = f"Оплата заказа #{order_id}"
        payment = create_yookassa_payment(
            amount=discounted_price,
            description=description,
            user_id=user_id
        )
        if not payment:
            await callback.answer("⚠️ Не удалось создать платеж в ЮKassa", show_alert=True)
            return
        await state.update_data(
            yookassa_payment_id=payment.id,
            order_id=order_id
        )
        payment_text = YOOKASSA_PAYMENT_TEXT.format(
            total_price=discounted_price  # Используем цену со скидкой
        )
        markup = InlineKeyboardMarkup(inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="💳 Перейти к оплате",
                    url=payment.confirmation.confirmation_url
                )
            ],
            [
                InlineKeyboardButton(
                    text="🔄 Проверить оплату",
                    callback_data="check_payment"
                )
            ],
            [
                InlineKeyboardButton(
                    text="🏠 Главное меню",
                    callback_data="back_main"
                )
            ]
        ])
        await callback.message.edit_text(
            text=payment_text,
            parse_mode="HTML",
            reply_markup=markup
        )
        await state.set_state(PaymentStates.CHECKING_PAYMENT)
        await callback.answer()
    except Exception as e:
        logger.error(f"Ошибка при начале оплаты через ЮKassa: {e}", exc_info=True)
        await callback.answer("⚠️ Произошла ошибка при начале оплаты", show_alert=True)


@router.callback_query(F.data == "check_payment")
async def check_payment(callback: CallbackQuery, state: FSMContext):
    user_id = callback.from_user.id
    logger.info(f"Пользователь {user_id} проверяет статус платежа")
    try:
        data = await state.get_data()
        yookassa_payment_id = data.get('yookassa_payment_id')
        order_id = data.get('order_id')
        if not yookassa_payment_id or not order_id:
            await callback.answer("⚠️ Не удалось найти платеж", show_alert=True)
            return
        status = check_payment_status(yookassa_payment_id)
        logger.info(f"Payment {yookassa_payment_id} status: {status}")
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
                "❌ Оплата была отменена.\n"
                "Вы можете оформить заказ заново.",
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
            await state.clear()
        elif status == "waiting_for_capture":
            await callback.answer("⏳ Платеж ожидает подтверждения", show_alert=True)
        else:
            await callback.answer(f"ℹ️ Текущий статус платежа: {status}", show_alert=True)
        await callback.answer()
    except Exception as e:
        logger.error(f"Ошибка при проверке платежа: {e}", exc_info=True)
        await callback.answer("⚠️ Произошла ошибка при проверке платежа", show_alert=True)

@router.pre_checkout_query()
async def pre_checkout_query(pre_checkout_q: PreCheckoutQuery):
    """Обрабатывает предварительный запрос на оплату"""
    logger.info(f"Получен предварительный запрос на оплату от {pre_checkout_q.from_user.id}")
    try:
        await pre_checkout_q.answer(ok=True)
    except Exception as e:
        logger.error(f"Ошибка при обработке предварительного запроса: {e}", exc_info=True)
        await pre_checkout_q.answer(ok=False, error_message="⚠️ Произошла ошибка при обработке платежа")

@router.message(F.content_type == "successful_payment")
async def successful_payment(message: Message, state: FSMContext):
    """Обрабатывает успешную оплату"""
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
            await message.answer("⚠️ Не удалось найти ваш заказ", reply_markup=None)
            return
        update_order_status(order_id, "paid")
        clear_cart(user_id)
        order = get_order_by_id(order_id)
        cart_items = order['items'] if order and 'items' in order else []
        bot = message.bot
        success = await process_successful_payment(
            bot=bot,
            user_id=user_id,
            order_id=order_id,
            cart_items=cart_items
        )
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
        logger.error(f"Ошибка при обработке успешной оплаты: {e}", exc_info=True)
        await message.answer("⚠️ Произошла ошибка при обработке оплаты", reply_markup=None)