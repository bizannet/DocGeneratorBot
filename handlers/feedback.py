import logging
import re
from aiogram import Router, F
from aiogram.types import (
    Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton,
    ReplyKeyboardRemove
)
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.filters import StateFilter
from config import config
from database.users import get_user_reviews_count
from database.orders import get_user_orders

logger = logging.getLogger('doc_bot.feedback')
router = Router()


class ReviewStates(StatesGroup):
    waiting_for_review = State()
    choose_publish_type = State()


# Улучшенный список запрещенных слов
BLACKLIST_PATTERNS = [
    r"\bмат\b", r"\bоскорбление\b", r"\bругательство\b",
    r"\bхуй\b", r"\bпизда\b", r"\bебал\b", r"\bебать\b",
    r"\bхуе\b", r"\bхуя\b", r"\bхуё\b", r"\bхуёв\b",
    r"\bебал\b", r"\bебло\b", r"\bебля\b", r"\bебнуть\b"
]


@router.callback_query(F.data == "reviews")
async def show_reviews(callback: CallbackQuery):
    user_id = callback.from_user.id

    # Проверяем, был ли хотя бы 1 оплаченный заказ
    from database.orders import get_user_orders
    orders = get_user_orders(user_id)
    paid_orders = [o for o in orders if o['status'] in ('paid', 'completed')]

    # Базовый текст — виден всем
    base_text = (
        "🌟 <b>Отзывы</b>\n\n"
        "Вы можете посмотреть отзывы других пользователей.\n\n"
        "👉 Все отзывы публикуются в канале: https://t.me/docgenerator\n\n"
    )

    buttons = [
        [InlineKeyboardButton(text="🏠 Главное меню", callback_data="back_main")]
    ]

    if paid_orders:
        # Проверяем, не оставлял ли отзыв в последние 30 дней
        from database.users import get_user_reviews_count
        review_count = get_user_reviews_count(user_id)
        if review_count > 0:
            extra_text = "⚠️ Вы уже оставляли отзыв. Новый можно оставить через 30 дней."
        else:
            extra_text = "💬 Хотите оставить свой отзыв?"
            buttons.insert(0, [InlineKeyboardButton(text="✍️ Оставить отзыв", callback_data="start_review")])
    else:
        extra_text = "💬 Оставить отзыв можно только после покупки любого документа."

    full_text = base_text + extra_text

    await callback.message.edit_text(
        full_text,
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons)
    )
    await callback.answer()

    # Проверка: не оставлял ли отзыв в последние 30 дней?
    review_count = get_user_reviews_count(user_id)
    if review_count > 0:
        await callback.message.answer(
            "⚠️ Вы уже оставляли отзыв. Вы можете оставить новый отзыв только раз в 30 дней.",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="🏠 Главное меню", callback_data="back_main")]
            ])
        )
        await callback.answer()
        return

    # Показываем страницу с описанием и кнопкой "Оставить отзыв"
    await callback.message.edit_text(
        "🌟 <b>Отзывы</b>\n\n"
        "Здесь вы можете посмотреть отзывы других пользователей или оставить свой.\n\n"
        "👉 Все отзывы публикуются в канале: https://t.me/docgenerator\n\n"
        "Ваш отзыв поможет другим принять решение!",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="✍️ Оставить отзыв", callback_data="start_review")],
            [InlineKeyboardButton(text="🏠 Главное меню", callback_data="back_main")]
        ])
    )
    await callback.answer()


@router.callback_query(F.data == "start_review")
async def start_review(callback: CallbackQuery, state: FSMContext):
    review_markup = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="⭐⭐⭐⭐⭐", callback_data="review_rating_5")],
        [InlineKeyboardButton(text="⭐⭐⭐⭐", callback_data="review_rating_4")],
        [InlineKeyboardButton(text="⭐⭐⭐", callback_data="review_rating_3")],
        [InlineKeyboardButton(text="⭐⭐", callback_data="review_rating_2")],
        [InlineKeyboardButton(text="⭐", callback_data="review_rating_1")],
        [InlineKeyboardButton(text="⬅ Назад", callback_data="reviews")]
    ])

    await callback.message.edit_text(
        "🌟 Здесь вы можете оставить честный отзыв о боте ДокГенератор!\n\n"
        "★★★★★ - Превосходно! Всё идеально.\n"
        "★★★★ - Хорошо, есть небольшие замечания.\n"
        "★★★ - Средне, ожидаю большего.\n"
        "★★ - Плохо, много недостатков.\n"
        "★ - Ужасно, совсем не понравилось.\n\n"
        "Ваш отзыв важен для нас!",
        reply_markup=review_markup,
        parse_mode="HTML"
    )
    await callback.answer()


@router.callback_query(F.data.startswith('review_rating_'))
async def handle_review_rating(callback: CallbackQuery, state: FSMContext):
    rating = int(callback.data.split('_')[2])
    await state.update_data(rating=rating)

    await callback.message.answer(
        "📝 Пожалуйста, напишите развернутый отзыв (минимум 20 символов).\n\n"
        "Ваше мнение поможет нам улучшить сервис!",
        reply_markup=ReplyKeyboardRemove()
    )
    await state.set_state(ReviewStates.waiting_for_review)
    await callback.answer()


@router.message(StateFilter(ReviewStates.waiting_for_review))
async def save_review(message: Message, state: FSMContext):
    data = await state.get_data()
    rating = data.get("rating", 0)
    review_text = message.text.strip()

    if len(review_text) < 20:
        await message.answer(
            "❌ Ваш отзыв слишком короткий. Пожалуйста, напишите более развернутый отзыв (минимум 20 символов).",
            reply_markup=ReplyKeyboardRemove()
        )
        return

    for pattern in BLACKLIST_PATTERNS:
        if re.search(pattern, review_text.lower()):
            await message.answer("❌ Ваш отзыв содержит неприемлемый контент и не может быть опубликован.")
            await state.clear()
            return

    publish_choice_markup = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Опубликовать анонимно", callback_data="publish_anonymously")],
        [InlineKeyboardButton(text="Опубликовать с моим ником", callback_data="publish_with_username")]
    ])

    await message.answer(
        "Спасибо за ваш отзыв! 🙏\n\n"
        "Хотите опубликовать отзыв анонимно или с вашим ником?",
        reply_markup=publish_choice_markup
    )
    await state.update_data(review_text=review_text)
    await state.set_state(ReviewStates.choose_publish_type)


@router.callback_query(StateFilter(ReviewStates.choose_publish_type))
async def process_publish_type(callback: CallbackQuery, state: FSMContext):
    choice = callback.data
    data = await state.get_data()
    rating = data.get("rating", 0)
    review_text = data.get("review_text", "")

    if choice == "publish_anonymously":
        publish_text = (
            f"🔥 Анонимный отзыв:\n\n"
            f"<b>Рейтинг:</b> {'⭐' * rating}\n"
            f"<b>Комментарий:</b> {review_text}"
        )
    else:
        username = callback.from_user.username or callback.from_user.first_name
        publish_text = (
            f"👉 Отзыв пользователя <a href='tg://user?id={callback.from_user.id}'>"
            f"{username}</a>:\n\n"
            f"<b>Рейтинг:</b> {'⭐' * rating}\n"
            f"<b>Комментарий:</b> {review_text}"
        )

    try:
        await callback.message.bot.send_message(
            chat_id=config.REVIEWS_CHANNEL_ID,
            text=publish_text,
            parse_mode="HTML"
        )
        await callback.message.answer(
            "✅ Спасибо за ваш отзыв! Он успешно опубликован!\n\n"
            "Вы можете посмотреть все отзывы в нашем канале: https://t.me/docgenerator",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="🔍 Посмотреть все отзывы", url="https://t.me/docgenerator")],
                [InlineKeyboardButton(text="🏠 Главное меню", callback_data="back_main")]
            ])
        )
    except Exception as e:
        logger.error(f"Ошибка отправки отзыва в канал: {e}")
        await callback.message.answer(
            "⚠️ Не удалось опубликовать отзыв. Попробуйте позже.\n\n"
            "Вы также можете написать нам в поддержку: @biz_annet"
        )

    await state.clear()
    await callback.answer()