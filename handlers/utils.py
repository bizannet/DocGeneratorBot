import logging
import re
from datetime import datetime
from aiogram import Router, F
from aiogram.types import CallbackQuery, Message, InlineKeyboardButton, InlineKeyboardMarkup
from aiogram.fsm.context import FSMContext
from config import config
from texts.messages import (
    MAIN_MENU_TEXT,
    SUPPORT_TEXT,
    ABOUT_TEXT
)

logger = logging.getLogger('doc_bot.utils')
router = Router(name="utils_router")


def format_user_info(user):
    """Форматирует информацию о пользователе"""
    user_info = (
        f"👤 <b>Информация о пользователе</b>\n\n"
        f"• ID: <code>{user.id}</code>\n"
    )

    if user.username:
        user_info += f"• Username: @{user.username}\n"

    if user.first_name:
        user_info += f"• Имя: {user.first_name}\n"

    if user.last_name:
        user_info += f"• Фамилия: {user.last_name}\n"

    user_info += f"• Язык: {user.language_code}"

    return user_info


async def safe_edit_message(message, text, reply_markup=None, parse_mode="HTML"):
    try:
        if message.text == text and message.reply_markup == reply_markup:
            return True

        await message.edit_text(
            text=text,
            reply_markup=reply_markup,
            parse_mode=parse_mode
        )
        return True
    except Exception as e:
        if "message is not modified" in str(e).lower():
            return True  # Текст не изменился, это нормально
        logger.warning(f"Не удалось отредактировать сообщение: {e}")
        return False


async def create_main_menu():
    """Создает основное меню бота"""
    buttons = [
        [
            InlineKeyboardButton(
                text="📂 Каталог документов",
                callback_data="catalog"
            )
        ],
        [
            InlineKeyboardButton(
                text="🔖 Сохраненные шаблоны",
                callback_data="templates"
            ),
            InlineKeyboardButton(
                text="🛒 Корзина",
                callback_data="view_cart"
            )
        ],
        [
            InlineKeyboardButton(
                text="🤝 Партнерская программа",
                callback_data="partner_program"
            ),
            InlineKeyboardButton(
                text="🔍 Рекомендации",
                callback_data="recommendations"
            )
        ],
        [
            InlineKeyboardButton(
                text="ℹ️ О боте",
                callback_data="about"
            ),
            InlineKeyboardButton(
                text="🆘 Поддержка",
                callback_data="support"
            )
        ],
        [
            InlineKeyboardButton(
                text="⭐ Оставить отзыв",
                callback_data="reviews"
            )
        ]
    ]

    return InlineKeyboardMarkup(inline_keyboard=buttons)


async def format_order_summary(order):
    order_date = order['created_at'].split(' ')[0]

    # Форматируем статус
    status_map = {
        'created': 'Создан',
        'pending': 'Ожидает оплаты',
        'paid': 'Оплачен',
        'processing': 'Генерируется',
        'completed': 'Готов',
        'cancelled': 'Отменен',
        'refunded': 'Возврат средств'
    }
    status = status_map.get(order['status'], order['status'].capitalize())

    # Форматируем элементы заказа
    items_text = ""
    for item in order['items']:
        items_text += f"• {item['doc_name']} — {item['price']} ₽\n"

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
        f"{items_text}\n"
        f"{total_text}"
    )

    return order_text


async def send_long_message(bot, chat_id, text, max_length=4096, parse_mode="HTML"):
    if len(text) <= max_length:
        await bot.send_message(chat_id, text, parse_mode=parse_mode)
        return
    paragraphs = re.split(r'\n\s*\n', text)
    current_message = ""

    for paragraph in paragraphs:
        if len(current_message) + len(paragraph) + 2 > max_length:
            if current_message:
                await bot.send_message(chat_id, current_message, parse_mode=parse_mode)
            current_message = paragraph
        else:
            if current_message:
                current_message += "\n\n" + paragraph
            else:
                current_message = paragraph

    if current_message:
        await bot.send_message(chat_id, current_message, parse_mode=parse_mode)


def format_datetime(dt_str, format="%Y-%m-%d %H:%M:%S"):
    try:
        for fmt in ["%Y-%m-%d %H:%M:%S", "%Y-%m-%d", "%d.%m.%Y %H:%M:%S", "%d.%m.%Y"]:
            try:
                date_obj = datetime.strptime(dt_str, fmt)
                return date_obj.strftime("%d.%m.%Y %H:%M")
            except (ValueError, TypeError):
                continue
        return dt_str
    except Exception:
        return dt_str


def is_valid_user(user_id):
    return user_id is not None and user_id > 0


def is_admin(user_id):
    return user_id in config.ADMIN_IDS


@router.callback_query(F.data == "back_main")
async def back_to_main(callback: CallbackQuery, state: FSMContext):
    logger.info(f"Пользователь {callback.from_user.id} вернулся в главное меню")

    try:
        await state.clear()
        main_menu = await create_main_menu()
        await safe_edit_message(
            callback.message,
            MAIN_MENU_TEXT,
            reply_markup=main_menu
        )
        await callback.answer()
    except Exception as e:
        logger.error(f"Ошибка при возврате в главное меню: {e}", exc_info=True)
        await callback.answer("⚠️ Произошла ошибка", show_alert=True)
        await callback.answer()


@router.callback_query(F.data == "about")
async def show_about(callback: CallbackQuery):
    logger.info(f"Пользователь {callback.from_user.id} запросил информацию о боте")
    try:
        buttons = [
            [
                InlineKeyboardButton(
                    text="⭐ Посмотреть отзывы",
                    url="https://t.me/otzyvy_dokgenerator"
                )
            ],
            [
                InlineKeyboardButton(
                    text="💎 Присоединиться к сообществу",
                    url="https://t.me/bizhack_annet"
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
        await safe_edit_message(
            callback.message,
            ABOUT_TEXT,
            reply_markup=markup
        )
        await callback.answer()
    except Exception as e:
        logger.error(f"Ошибка при отображении информации о боте: {e}", exc_info=True)
        await callback.answer("⚠️ Произошла ошибка", show_alert=True)
        await callback.answer()


@router.callback_query(F.data == "support")
async def show_support(callback: CallbackQuery):
    logger.info(f"Пользователь {callback.from_user.id} запросил информацию о поддержке")

    try:
        buttons = [
            [
                InlineKeyboardButton(
                    text="Написать в поддержку",
                    url="https://t.me/biz_annet"
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
        await safe_edit_message(
            callback.message,
            SUPPORT_TEXT,
            reply_markup=markup
        )
        await callback.answer()
    except Exception as e:
        logger.error(f"Ошибка при отображении информации о поддержке: {e}", exc_info=True)
        await callback.answer("⚠️ Произошла ошибка", show_alert=True)
        await callback.answer()


@router.callback_query(F.data == "unknown_callback")
async def handle_unknown_callback(callback: CallbackQuery):
    logger.warning(f"Получен неизвестный callback от {callback.from_user.id}: {callback.data}")

    try:
        buttons = [
            [
                InlineKeyboardButton(
                    text="🏠 Вернуться в меню",
                    callback_data="back_main"
                )
            ]
        ]

        markup = InlineKeyboardMarkup(inline_keyboard=buttons)
        await safe_edit_message(
            callback.message,
            "⚠️ Неизвестная команда. Пожалуйста, воспользуйтесь кнопками меню.",
            reply_markup=markup
        )
        await callback.answer()
    except Exception as e:
        logger.error(f"Ошибка при обработке неизвестного callback: {e}", exc_info=True)


@router.message()
async def handle_unknown_message(message: Message):
    logger.info(f"Получено неизвестное сообщение от {message.from_user.id}: {message.text}")

    try:
        main_menu = await create_main_menu()
        await message.answer(
            "⚠️ Я не понимаю ваше сообщение. Пожалуйста, воспользуйтесь кнопками меню ниже.",
            reply_markup=main_menu
        )
    except Exception as e:
        logger.error(f"Ошибка при обработке неизвестного сообщения: {e}", exc_info=True)


def split_text(text, max_length=4000):
    parts = []
    while text:
        if len(text) <= max_length:
            parts.append(text)
            break
        else:
            split_index = text.rfind('\n\n', 0, max_length)
            if split_index == -1:
                split_index = text.rfind('. ', 0, max_length)
            if split_index == -1:
                split_index = max_length
            else:
                split_index += 2

            parts.append(text[:split_index])
            text = text[split_index:].strip()

    return parts


async def paginate_text(message, text, page=1, items_per_page=8):
    lines = text.split('\n')
    total_pages = (len(lines) + items_per_page - 1) // items_per_page

    if page < 1:
        page = 1
    elif page > total_pages:
        page = total_pages

    start_idx = (page - 1) * items_per_page
    end_idx = min(start_idx + items_per_page, len(lines))

    page_text = '\n'.join(lines[start_idx:end_idx])

    buttons = []
    if total_pages > 1:
        nav_buttons = []
        if page > 1:
            nav_buttons.append(InlineKeyboardButton(text="⬅️", callback_data=f"page_{page - 1}"))
        nav_buttons.append(InlineKeyboardButton(text=f"{page}/{total_pages}", callback_data="current_page"))
        if page < total_pages:
            nav_buttons.append(InlineKeyboardButton(text="➡️", callback_data=f"page_{page + 1}"))
        buttons.append(nav_buttons)

    buttons.append([
        InlineKeyboardButton(text="🏠 Главное меню", callback_data="back_main")
    ])

    markup = InlineKeyboardMarkup(inline_keyboard=buttons)

    await safe_edit_message(
        message,
        page_text,
        reply_markup=markup
    )


@router.callback_query(F.data.startswith("page_"))
async def handle_pagination(callback: CallbackQuery):
    try:
        page = int(callback.data.split("_")[1])
        text = "Строка 1\nСтрока 2\nСтрока 3\nСтрока 4\nСтрока 5\nСтрока 6\nСтрока 7\nСтрока 8\nСтрока 9\nСтрока 10"
        await paginate_text(callback.message, text, page)
        await callback.answer()
    except Exception as e:
        logger.error(f"Ошибка при пагинации: {e}", exc_info=True)
        await callback.answer("⚠️ Произошла ошибка", show_alert=True)
        await callback.answer()


def get_user_name(user):
    if user.username:
        return f"@{user.username}"
    elif user.first_name and user.last_name:
        return f"{user.first_name} {user.last_name}"
    elif user.first_name:
        return user.first_name
    else:
        return f"Пользователь {user.id}"


async def handle_error(callback: CallbackQuery, error_message: str):
    logger.error(f"Ошибка: {error_message}")

    try:
        buttons = [
            [
                InlineKeyboardButton(
                    text="🏠 Вернуться в меню",
                    callback_data="back_main"
                )
            ]
        ]

        markup = InlineKeyboardMarkup(inline_keyboard=buttons)
        await safe_edit_message(
            callback.message,
            f"⚠️ {error_message}",
            reply_markup=markup
        )
        await callback.answer()
    except Exception as e:
        logger.error(f"Ошибка при обработке ошибки: {e}", exc_info=True)


def clean_html(text):
    clean_text = re.sub('<[^<]+?>', '', text)
    return clean_text


def escape_markdown(text):
    if not text:
        return text
    chars_to_escape = ['_', '*', '[', ']', '(', ')', '~', '`', '>', '#', '+', '-', '=', '|', '{', '}', '.', '!']

    for char in chars_to_escape:
        text = text.replace(char, f'\\{char}')

    return text


def truncate_text(text, max_length=100):
    if len(text) <= max_length:
        return text
    else:
        return text[:max_length - 3] + "..."


async def show_error(message, error_message):
    try:
        buttons = [
            [
                InlineKeyboardButton(
                    text="🏠 Вернуться в меню",
                    callback_data="back_main"
                )
            ]
        ]

        markup = InlineKeyboardMarkup(inline_keyboard=buttons)

        await message.answer(
            f"⚠️ {error_message}",
            reply_markup=markup
        )
    except Exception as e:
        logger.error(f"Ошибка при показе ошибки: {e}", exc_info=True)