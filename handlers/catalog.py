import logging
import datetime
from aiogram import Router, F
from aiogram.types import CallbackQuery, Message, InlineKeyboardButton, InlineKeyboardMarkup
from aiogram.fsm.context import FSMContext
from pathlib import Path
from config import config
from services.document_service import get_templates_from_filesystem, get_template_by_id_from_filesystem, \
    get_template_info
from services.pricing import get_template_price, get_autogeneration_price
from texts.messages import (
    CATALOG_TEXT,
    BUSINESS_DOCUMENTS_TEXT,
    REALESTATE_DOCUMENTS_TEXT,
    LOGISTICS_DOCUMENTS_TEXT,
    WEBSITE_DOCUMENTS_TEXT,
    CART_TEXT,
    DOCUMENT_DESCRIPTION_TEXT
)
from database.cart import add_to_cart, get_user_cart, clear_cart, remove_from_cart

logger = logging.getLogger('doc_bot.catalog')
router = Router(name="catalog_router")

CATEGORIES = {
    "business": {
        "text": BUSINESS_DOCUMENTS_TEXT,
        "name": "Для бизнеса",
        "icon": "🏢"
    },
    "logistics": {
        "text": LOGISTICS_DOCUMENTS_TEXT,
        "name": "Для грузоперевозок",
        "icon": "🚛"
    },
    "realestate": {
        "text": REALESTATE_DOCUMENTS_TEXT,
        "name": "Для аренды",
        "icon": "🏠"
    },
    "website": {
        "text": WEBSITE_DOCUMENTS_TEXT,
        "name": "Документы для сайта",
        "icon": "💻"
    }
}


def format_item_count(count: int) -> str:
    """Форматирует количество документов с правильным склонением"""
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
        if item.get('price_type') == 'autogen':
            doc_type = "автогенерация"

        price = item['price']
        items_list += f"{i}. {item['doc_name']} ({doc_type}) - {price} ₽\n"
    return items_list


@router.callback_query(F.data == "catalog")
async def show_catalog(callback: CallbackQuery):
    logger.info(f"Пользователь {callback.from_user.id} открыл каталог")

    try:
        buttons = []
        for category_key, category_info in CATEGORIES.items():
            buttons.append([
                InlineKeyboardButton(
                    text=f"{category_info['icon']} {category_info['name']}",
                    callback_data=f"category_{category_key}"
                )
            ])

        # Добавляем кнопку "Назад"
        buttons.append([
            InlineKeyboardButton(
                text="🏠 Главное меню",
                callback_data="back_main"
            )
        ])

        markup = InlineKeyboardMarkup(inline_keyboard=buttons)

        # Отправляем сообщение с каталогом
        await callback.message.edit_text(
            text=CATALOG_TEXT,
            reply_markup=markup,
            parse_mode="HTML"
        )
        await callback.answer()

    except Exception as e:
        logger.error(f"Ошибка при отображении каталога: {e}", exc_info=True)
        await callback.answer("⚠️ Произошла ошибка при отображении каталога", show_alert=True)
        await callback.answer()


@router.callback_query(F.data.startswith("category_"))
async def show_category(callback: CallbackQuery):
    """Показывает документы в категории"""
    category = callback.data.split("_")[1]
    logger.info(f"Пользователь {callback.from_user.id} открыл категорию {category}")

    # Получаем шаблоны по категории
    templates = get_templates_from_filesystem(category)

    if not templates:
        logger.warning(f"Не найдено шаблонов для категории {category}. Проверяем структуру проекта...")

        contracts_path = Path(config.DOCUMENTS_PATH) / "templates" / "contracts"
        website_path = Path(config.DOCUMENTS_PATH) / "templates" / "website"

        logger.warning(f"Путь к DOCUMENTS_PATH: {config.DOCUMENTS_PATH}")
        logger.warning(f"Путь к templates/contracts существует: {contracts_path.exists()}")
        logger.warning(f"Путь к templates/website существует: {website_path.exists()}")

        if contracts_path.exists():
            logger.warning(f"Содержимое папки contracts: {[str(p) for p in contracts_path.iterdir()]}")
        if website_path.exists():
            logger.warning(f"Содержимое папки website: {[str(p) for p in website_path.iterdir()]}")

        # Проверяем, есть ли шаблоны в других категориях
        for test_category in ["business", "logistics", "realestate", "website"]:
            test_templates = get_templates_from_filesystem(test_category)
            logger.warning(f"Найдено шаблонов для категории {test_category}: {len(test_templates)}")

        await callback.message.edit_text(
            f"⚠️ Нет шаблонов для категории: {category}",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="⬅️ Назад", callback_data="catalog")]
            ])
        )
        return

    buttons = []
    for template in templates:
        buttons.append([
            InlineKeyboardButton(
                text=f"📄 {template['name']}",
                callback_data=f"doc_{category}_{template['id']}"
            )
        ])

    buttons.append([
        InlineKeyboardButton(
            text="⬅️ Назад",
            callback_data="catalog"
        )
    ])

    category_texts = {
        "business": BUSINESS_DOCUMENTS_TEXT,
        "logistics": LOGISTICS_DOCUMENTS_TEXT,
        "realestate": REALESTATE_DOCUMENTS_TEXT,
        "website": WEBSITE_DOCUMENTS_TEXT
    }

    category_text = category_texts.get(category, f"Документы категории {category}")

    await callback.message.edit_text(
        text=category_text,
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons)
    )
    await callback.answer()


@router.callback_query(F.data.startswith("doc_"))
async def show_document(callback: CallbackQuery):
    logger.info(f"Пользователь {callback.from_user.id} просмотрел документ")

    try:
        # Получаем данные из callback_data
        parts = callback.data.split("_")
        if len(parts) < 3:  # Ожидаем как минимум 3 части: doc_category_id
            await callback.answer("⚠️ Некорректный запрос", show_alert=True)
            await callback.answer()
            return

        category_key = parts[1]
        doc_id = "_".join(parts[2:])

        template = get_template_by_id_from_filesystem(category_key, doc_id)

        if not template:
            await callback.answer("⚠️ Документ не найден", show_alert=True)
            await callback.answer()
            return

        template_info = get_template_info(template['template_name'], category_key)

        description = "Нет описания документа."
        if 'description' in template_info and template_info['description']:
            description = template_info['description']
        elif 'description' in template and template['description']:
            description = template['description']

        document_text = DOCUMENT_DESCRIPTION_TEXT.format(
            doc_name=template['name'],
            description=description,
            template_price=template_info['price']['template'],
            autogen_price=template_info['price']['autogen']
        )

        # Создаем клавиатуру с двумя основными кнопками
        markup = InlineKeyboardMarkup(inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="📝 Автогенерация",
                    callback_data=f"fill_{category_key}_{doc_id}_autogen"
                ),
                InlineKeyboardButton(
                    text="📥 Добавить шаблон в корзину",
                    callback_data=f"add_{category_key}_{doc_id}_template"
                )
            ],
            [
                InlineKeyboardButton(
                    text="⬅️ Назад",
                    callback_data=f"category_{category_key}"
                ),
                InlineKeyboardButton(
                    text="🏠 Главное меню",
                    callback_data="back_main"
                )
            ]
        ])

        await callback.message.edit_text(
            text=document_text,
            reply_markup=markup,
            parse_mode="HTML"
        )
        await callback.answer()

    except Exception as e:
        logger.error(f"Ошибка при отображении документа: {e}", exc_info=True)
        await callback.answer("⚠️ Произошла ошибка при отображении документа", show_alert=True)
        await callback.answer()


@router.callback_query(F.data.startswith("add_"))
async def add_to_cart_handler(callback: CallbackQuery):
    logger.info(f"Пользователь {callback.from_user.id} добавил документ в корзину")

    try:
        # Получаем данные из callback_data
        parts = callback.data.split("_")
        if len(parts) < 4:  # Ожидаем 4 части: add_category_id_type
            await callback.answer("⚠️ Некорректный запрос", show_alert=True)
            await callback.answer()
            return

        category_key = parts[1]
        # ID может содержать подчеркивания
        doc_id = "_".join(parts[2:-1])
        price_type = parts[-1]

        # Получаем информацию о шаблоне из файловой системы
        template = get_template_by_id_from_filesystem(category_key, doc_id)

        if not template:
            await callback.answer("⚠️ Документ не найден", show_alert=True)
            await callback.answer()
            return

        # Получаем полную информацию о шаблоне
        template_info = get_template_info(template['template_name'], category_key)

        # Определяем цену в зависимости от типа
        if price_type == 'autogen':
            price = template_info['price']['autogen']
        else:  # 'template'
            price = template_info['price']['template']

        now = datetime.datetime.now()
        suffix = now.strftime("%d.%m/%H:%M")
        cart_item_id = f"{template['template_name']}__{suffix}"

        # Создаем объект документа с правильной ценой и типом
        document = {
            'id': template['id'],
            'doc_name': template['name'],
            'category': template['category'],
            'description': template['description'],
            'template_name': template['template_name'],
            'price': price,
            'price_type': price_type,
            'filled_data': {}
        }

        add_to_cart(
            user_id=callback.from_user.id,
            cart_item_id=cart_item_id,
            doc_id=template['id'],
            doc_name=template['name'],
            category=template['category'],
            template_name=template['template_name'],
            price=price,
            price_type=price_type,
            filled_data={}
        )

        # Получаем обновленную корзину
        cart = get_user_cart(callback.from_user.id)

        # Формируем список документов в корзине
        items_list = format_cart_items(cart['items'])

        # Форматируем количество с правильным склонением
        item_count_str = format_item_count(cart['item_count'])

        # Формируем текст корзины
        cart_text = CART_TEXT.format(
            items_list=items_list,
            item_count=item_count_str,
            total_price=cart['total']
        )

        # Создаем клавиатуру
        buttons = [
            [
                InlineKeyboardButton(
                    text="✅ Оформить заказ",
                    callback_data="checkout"
                )
            ],
            [
                InlineKeyboardButton(
                    text="🛍️ Продолжить покупки",
                    callback_data="catalog"
                )
            ]
        ]

        # Добавляем кнопки для управления каждым элементом
        for i, item in enumerate(cart['items'], 1):
            buttons.append([
                InlineKeyboardButton(
                    text=f"🗑 Очистить {i}",
                    callback_data=f"remove_from_cart_{item['cart_item_id']}"
                )
            ])

        buttons.append([
            InlineKeyboardButton(
                text="🏠 Главное меню",
                callback_data="back_main"
            )
        ])

        markup = InlineKeyboardMarkup(inline_keyboard=buttons)

        # Отправляем сообщение
        await callback.message.edit_text(
            text=cart_text,
            reply_markup=markup,
            parse_mode="HTML"
        )
        await callback.answer("✅ Документ добавлен в корзину!")

    except Exception as e:
        logger.error(f"Ошибка при добавлении в корзину: {e}", exc_info=True)
        await callback.answer("⚠️ Произошла ошибка при добавлении в корзину", show_alert=True)
        await callback.answer()