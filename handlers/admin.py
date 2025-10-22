import logging
import json
import re
import datetime
from aiogram import Router, F
from aiogram.types import CallbackQuery, Message, InlineKeyboardButton, InlineKeyboardMarkup
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from config import config
from database.users import (
    get_all_users, get_user_by_id, get_user_referrals, get_partner_stats,
    get_new_users_count, get_news_subscribers
)
from database.orders import (
    get_all_orders, get_order_by_id_full, update_order_status as db_update_order_status,
    get_orders_stats
)
from database.promocodes import (
    get_all_promocodes, get_promocode_by_code, create_promocode as db_create_promocode
)
from database.templates import get_all_templates, create_template as db_create_template
from database.cart import get_cart_items
from services.pricing import (
    get_template_price, get_autogeneration_price, update_price_in_db, get_price_for_type
)
from services.notifications import (
    send_daily_stats_report, send_monthly_stats_report, send_yearly_stats_report
)
from services.file_utils import get_logs_path
from texts.messages import ADMIN_PANEL_TEXT

logger = logging.getLogger('doc_bot.admin')
router = Router(name="admin_router")

class AdminStates(StatesGroup):
    WAITING_FOR_ORDER_SEARCH = State()
    CREATING_TEMPLATE = State()
    ENTERING_TEMPLATE_CATEGORY = State()
    ENTERING_TEMPLATE_PRICE = State()
    CREATING_PROMOCODE = State()
    ENTERING_PROMOCODE_DISCOUNT = State()
    WAITING_FOR_REPLY = State()
    SEARCHING_ORDER = State()
    EDITING_PRICE = State()
    WAITING_FOR_BROADCAST = State()

def is_admin(user_id: int) -> bool:
    try:
        return user_id in config.ADMIN_IDS
    except Exception as e:
        logger.error(f"Ошибка при проверке администратора: {e}")
        return False

def format_admin_stats():
    orders = get_all_orders()
    users = get_all_users()

    # Рассчитываем статистику
    total_orders = len(orders)
    total_users = len(users)

    # Активные заказы
    active_statuses = ['pending', 'processing', 'paid']
    active_orders = sum(1 for order in orders if order['status'] in active_statuses)

    # Общая выручка
    total_revenue = sum(order.get('total_price', 0) for order in orders if order['status'] == 'paid')

    # Новые пользователи за неделю
    week_ago = datetime.datetime.now() - datetime.timedelta(days=7)
    new_users = 0
    for user in users:
        try:
            reg_date_str = user.get('registered_at')
            if reg_date_str:
                reg_date = datetime.datetime.strptime(reg_date_str, "%Y-%m-%d %H:%M:%S")
                if reg_date > week_ago:
                    new_users += 1
        except (ValueError, TypeError) as e:
            logger.warning(f"Ошибка парсинга даты регистрации для пользователя {user.get('id')}: {e}")
            continue

    # Формируем текст статистики
    stats_text = (
        f"📊 <b>Админ-панель</b>\n"
        f"👥 Всего пользователей: <b>{total_users}</b>\n"
        f"🆕 Новых за неделю: <b>{new_users}</b>\n"
        f"📦 Всего заказов: <b>{total_orders}</b>\n"
        f"🔄 Активных заказов: <b>{active_orders}</b>\n"
        f"💰 Общая выручка: <b>{total_revenue:.2f} ₽</b>\n"
        "<i>Выберите раздел для управления:</i>"
    )
    return stats_text

def get_admin_menu():
    buttons = [
        [
            InlineKeyboardButton(text="📊 Статистика", callback_data="admin_stats")
        ],
        [
            InlineKeyboardButton(text="🏷 Управление ценами", callback_data="admin_prices")
        ],
        [
            InlineKeyboardButton(text="📦 Заказы", callback_data="admin_orders"),
            InlineKeyboardButton(text="👥 Пользователи", callback_data="admin_users")
        ],
        [
            InlineKeyboardButton(text="📑 Документы", callback_data="admin_templates"),
            InlineKeyboardButton(text="🎟 Промокоды", callback_data="admin_promocodes")
        ],
        [
            InlineKeyboardButton(text="📤 Рассылка", callback_data="admin_newsletter")
        ],
        [
            InlineKeyboardButton(text="🏠 Вернуться в меню", callback_data="back_main")
        ]
    ]
    return InlineKeyboardMarkup(inline_keyboard=buttons)

def get_stats_menu():
    buttons = [
        [
            InlineKeyboardButton(text="📅 Сегодня", callback_data="stats_daily"),
            InlineKeyboardButton(text="📆 Неделя", callback_data="stats_week")
        ],
        [
            InlineKeyboardButton(text="🗓 Месяц", callback_data="stats_monthly"),
            InlineKeyboardButton(text="🧾 Год", callback_data="stats_yearly")
        ],
        [
            InlineKeyboardButton(text="⬅️ Назад", callback_data="admin_panel")
        ]
    ]
    return InlineKeyboardMarkup(inline_keyboard=buttons)

@router.callback_query(F.data == "admin_panel")
async def admin_panel(callback: CallbackQuery):
    user_id = callback.from_user.id
    logger.info(f"Пользователь {user_id} запросил админ-панель")

    if not is_admin(user_id):
        await callback.answer("⚠️ Доступ запрещен", show_alert=True)
        return

    try:
        stats_text = format_admin_stats()
        markup = get_admin_menu()

        await callback.message.edit_text(
            text=stats_text,
            parse_mode="HTML",
            reply_markup=markup
        )
        await callback.answer()
    except Exception as e:
        logger.error(f"Ошибка при отображении админ-панели: {e}", exc_info=True)
        await callback.answer("⚠️ Произошла ошибка при загрузке админ-панели", show_alert=True)

@router.callback_query(F.data == "admin_stats")
async def admin_stats(callback: CallbackQuery):
    user_id = callback.from_user.id
    logger.info(f"Пользователь {user_id} запросил статистику")

    if not is_admin(user_id):
        await callback.answer("⚠️ Доступ запрещен", show_alert=True)
        return

    try:
        stats_text = (
            "📊 <b>Статистика</b>\n"
            "<i>Выберите период для просмотра:</i>"
        )
        markup = get_stats_menu()

        await callback.message.edit_text(
            text=stats_text,
            parse_mode="HTML",
            reply_markup=markup
        )
        await callback.answer()
    except Exception as e:
        logger.error(f"Ошибка при отображении статистики: {e}", exc_info=True)
        await callback.answer("⚠️ Произошла ошибка при загрузке статистики", show_alert=True)

@router.callback_query(F.data == "admin_orders")
async def admin_orders(callback: CallbackQuery):
    user_id = callback.from_user.id
    logger.info(f"Пользователь {user_id} запросил управление заказами")

    if not is_admin(user_id):
        await callback.answer("⚠️ Доступ запрещен", show_alert=True)
        return

    try: # Добавлен блок try-except
        orders = get_all_orders(limit=10)
        if not orders:
            await callback.message.edit_text(
                "📦 <b>Управление заказами</b>\n"
                "Нет заказов для отображения.",
                parse_mode="HTML",
                reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                    [InlineKeyboardButton(text="🔍 Найти заказ", callback_data="search_order")],
                    [InlineKeyboardButton(text="🔄 Обновить", callback_data="admin_orders")],
                    [InlineKeyboardButton(text="⬅️ Назад", callback_data="admin_panel")]
                ])
            )
            await callback.answer() # Добавлен await callback.answer()
            return

        orders_text = "📦 <b>Последние заказы</b>\n\n"
        for order in orders:
            order_id = order.get('id', 'N/A')
            user_id_order = order.get('user_id', 'N/A')
            status = order.get('status', 'N/A')
            total_price = order.get('total_price', 0)
            orders_text += (
                f"Заказ #{order_id}\n"
                f"Пользователь: {user_id_order}\n"
                f"Статус: {status}\n"
                f"Сумма: {total_price} ₽\n\n"
            )

        markup = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🔍 Найти заказ", callback_data="search_order")],
            [InlineKeyboardButton(text="🔄 Обновить", callback_data="admin_orders")],
            [InlineKeyboardButton(text="⬅️ Назад", callback_data="admin_panel")]
        ])

        await callback.message.edit_text(
            text=orders_text,
            parse_mode="HTML",
            reply_markup=markup
        )
        await callback.answer()
    except Exception as e: # Добавлен блок except
        logger.error(f"Ошибка при отображении заказов: {e}", exc_info=True)
        await callback.answer("⚠️ Произошла ошибка при загрузке заказов", show_alert=True)

@router.callback_query(F.data == "search_order")
async def search_order_start(callback: CallbackQuery, state: FSMContext):
    user_id = callback.from_user.id
    logger.info(f"Пользователь {user_id} начал поиск заказа")

    if not is_admin(user_id):
        await callback.answer("⚠️ Доступ запрещен", show_alert=True)
        return

    await callback.message.edit_text(
        "Введите ID заказа:",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="⬅️ Назад", callback_data="admin_orders")]
        ])
    )
    await state.set_state(AdminStates.SEARCHING_ORDER)
    await callback.answer()

@router.message(AdminStates.SEARCHING_ORDER)
async def search_order_process(message: Message, state: FSMContext):
    user_id = message.from_user.id
    logger.info(f"Пользователь {user_id} ввел ID заказа: {message.text}")

    if not is_admin(user_id):
        await message.answer("⚠️ Доступ запрещен", reply_markup=None)
        return

    try:
        order_id = int(message.text)
    except ValueError:
        await message.answer("⚠️ Некорректный ID заказа", reply_markup=None)
        # Можно вернуться к предыдущему меню или очистить состояние
        await state.clear()
        return

    try:
        order = get_order_by_id_full(order_id)
        if not order:
            await message.answer("⚠️ Заказ не найден", reply_markup=None)
            await state.clear()
            return

        order_text = (
            f"📦 <b>Заказ #{order['id']}</b>\n"
            f"Пользователь: {order['user_id']}\n"
            f"Статус: {order['status']}\n"
            f"Сумма: {order.get('total_price', 0)} ₽\n"
            f"Дата: {order.get('created_at', 'N/A')}\n\n"
            "<b>Позиции заказа:</b>\n"
        )
        # Проверяем, есть ли 'items' в order и это список
        if 'items' in order and isinstance(order['items'], list):
            for item in order['items']:
                order_text += f"- {item.get('doc_name', 'N/A')} - {item.get('price', 0)} ₽\n"
        else:
            order_text += "Нет позиций в заказе.\n"

        # Кнопки изменения статуса
        status_buttons = [
            [InlineKeyboardButton(text="✅ Оплачен", callback_data=f"change_status_{order['id']}_paid")],
            [InlineKeyboardButton(text="📦 В обработке", callback_data=f"change_status_{order['id']}_processing")],
            [InlineKeyboardButton(text="✅ Отправлен", callback_data=f"change_status_{order['id']}_sent")],
            [InlineKeyboardButton(text="✅ Доставлен", callback_data=f"change_status_{order['id']}_delivered")],
            [InlineKeyboardButton(text="❌ Отменен", callback_data=f"change_status_{order['id']}_cancelled")]
        ]
        status_buttons.append([InlineKeyboardButton(text="⬅️ Назад", callback_data="admin_orders")])

        markup = InlineKeyboardMarkup(inline_keyboard=status_buttons)

        await message.answer(
            text=order_text,
            parse_mode="HTML",
            reply_markup=markup
        )
    except Exception as e: # Добавлен блок except
        logger.error(f"Ошибка при поиске/отображении заказа {order_id}: {e}", exc_info=True)
        await message.answer("⚠️ Произошла ошибка при поиске заказа", reply_markup=None)
    finally:
         await state.clear()

@router.callback_query(F.data.startswith("change_status_"))
async def change_order_status(callback: CallbackQuery):
    """Изменяет статус заказа"""
    user_id = callback.from_user.id
    logger.info(f"Пользователь {user_id} изменил статус заказа")

    if not is_admin(user_id):
        await callback.answer("⚠️ Доступ запрещен", show_alert=True)
        return

    try:
        parts = callback.data.split("_")
        if len(parts) < 4:
            await callback.answer("⚠️ Некорректный запрос", show_alert=True)
            return

        order_id = int(parts[2])
        new_status = parts[3]

        success = db_update_order_status(order_id, new_status)
        if success:
            await callback.answer(f"✅ Статус заказа {order_id} изменен на '{new_status}'", show_alert=True)
            await admin_orders(callback) # Вызываем обработчик отображения заказов
        else:
            await callback.answer("⚠️ Не удалось изменить статус", show_alert=True)
    except (ValueError, IndexError) as e: # Конкретные исключения
        logger.error(f"Ошибка парсинга данных для изменения статуса: {e}")
        await callback.answer("⚠️ Некорректные данные для изменения статуса", show_alert=True)
    except Exception as e:
        logger.error(f"Ошибка при изменении статуса заказа: {e}", exc_info=True)
        await callback.answer("⚠️ Произошла ошибка при изменении статуса", show_alert=True)


@router.callback_query(F.data == "admin_prices")
async def admin_prices(callback: CallbackQuery):
    user_id = callback.from_user.id
    logger.info(f"Пользователь {user_id} запросил управление ценами")

    if not is_admin(user_id):
        await callback.answer("⚠️ Доступ запрещен", show_alert=True)
        return

    try:
        # Получаем цены из базы данных
        template_price = get_template_price()
        autogen_price = get_autogeneration_price()

        prices_text = (
            "🏷 <b>Управление ценами</b>\n"
            f"• Шаблон: <b>{template_price}</b> ₽\n"
            f"• Автогенерация: <b>{autogen_price}</b> ₽\n\n"
            "Выберите, что хотите изменить:"
        )

        markup = InlineKeyboardMarkup(inline_keyboard=[
            [
                InlineKeyboardButton(text="✏️ Цена за шаблон", callback_data="edit_price_template"),
                InlineKeyboardButton(text="✏️ Цена за автогенерацию", callback_data="edit_price_autogen")
            ],
            [
                InlineKeyboardButton(text="⬅️ Назад", callback_data="admin_panel")
            ]
        ])

        await callback.message.edit_text(
            text=prices_text,
            parse_mode="HTML",
            reply_markup=markup
        )
        await callback.answer()
    except Exception as e:
        logger.error(f"Ошибка при отображении цен: {e}", exc_info=True)
        await callback.answer("⚠️ Произошла ошибка при загрузке цен", show_alert=True)

@router.callback_query(F.data.startswith("edit_price_"))
async def start_editing_price(callback: CallbackQuery, state: FSMContext):
    user_id = callback.from_user.id
    # Проверка администратора уже внутри is_admin
    if not is_admin(user_id):
        await callback.answer("⚠️ Доступ запрещен", show_alert=True)
        return

    try: # Добавлен блок try-except
        data = callback.data
        service_type = data.replace("edit_price_", "")
        if service_type not in ["template", "autogen"]:
            await callback.answer("⚠️ Некорректный запрос", show_alert=True)
            return

        await state.set_state(AdminStates.EDITING_PRICE)
        await state.update_data(service_type=service_type)

        price_name = "шаблона" if service_type == "template" else "автогенерации"
        await callback.message.edit_text(
            text=f"Введите новую цену для <b>{price_name}</b> (в рублях, например, 25.7):",
            parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="⬅️ Назад", callback_data="admin_prices")]
            ])
        )
        await callback.answer()
    except Exception as e: # Добавлен блок except
        logger.error(f"Ошибка при начале редактирования цены: {e}", exc_info=True)
        await callback.answer("⚠️ Произошла ошибка", show_alert=True)

@router.message(AdminStates.EDITING_PRICE)
async def process_new_price(message: Message, state: FSMContext):
    user_id = message.from_user.id
    # Проверка администратора уже внутри is_admin
    if not is_admin(user_id):
        await message.answer("⚠️ Доступ запрещен", reply_markup=None)
        await state.clear()
        return

    try:
        new_price_input = message.text.strip()
        new_price_float = float(new_price_input)
        if new_price_float < 0:
            await message.answer("Цена не может быть отрицательной. Введите новую цену:")
            return
        new_price = int(new_price_float)
    except ValueError:
        await message.answer("Пожалуйста, введите корректное число для цены (например, 25.7):")
        return

    try:
        data = await state.get_data()
        service_type = data.get('service_type')

        success = update_price_in_db(service_type, new_price)

        if success:
            template_price = get_template_price()
            autogen_price = get_autogeneration_price()
            price_name = "шаблона" if service_type == "template" else "автогенерации"
            prices_text = (
                "🏷 <b>Управление ценами</b>\n"
                f"• Шаблон: <b>{template_price}</b> ₽\n"
                f"• Автогенерация: <b>{autogen_price}</b> ₽\n"
                f"✅ Цена для <b>{price_name}</b> успешно обновлена на <b>{new_price}</b> ₽"
            )
            await message.answer(text=prices_text, parse_mode="HTML", reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="⬅️ Назад", callback_data="admin_panel")]
            ]))
        else:
            await message.answer("❌ Ошибка при обновлении цены. Проверьте логи.")
    except Exception as e: # Добавлен блок except
        logger.error(f"Ошибка при обновлении цены в БД: {e}", exc_info=True)
        await message.answer("❌ Ошибка при обновлении цены. Проверьте логи.")
    finally:
        await state.clear()

@router.callback_query(F.data == "admin_users")
async def admin_users(callback: CallbackQuery):
    user_id = callback.from_user.id
    logger.info(f"Пользователь {user_id} запросил список пользователей")

    if not is_admin(user_id):
        await callback.answer("⚠️ Доступ запрещен", show_alert=True)
        return

    try:
        users = get_all_users()
        if not users:
            await callback.message.edit_text(
                "👥 <b>Пользователи</b>\n"
                "Нет пользователей для отображения.",
                parse_mode="HTML",
                reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                    [InlineKeyboardButton(text="🔄 Обновить", callback_data="admin_users")],
                    [InlineKeyboardButton(text="⬅️ Назад", callback_data="admin_panel")]
                ])
            )
            await callback.answer()
            return

        users_text = "👥 <b>Последние пользователи</b>\n\n"
        for user in users[:10]:
            users_text += (
                f"ID: {user.get('id', 'N/A')}\n"
                f"Имя: {user.get('first_name', 'N/A')}\n"
                f"Username: @{user.get('username', 'N/A')}\n"
                f"Дата регистрации: {user.get('registered_at', 'N/A')}\n\n"
            )

        markup = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🔄 Обновить", callback_data="admin_users")],
            [InlineKeyboardButton(text="⬅️ Назад", callback_data="admin_panel")]
        ])

        await callback.message.edit_text(
            text=users_text,
            parse_mode="HTML",
            reply_markup=markup
        )
        await callback.answer()
    except Exception as e:
        logger.error(f"Ошибка при отображении пользователей: {e}", exc_info=True)
        await callback.answer("⚠️ Произошла ошибка при загрузке пользователей", show_alert=True)

@router.callback_query(F.data == "admin_templates")
async def admin_templates(callback: CallbackQuery):
    user_id = callback.from_user.id
    logger.info(f"Пользователь {user_id} запросил управление шаблонами")

    if not is_admin(user_id):
        await callback.answer("⚠️ Доступ запрещен", show_alert=True)
        return

    try:
        templates = get_all_templates()

        if not templates:
            await callback.message.edit_text(
                "📑 <b>Управление шаблонами</b>\n"
                "Нет шаблонов для отображения.",
                parse_mode="HTML",
                reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                    [InlineKeyboardButton(text="➕ Создать шаблон", callback_data="create_template")],
                    [InlineKeyboardButton(text="🔄 Обновить", callback_data="admin_templates")],
                    [InlineKeyboardButton(text="⬅️ Назад", callback_data="admin_panel")]
                ])
            )
            await callback.answer()
            return

        templates_text = "📑 <b>Шаблоны документов</b>\n\n"
        for template in templates:
            template_id = template.get('id', 'N/A')
            name = template.get('name', 'Без названия')
            category = template.get('category', 'Без категории')
            price = template.get('price', template.get('template_price', 0))
            templates_text += (
                f"ID: {template_id}\n"
                f"Название: {name}\n"
                f"Категория: {category}\n"
                f"Цена: {price} ₽\n\n"
            )

        markup = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="➕ Создать шаблон", callback_data="create_template")],
            [InlineKeyboardButton(text="🔄 Обновить", callback_data="admin_templates")],
            [InlineKeyboardButton(text="⬅️ Назад", callback_data="admin_panel")]
        ])

        await callback.message.edit_text(
            text=templates_text,
            parse_mode="HTML",
            reply_markup=markup
        )
        await callback.answer()
    except Exception as e:
        logger.error(f"Ошибка при отображении шаблонов: {e}", exc_info=True)
        await callback.answer("⚠️ Произошла ошибка при загрузке шаблонов", show_alert=True)

@router.callback_query(F.data == "create_template")
async def create_template_start(callback: CallbackQuery, state: FSMContext):
    user_id = callback.from_user.id
    logger.info(f"Пользователь {user_id} начал создание шаблона")
    if not is_admin(user_id):
        await callback.answer("⚠️ Доступ запрещен", show_alert=True)
        return

    try:
        await callback.message.edit_text(
            "➕ <b>Создание шаблона</b>\n"
            "Введите название шаблона:",
            parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="⬅️ Назад", callback_data="admin_templates")]
            ])
        )
        await state.set_state(AdminStates.CREATING_TEMPLATE)
        await callback.answer()
    except Exception as e:
        logger.error(f"Ошибка при начале создания шаблона: {e}", exc_info=True)
        await callback.answer("⚠️ Произошла ошибка", show_alert=True)

@router.message(AdminStates.CREATING_TEMPLATE)
async def process_template_name(message: Message, state: FSMContext):
    user_id = message.from_user.id
    logger.info(f"Пользователь {user_id} ввел название шаблона: {message.text}")

    if not is_admin(user_id):
        await message.answer("⚠️ Доступ запрещен", reply_markup=None)
        await state.clear()
        return

    try:
        await state.update_data(template_name=message.text)
        await message.answer(
            "Введите категорию шаблона (например, business, realestate):",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="⬅️ Назад", callback_data="admin_templates")]
            ])
        )
        await state.set_state(AdminStates.ENTERING_TEMPLATE_CATEGORY)
    except Exception as e:
        logger.error(f"Ошибка при обработке названия шаблона: {e}", exc_info=True)
        await message.answer("⚠️ Произошла ошибка", reply_markup=None)
        await state.clear()

@router.message(AdminStates.ENTERING_TEMPLATE_CATEGORY)
async def process_template_category(message: Message, state: FSMContext):
    user_id = message.from_user.id
    logger.info(f"Пользователь {user_id} ввел категорию шаблона: {message.text}")

    if not is_admin(user_id):
        await message.answer("⚠️ Доступ запрещен", reply_markup=None)
        await state.clear()
        return

    try:
        await state.update_data(template_category=message.text.lower()) # Сохраняем категорию в нижнем регистре
        await message.answer(
            "Введите цену шаблона (в рублях, например, 25.7):",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="⬅️ Назад", callback_data="admin_templates")]
            ])
        )
        await state.set_state(AdminStates.ENTERING_TEMPLATE_PRICE)
    except Exception as e:
        logger.error(f"Ошибка при обработке категории шаблона: {e}", exc_info=True)
        await message.answer("⚠️ Произошла ошибка", reply_markup=None)
        await state.clear()

@router.message(AdminStates.ENTERING_TEMPLATE_PRICE)
async def process_template_price(message: Message, state: FSMContext):
    user_id = message.from_user.id
    logger.info(f"Пользователь {user_id} ввел цену шаблона: {message.text}")

    if not is_admin(user_id):
        await message.answer("⚠️ Доступ запрещен", reply_markup=None)
        await state.clear()
        return

    try:
        price_input = message.text.strip()
        price_float = float(price_input)
        if price_float < 0:
            await message.answer("Цена не может быть отрицательной. Введите цену:")
            return
        price = int(price_float)
    except ValueError:
        await message.answer("Пожалуйста, введите корректное число для цены (например, 25.7):")
        return

    try:
        data = await state.get_data()
        name = data.get('template_name', 'Без названия')
        category = data.get('template_category', 'unknown')
        success = db_create_template(name, category, price)

        if success:
            await message.answer(
                f"✅ Шаблон '{name}' успешно создан с ценой {price} ₽",
                reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                    [InlineKeyboardButton(text="↩️ Вернуться к шаблонам", callback_data="admin_templates")]
                ])
            )
        else:
            await message.answer("❌ Ошибка при создании шаблона. Проверьте логи.")
    except Exception as e: # Добавлен блок except
        logger.error(f"Ошибка при создании шаблона: {e}", exc_info=True)
        await message.answer("❌ Ошибка при создании шаблона. Проверьте логи.")
    finally:
        await state.clear()

@router.callback_query(F.data == "admin_promocodes")
async def admin_promocodes(callback: CallbackQuery):
    user_id = callback.from_user.id
    logger.info(f"Пользователь {user_id} запросил управление промокодами")

    if not is_admin(user_id):
        await callback.answer("⚠️ Доступ запрещен", show_alert=True)
        return

    try:
        promocodes = get_all_promocodes()

        if not promocodes:
            await callback.message.edit_text(
                "🎟 <b>Управление промокодами</b>\n"
                "Нет промокодов для отображения.",
                parse_mode="HTML",
                reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                    [InlineKeyboardButton(text="➕ Создать промокод", callback_data="create_promocode")],
                    [InlineKeyboardButton(text="🔄 Обновить", callback_data="admin_promocodes")],
                    [InlineKeyboardButton(text="⬅️ Назад", callback_data="admin_panel")]
                ])
            )
            await callback.answer()
            return

        promocodes_text = "🎟 <b>Промокоды</b>\n\n"
        for promocode in promocodes:
            # Используем .get() для избежания KeyError и проверяем типы
            code = promocode.get('code', 'N/A')
            discount = promocode.get('discount', 0)
            used_count = promocode.get('used_count', 0)
            max_uses = promocode.get('max_uses', 0)
            expires_at = promocode.get('expires_at', 'N/A')
            promocodes_text += (
                f"Код: <code>{code}</code>\n"
                f"Скидка: {discount}%\n"
                f" Использован: {used_count}/{max_uses}\n"
                f" Действует до: {expires_at}\n\n"
            )

        buttons = [
            [
                InlineKeyboardButton(text="➕ Создать промокод", callback_data="create_promocode")
            ],
            [
                InlineKeyboardButton(text="🔄 Обновить", callback_data="admin_promocodes")
            ],
            [
                InlineKeyboardButton(text="⬅️ Назад", callback_data="admin_panel")
            ]
        ]
        markup = InlineKeyboardMarkup(inline_keyboard=buttons)

        await callback.message.edit_text(
            text=promocodes_text,
            parse_mode="HTML",
            reply_markup=markup
        )
        await callback.answer()
    except Exception as e:
        logger.error(f"Ошибка при отображении промокодов: {e}", exc_info=True)
        await callback.answer("⚠️ Произошла ошибка при загрузке промокодов", show_alert=True)

@router.callback_query(F.data == "create_promocode")
async def create_promocode_start(callback: CallbackQuery, state: FSMContext):
    user_id = callback.from_user.id
    logger.info(f"Пользователь {user_id} начал создание промокода")

    if not is_admin(user_id):
        await callback.answer("⚠️ Доступ запрещен", show_alert=True)
        return

    try:
        await callback.message.edit_text(
            "➕ <b>Создание промокода</b>\n"
            "Введите код промокода:",
            parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="⬅️ Назад", callback_data="admin_promocodes")]
            ])
        )
        await state.set_state(AdminStates.CREATING_PROMOCODE)
        await callback.answer()
    except Exception as e:
        logger.error(f"Ошибка при начале создания промокода: {e}", exc_info=True)
        await callback.answer("⚠️ Произошла ошибка", show_alert=True)

@router.message(AdminStates.CREATING_PROMOCODE)
async def process_promocode_code(message: Message, state: FSMContext):
    user_id = message.from_user.id
    logger.info(f"Пользователь {user_id} ввел код промокода: {message.text}")
    if not is_admin(user_id):
        await message.answer("⚠️ Доступ запрещен", reply_markup=None)
        await state.clear()
        return

    try:
        await state.update_data(promocode_code=message.text.upper())
        await message.answer(
            "Введите размер скидки (в процентах):",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="⬅️ Назад", callback_data="admin_promocodes")]
            ])
        )
        await state.set_state(AdminStates.ENTERING_PROMOCODE_DISCOUNT)
    except Exception as e:
        logger.error(f"Ошибка при обработке кода промокода: {e}", exc_info=True)
        await message.answer("⚠️ Произошла ошибка", reply_markup=None)
        await state.clear()

@router.message(AdminStates.ENTERING_PROMOCODE_DISCOUNT)
async def process_promocode_discount(message: Message, state: FSMContext):
    user_id = message.from_user.id
    logger.info(f"Пользователь {user_id} ввел скидку промокода: {message.text}")
    if not is_admin(user_id):
        await message.answer("⚠️ Доступ запрещен", reply_markup=None)
        await state.clear()
        return

    try:
        try:
            discount = int(message.text)
            if discount <= 0 or discount > 100:
                raise ValueError("Скидка должна быть от 1 до 100")
        except (ValueError, TypeError) as ve:
            await message.answer(
                f"❌ Неверный размер скидки: {ve}. Введите число от 1 до 100:",
                reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                    [InlineKeyboardButton(text="⬅️ Назад", callback_data="admin_promocodes")]
                ])
            )
            return # Не очищаем состояние, позволяем повторный ввод

        data = await state.get_data()
        code = data.get('promocode_code')
        success = db_create_promocode(code, "percent", discount, 30, 100)

        if success:
            await message.answer(
                f"✅ Промокод <code>{code}</code> успешно создан со скидкой {discount}%",
                parse_mode="HTML",
                reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                    [InlineKeyboardButton(text="↩️ Вернуться к промокодам", callback_data="admin_promocodes")]
                ])
            )
        else:
            await message.answer("❌ Ошибка при создании промокода. Проверьте логи.")
    except Exception as e:
        logger.error(f"Ошибка при создании промокода: {e}", exc_info=True)
        await message.answer("⚠️ Произошла ошибка при создании промокода", reply_markup=None)
    finally:
        await state.clear()

@router.callback_query(F.data == "admin_newsletter")
async def admin_newsletter(callback: CallbackQuery, state: FSMContext):
    user_id = callback.from_user.id
    logger.info(f"Пользователь {user_id} начал процесс рассылки")

    if not is_admin(user_id):
        await callback.answer("⚠️ Доступ запрещен", show_alert=True)
        return

    try:
        await callback.message.edit_text(
            "📤 <b>Создание рассылки</b>\n"
            "Введите текст сообщения для рассылки:",
            parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="⬅️ Назад", callback_data="admin_panel")]
            ])
        )
        await state.set_state(AdminStates.WAITING_FOR_BROADCAST)
        await callback.answer()
    except Exception as e:
        logger.error(f"Ошибка при начале рассылки: {e}", exc_info=True)
        await callback.answer("⚠️ Произошла ошибка", show_alert=True)

@router.message(AdminStates.WAITING_FOR_BROADCAST)
async def process_broadcast_message(message: Message, state: FSMContext):
    user_id = message.from_user.id
    logger.info(f"Пользователь {user_id} отправил текст рассылки")

    if not is_admin(user_id):
        await message.answer("⚠️ Доступ запрещен", reply_markup=None)
        await state.clear()
        return

    try:
        await state.update_data(broadcast_text=message.text)

        markup = InlineKeyboardMarkup(inline_keyboard=[
            [
                InlineKeyboardButton(text="✅ Отправить", callback_data="send_broadcast"),
                InlineKeyboardButton(text="❌ Отмена", callback_data="cancel_broadcast")
            ]
        ])

        await message.answer(
            "Проверьте текст рассылки. Отправить?",
            reply_markup=markup
        )
    except Exception as e:
        logger.error(f"Ошибка при обработке текста рассылки: {e}", exc_info=True)
        await message.answer("⚠️ Произошла ошибка", reply_markup=None)
        await state.clear() # Очищаем состояние при ошибке

@router.callback_query(F.data == "send_broadcast")
async def confirm_broadcast(callback: CallbackQuery, state: FSMContext):
    user_id = callback.from_user.id
    logger.info(f"Пользователь {user_id} подтвердил рассылку")

    if not is_admin(user_id):
        await callback.answer("⚠️ Доступ запрещен", show_alert=True)
        return

    try:
        data = await state.get_data()
        text = data.get('broadcast_text')

        if not text:
            await callback.answer("⚠️ Текст рассылки отсутствует", show_alert=True)
            await state.clear() # Очищаем состояние
            return

        subscribers = get_news_subscribers()

        if not subscribers:
             await callback.message.edit_text(
                "❌ Нет подписчиков для рассылки.",
                reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                    [InlineKeyboardButton(text="⬅️ Назад", callback_data="admin_panel")]
                ])
            )
             await state.clear()
             return


        success_count = 0
        fail_count = 0

        for user_id_sub in subscribers:
            try:
                # Отправляем сообщение каждому подписчику
                await callback.send_message(chat_id=user_id_sub, text=text, parse_mode="HTML")
                success_count += 1
                # Небольшая задержка, чтобы избежать ограничений Telegram API
                # import asyncio
                # await asyncio.sleep(0.1)
            except Exception as e:
                logger.error(f"Ошибка отправки рассылки пользователю {user_id_sub}: {e}")
                fail_count += 1

        await callback.message.edit_text(
            f"📤 Рассылка завершена!\n"
            f"✅ Успешно: {success_count}\n"
            f"❌ Ошибок: {fail_count}",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="⬅️ Назад", callback_data="admin_panel")]
            ])
        )

    except Exception as e:
        logger.error(f"Ошибка при отправке рассылки: {e}", exc_info=True)
        await callback.answer("⚠️ Произошла ошибка при отправке", show_alert=True)
        # Можно также отправить сообщение в чат
        await callback.message.answer("⚠️ Произошла ошибка при отправке рассылки. Проверьте логи.")
    finally:
        await state.clear()

@router.callback_query(F.data == "cancel_broadcast")
async def cancel_broadcast(callback: CallbackQuery, state: FSMContext):
    """Отменяет рассылку"""
    await state.clear()
    await callback.message.edit_text(
        "❌ Рассылка отменена.",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="⬅️ Назад", callback_data="admin_panel")]
        ])
    )
    await callback.answer()

@router.message(F.text.startswith("/stats"))
async def handle_stats_request(message: Message):
    # Проверяем, что сообщение пришло в чат поддержки
    if str(message.chat.id) != str(config.SUPPORT_CHAT_ID):
        return

    is_user_admin = False
    sender_id = message.from_user.id
    if is_admin(sender_id):
         is_user_admin = True

    if not is_user_admin:
        return

    try:
        command = message.text.strip().lower()
        if "/stats daily" in command or "/stats day" in command:
            # Отправляем ежедневную статистику
            await send_daily_stats_report()
            await message.reply("📊 Ежедневная статистика отправлена в группу.")
        elif "/stats monthly" in command or "/stats month" in command:
            # Отправляем ежемесячную статистику
            await send_monthly_stats_report()
            await message.reply("📊 Ежемесячная статистика отправлена в группу.")
        elif "/stats yearly" in command or "/stats year" in command:
            # Отправляем годовую статистику
            await send_yearly_stats_report()
            await message.reply("📊 Годовая статистика отправлена в группу.")
        elif "/stats" in command:
            # Отправляем краткую статистику
            stats = get_orders_stats()
            # Проверяем наличие ключей в stats
            total_orders = stats.get('total_orders', 0)
            total_revenue = stats.get('total_revenue', 0.0)
            stats_text = (
                f"📊 Краткая статистика:\n"
                f"Всего заказов: {total_orders}\n"
                f"Выручка: {total_revenue:.2f} ₽"
            )
            await message.reply(stats_text)
    except Exception as e:
        logger.error(f"Ошибка при обработке команды /stats в группе: {e}", exc_info=True)
        await message.reply("⚠️ Произошла ошибка при обработке команды.")

@router.message(F.text.startswith("/promocodes"))
async def handle_promocodes_request(message: Message):
     # Проверяем, что сообщение пришло в чат поддержки
    if str(message.chat.id) != str(config.SUPPORT_CHAT_ID):
        return # Игнорируем сообщения не из чата поддержки

    # Проверяем, что отправитель является админом
    is_user_admin = False
    sender_id = message.from_user.id
    if is_admin(sender_id):
         is_user_admin = True

    if not is_user_admin:
        return

    try:
        promocodes = get_all_promocodes()
        if not promocodes:
            await message.reply("Нет активных промокодов.")
            return

        promocodes_text = "🎟 Активные промокоды:\n"
        for promocode in promocodes:
            # Используем .get() для избежания KeyError
            code = promocode.get('code', 'N/A')
            discount = promocode.get('discount', 0)
            used_count = promocode.get('used_count', 0)
            max_uses = promocode.get('max_uses', 0)
            remaining = max_uses - used_count
            promocodes_text += f"- {code}: {discount}% (осталось {remaining} использований)\n"

        await message.reply(promocodes_text)
    except Exception as e:
        logger.error(f"Ошибка при обработке команды /promocodes в группе: {e}", exc_info=True)
        await message.reply("⚠️ Произошла ошибка при обработке команды.")