import logging
from aiogram import Router, F
from aiogram.types import CallbackQuery, Message, InlineKeyboardButton, InlineKeyboardMarkup
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from config import config
from database.templates import (
    get_user_templates,
    create_user_template,
    get_user_template_by_id,
    update_user_template,
    delete_user_template
)
from texts.messages import (
    TEMPLATES_LIST_TEXT,
    NO_TEMPLATES_TEXT,
    TEMPLATE_MANAGEMENT_TEXT,
    DOCUMENT_DESCRIPTION_TEXT
)
from services.document_service import load_questions

logger = logging.getLogger('doc_bot.templates')
router = Router(name="templates_router")


class TemplateStates(StatesGroup):
    SELECTING_DOCUMENT = State()
    SELECTING_TEMPLATE_NAME = State()
    SAVING_TEMPLATE = State()
    EDITING_TEMPLATE = State()
    EDITING_FIELD = State()


@router.callback_query(F.data == "templates")
async def show_templates(callback: CallbackQuery):
    """Показывает список сохраненных шаблонов"""
    user_id = callback.from_user.id
    logger.info(f"Пользователь {user_id} запросил список шаблонов")

    try:
        # Получаем шаблоны пользователя
        templates = get_user_templates(user_id)

        if not templates:
            await callback.message.edit_text(
                NO_TEMPLATES_TEXT,
                parse_mode="HTML",
                reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                    [
                        InlineKeyboardButton(
                            text="➕ Создать шаблон",
                            callback_data="create_template"
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
        templates_text = TEMPLATES_LIST_TEXT

        # Добавляем шаблоны
        for i, template in enumerate(templates, 1):
            templates_text += (
                f"{i}. <b>{template['name']}</b>\n"
                f"   • Тип: {template['document_type']}\n"
                f"   • Создан: {template['created_at'].split(' ')[0]}\n\n"
            )

        # Создаем клавиатуру
        buttons = []

        # Добавляем кнопки для каждого шаблона
        for template in templates[:5]:  # Только первые 5 шаблонов
            buttons.append([
                InlineKeyboardButton(
                    text=f"🔖 {template['name']}",
                    callback_data=f"template_{template['id']}"
                )
            ])

        # Добавляем общие кнопки
        buttons.append([
            InlineKeyboardButton(
                text="➕ Создать шаблон",
                callback_data="create_template"
            )
        ])
        buttons.append([
            InlineKeyboardButton(
                text="🔄 Обновить",
                callback_data="templates"
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
            text=templates_text,
            parse_mode="HTML",
            reply_markup=markup
        )
        await callback.answer()

    except Exception as e:
        logger.error(f"Ошибка при отображении шаблонов: {e}", exc_info=True)
        await callback.answer("⚠️ Произошла ошибка при загрузке шаблонов", show_alert=True)
        await callback.answer()


@router.callback_query(F.data.startswith("template_"))
async def show_template_details(callback: CallbackQuery):
    """Показывает детали шаблона"""
    template_id = int(callback.data.split("_")[1])
    user_id = callback.from_user.id
    logger.info(f"Пользователь {user_id} запросил детали шаблона {template_id}")

    try:
        # Получаем шаблон
        template = get_user_template_by_id(user_id, template_id)

        if not template:
            await callback.answer("⚠️ Шаблон не найден", show_alert=True)
            await callback.answer()
            return

        # Формируем текст
        template_text = TEMPLATE_MANAGEMENT_TEXT.format(
            template_name=template['name'],
            document_type=template['document_type'],
            created_at=template['created_at'].split(' ')[0],
            updated_at=template['updated_at'].split(' ')[0]
        )

        # Создаем клавиатуру
        buttons = [
            [
                InlineKeyboardButton(
                    text="📝 Использовать шаблон",
                    callback_data=f"use_template_{template_id}"
                )
            ],
            [
                InlineKeyboardButton(
                    text="✏️ Редактировать шаблон",
                    callback_data=f"edit_template_{template_id}"
                )
            ],
            [
                InlineKeyboardButton(
                    text="🗑 Удалить шаблон",
                    callback_data=f"delete_template_{template_id}"
                )
            ],
            [
                InlineKeyboardButton(
                    text="⬅️ Назад к списку",
                    callback_data="templates"
                )
            ]
        ]

        markup = InlineKeyboardMarkup(inline_keyboard=buttons)

        await callback.message.edit_text(
            text=template_text,
            parse_mode="HTML",
            reply_markup=markup
        )
        await callback.answer()

    except Exception as e:
        logger.error(f"Ошибка при отображении деталей шаблона: {e}", exc_info=True)
        await callback.answer("⚠️ Произошла ошибка при загрузке деталей шаблона", show_alert=True)
        await callback.answer()


@router.callback_query(F.data == "create_template")
async def create_template_start(callback: CallbackQuery, state: FSMContext):
    """Начинает процесс создания шаблона"""
    user_id = callback.from_user.id
    logger.info(f"Пользователь {user_id} начал создание шаблона")

    try:
        text = (
            "🔖 <b>Создание шаблона</b>\n\n"
            "Введите название для нового шаблона:"
        )
        buttons = [
            [
                InlineKeyboardButton(
                    text="❌ Отмена",
                    callback_data="templates"
                )
            ]
        ]

        markup = InlineKeyboardMarkup(inline_keyboard=buttons)

        await callback.message.edit_text(
            text=text,
            parse_mode="HTML",
            reply_markup=markup
        )
        await state.set_state(TemplateStates.SELECTING_TEMPLATE_NAME)
        await callback.answer()

    except Exception as e:
        logger.error(f"Ошибка при начале создания шаблона: {e}", exc_info=True)
        await callback.answer("⚠️ Произошла ошибка", show_alert=True)
        await callback.answer()


@router.message(TemplateStates.SELECTING_TEMPLATE_NAME)
async def process_template_name(message: Message, state: FSMContext):
    user_id = message.from_user.id
    logger.info(f"Пользователь {user_id} ввел название шаблона: {message.text}")

    try:
        await state.update_data(template_name=message.text)
        text = (
            "🔖 <b>Создание шаблона</b>\n\n"
            "Выберите тип документа для шаблона:"
        )
        buttons = [
            [
                InlineKeyboardButton(
                    text="Договор оказания услуг",
                    callback_data="doc_type_service_contract"
                )
            ],
            [
                InlineKeyboardButton(
                    text="Политика конфиденциальности",
                    callback_data="doc_type_privacy_policy"
                )
            ],
            [
                InlineKeyboardButton(
                    text="Договор аренды",
                    callback_data="doc_type_rental_contract"
                )
            ],
            [
                InlineKeyboardButton(
                    text="Акт выполненных работ",
                    callback_data="doc_type_work_act"
                )
            ],
            [
                InlineKeyboardButton(
                    text="❌ Отмена",
                    callback_data="templates"
                )
            ]
        ]

        markup = InlineKeyboardMarkup(inline_keyboard=buttons)

        await message.answer(
            text=text,
            parse_mode="HTML",
            reply_markup=markup
        )

    except Exception as e:
        logger.error(f"Ошибка при обработке названия шаблона: {e}", exc_info=True)
        await message.answer("⚠️ Произошла ошибка", reply_markup=None)


@router.callback_query(F.data.startswith("doc_type_"))
async def select_document_type(callback: CallbackQuery, state: FSMContext):
    user_id = callback.from_user.id
    logger.info(f"Пользователь {user_id} выбрал тип документа")

    try:
        doc_type = callback.data.split("_")[2]
        await state.update_data(document_type=doc_type)

        text = (
            "🔖 <b>Создание шаблона</b>\n\n"
            "Введите данные для шаблона.\n\n"
            "Вы можете заполнить только те поля, которые часто повторяются."
        )

        buttons = [
            [
                InlineKeyboardButton(
                    text="📝 Начать заполнение",
                    callback_data="start_template_filling"
                )
            ],
            [
                InlineKeyboardButton(
                    text="❌ Отмена",
                    callback_data="templates"
                )
            ]
        ]

        markup = InlineKeyboardMarkup(inline_keyboard=buttons)

        await callback.message.edit_text(
            text=text,
            parse_mode="HTML",
            reply_markup=markup
        )

        # Устанавливаем состояние
        await state.set_state(TemplateStates.SAVING_TEMPLATE)
        await callback.answer()

    except Exception as e:
        logger.error(f"Ошибка при выборе типа документа: {e}", exc_info=True)
        await callback.answer("⚠️ Произошла ошибка", show_alert=True)
        await callback.answer()


@router.callback_query(F.data == "start_template_filling")
async def start_template_filling(callback: CallbackQuery, state: FSMContext):
    """Начинает процесс заполнения шаблона"""
    user_id = callback.from_user.id
    logger.info(f"Пользователь {user_id} начал заполнение шаблона")

    try:
        data = await state.get_data()
        document_type = data.get('document_type', 'service_contract')
        questions = await load_questions(state, document_type)

        await state.update_data(
            questions=questions,
            current_question=0,
            answers={}
        )

        await ask_template_question(callback, state)

    except Exception as e:
        logger.error(f"Ошибка при начале заполнения шаблона: {e}", exc_info=True)
        await callback.answer("⚠️ Произошла ошибка", show_alert=True)
        await callback.answer()


async def ask_template_question(callback: CallbackQuery, state: FSMContext):
    try:
        data = await state.get_data()
        questions = data.get('questions', [])
        current_question = data.get('current_question', 0)
        answers = data.get('answers', {})

        if current_question >= len(questions):
            await save_template(callback, state)
            return

        question = questions[current_question]
        question_text = (
            f"🔖 <b>Заполнение шаблона</b>\n\n"
            f"Вопрос {current_question + 1}/{len(questions)}:\n\n"
            f"<b>{question['label']}</b>\n"
            f"{question['description']}"
        )

        buttons = []

        if current_question > 0:
            buttons.append([
                InlineKeyboardButton(
                    text="⬅️ Назад",
                    callback_data="prev_template_question"
                )
            ])

        # Кнопка "Пропустить"
        buttons.append([
            InlineKeyboardButton(
                text="➡️ Пропустить",
                callback_data="skip_template_question"
            )
        ])

        # Кнопка "Отмена"
        buttons.append([
            InlineKeyboardButton(
                text="❌ Отмена",
                callback_data="templates"
            )
        ])

        markup = InlineKeyboardMarkup(inline_keyboard=buttons)

        await callback.message.edit_text(
            text=question_text,
            parse_mode="HTML",
            reply_markup=markup
        )
        await callback.answer()

    except Exception as e:
        logger.error(f"Ошибка при задавании вопроса шаблона: {e}", exc_info=True)
        await callback.answer("⚠️ Произошла ошибка", show_alert=True)
        await callback.answer()


@router.callback_query(F.data == "prev_template_question")
async def prev_template_question(callback: CallbackQuery, state: FSMContext):
    """Переход к предыдущему вопросу при заполнении шаблона"""
    data = await state.get_data()
    current_question = data.get('current_question', 0)

    if current_question > 0:
        await state.update_data(current_question=current_question - 1)

    await ask_template_question(callback, state)


@router.callback_query(F.data == "skip_template_question")
async def skip_template_question(callback: CallbackQuery, state: FSMContext):
    """Пропуск текущего вопроса при заполнении шаблона"""
    data = await state.get_data()
    current_question = data.get('current_question', 0)

    await state.update_data(current_question=current_question + 1)

    await ask_template_question(callback, state)


@router.message(TemplateStates.SAVING_TEMPLATE)
async def process_template_answer(message: Message, state: FSMContext):
    """Обрабатывает ответ при заполнении шаблона"""
    user_id = message.from_user.id
    logger.info(f"Пользователь {user_id} дал ответ при заполнении шаблона")

    try:
        data = await state.get_data()
        questions = data.get('questions', [])
        current_question = data.get('current_question', 0)
        answers = data.get('answers', {})

        if current_question >= len(questions):
            await message.answer("⚠️ Все вопросы уже заполнены", reply_markup=None)
            return

        # Получаем текущий вопрос
        question = questions[current_question]

        # Сохраняем ответ
        answers[question["id"]] = message.text
        await state.update_data(answers=answers)

        # Переходим к следующему вопросу
        await state.update_data(current_question=current_question + 1)

        # Задаем следующий вопрос
        await ask_template_question(message, state)

    except Exception as e:
        logger.error(f"Ошибка при обработке ответа шаблона: {e}", exc_info=True)
        await message.answer("⚠️ Произошла ошибка", reply_markup=None)


async def ask_template_question(message: Message, state: FSMContext):
    """Альтернативная версия для Message"""
    try:
        data = await state.get_data()
        questions = data.get('questions', [])
        current_question = data.get('current_question', 0)

        if current_question >= len(questions):
            await save_template(message, state)
            return

        # Получаем текущий вопрос
        question = questions[current_question]

        # Формируем текст вопроса
        question_text = (
            f"🔖 <b>Заполнение шаблона</b>\n\n"
            f"Вопрос {current_question + 1}/{len(questions)}:\n\n"
            f"<b>{question['label']}</b>\n"
            f"{question['description']}"
        )

        # Создаем клавиатуру
        buttons = []

        # Кнопка "Назад" если это не первый вопрос
        if current_question > 0:
            buttons.append([
                InlineKeyboardButton(
                    text="⬅️ Назад",
                    callback_data="prev_template_question"
                )
            ])

        # Кнопка "Пропустить"
        buttons.append([
            InlineKeyboardButton(
                text="➡️ Пропустить",
                callback_data="skip_template_question"
            )
        ])

        # Кнопка "Отмена"
        buttons.append([
            InlineKeyboardButton(
                text="❌ Отмена",
                callback_data="templates"
            )
        ])

        markup = InlineKeyboardMarkup(inline_keyboard=buttons)

        await message.answer(
            text=question_text,
            parse_mode="HTML",
            reply_markup=markup
        )

    except Exception as e:
        logger.error(f"Ошибка при задавании вопроса шаблона: {e}", exc_info=True)
        await message.answer("⚠️ Произошла ошибка", reply_markup=None)


async def save_template(callback: CallbackQuery, state: FSMContext):
    """Сохраняет шаблон"""
    user_id = callback.from_user.id
    logger.info(f"Пользователь {user_id} сохраняет шаблон")

    try:
        # Получаем данные из состояния
        data = await state.get_data()
        template_name = data.get('template_name', 'Мой шаблон')
        document_type = data.get('document_type', 'service_contract')
        answers = data.get('answers', {})

        # Сохраняем шаблон в базу данных
        template_id = create_user_template(
            user_id=user_id,
            name=template_name,
            document_type=document_type,
            data=answers
        )

        if template_id:
            await callback.message.edit_text(
                f"✅ Шаблон '{template_name}' успешно сохранен!\n\n"
                "Теперь вы можете использовать его для быстрого заполнения документов.",
                reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                    [
                        InlineKeyboardButton(
                            text="🔖 Перейти к шаблонам",
                            callback_data="templates"
                        )
                    ]
                ])
            )
        else:
            await callback.message.edit_text(
                "⚠️ Не удалось сохранить шаблон. Попробуйте еще раз.",
                reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                    [
                        InlineKeyboardButton(
                            text="🔖 Перейти к шаблонам",
                            callback_data="templates"
                        )
                    ]
                ])
            )

        # Сбрасываем состояние
        await state.clear()
        await callback.answer()

    except Exception as e:
        logger.error(f"Ошибка при сохранении шаблона: {e}", exc_info=True)
        await callback.answer("⚠️ Произошла ошибка при сохранении шаблона", show_alert=True)
        await callback.answer()


@router.callback_query(F.data.startswith("use_template_"))
async def use_template(callback: CallbackQuery, state: FSMContext):
    """Использует шаблон для заполнения документа"""
    template_id = int(callback.data.split("_")[2])
    user_id = callback.from_user.id
    logger.info(f"Пользователь {user_id} использует шаблон {template_id} для заполнения документа")

    try:
        # Получаем шаблон
        template = get_user_template_by_id(user_id, template_id)

        if not template:
            await callback.answer("⚠️ Шаблон не найден", show_alert=True)
            await callback.answer()
            return

        # Сохраняем данные шаблона в состоянии
        await state.update_data(
            template_data=template['data'],
            template_name=template['name']
        )

        await callback.message.edit_text(
            f"🔖 <b>Использование шаблона</b>\n\n"
            f"Вы выбрали шаблон: <b>{template['name']}</b>\n\n"
            "Теперь выберите документ, который вы хотите заполнить с помощью этого шаблона:",
            parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [
                    InlineKeyboardButton(
                        text="📝 Договор оказания услуг",
                        callback_data="fill_service_contract"
                    )
                ],
                [
                    InlineKeyboardButton(
                        text="📝 Политика конфиденциальности",
                        callback_data="fill_privacy_policy"
                    )
                ],
                [
                    InlineKeyboardButton(
                        text="⬅️ Назад",
                        callback_data="templates"
                    )
                ]
            ])
        )
        await callback.answer()

    except Exception as e:
        logger.error(f"Ошибка при использовании шаблона: {e}", exc_info=True)
        await callback.answer("⚠️ Произошла ошибка", show_alert=True)
        await callback.answer()


@router.callback_query(F.data.startswith("edit_template_"))
async def edit_template(callback: CallbackQuery, state: FSMContext):
    """Начинает редактирование шаблона"""
    template_id = int(callback.data.split("_")[2])
    user_id = callback.from_user.id
    logger.info(f"Пользователь {user_id} начал редактирование шаблона {template_id}")

    try:
        # Получаем шаблон
        template = get_user_template_by_id(user_id, template_id)

        if not template:
            await callback.answer("⚠️ Шаблон не найден", show_alert=True)
            await callback.answer()
            return

        # Сохраняем ID шаблона в состоянии
        await state.update_data(
            editing_template_id=template_id,
            template_name=template['name'],
            document_type=template['document_type'],
            current_question=0,
            answers=template['data']
        )

        questions = await load_questions(state, template['document_type'])

        await state.update_data(questions=questions)

        # Устанавливаем состояние
        await state.set_state(TemplateStates.EDITING_TEMPLATE)

        # Показываем первый вопрос для редактирования
        await edit_template_question(callback, state)

    except Exception as e:
        logger.error(f"Ошибка при начале редактирования шаблона: {e}", exc_info=True)
        await callback.answer("⚠️ Произошла ошибка", show_alert=True)
        await callback.answer()


async def edit_template_question(callback: CallbackQuery, state: FSMContext):
    """Показывает вопрос для редактирования шаблона"""
    try:
        data = await state.get_data()
        questions = data.get('questions', [])
        current_question = data.get('current_question', 0)
        answers = data.get('answers', {})

        if current_question >= len(questions):
            await save_edited_template(callback, state)
            return

        # Получаем текущий вопрос
        question = questions[current_question]
        current_answer = answers.get(question["id"], "")

        # Формируем текст вопроса
        question_text = (
            f"🔖 <b>Редактирование шаблона</b>\n\n"
            f"Вопрос {current_question + 1}/{len(questions)}:\n\n"
            f"<b>{question['label']}</b>\n"
            f"{question['description']}\n\n"
            f"Текущее значение: {current_answer if current_answer else 'не задано'}"
        )

        # Создаем клавиатуру
        buttons = []

        # Кнопка "Назад" если это не первый вопрос
        if current_question > 0:
            buttons.append([
                InlineKeyboardButton(
                    text="⬅️ Назад",
                    callback_data="prev_edit_question"
                )
            ])

        # Кнопка "Пропустить"
        buttons.append([
            InlineKeyboardButton(
                text="➡️ Пропустить",
                callback_data="skip_edit_question"
            )
        ])

        # Кнопка "Отмена"
        buttons.append([
            InlineKeyboardButton(
                text="❌ Отмена",
                callback_data="templates"
            )
        ])

        markup = InlineKeyboardMarkup(inline_keyboard=buttons)

        await callback.message.edit_text(
            text=question_text,
            parse_mode="HTML",
            reply_markup=markup
        )
        await callback.answer()

    except Exception as e:
        logger.error(f"Ошибка при показе вопроса редактирования: {e}", exc_info=True)
        await callback.answer("⚠️ Произошла ошибка", show_alert=True)
        await callback.answer()


@router.callback_query(F.data == "prev_edit_question")
async def prev_edit_question(callback: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    current_question = data.get('current_question', 0)

    if current_question > 0:
        await state.update_data(current_question=current_question - 1)

    await edit_template_question(callback, state)


@router.callback_query(F.data == "skip_edit_question")
async def skip_edit_question(callback: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    current_question = data.get('current_question', 0)

    await state.update_data(current_question=current_question + 1)

    await edit_template_question(callback, state)


@router.message(TemplateStates.EDITING_TEMPLATE)
async def process_edit_answer(message: Message, state: FSMContext):
    """Обрабатывает ответ при редактировании шаблона"""
    user_id = message.from_user.id
    logger.info(f"Пользователь {user_id} дал ответ при редактировании шаблона")

    try:
        data = await state.get_data()
        questions = data.get('questions', [])
        current_question = data.get('current_question', 0)
        answers = data.get('answers', {})

        if current_question >= len(questions):
            await message.answer("⚠️ Все вопросы уже заполнены", reply_markup=None)
            return

        # Получаем текущий вопрос
        question = questions[current_question]

        # Сохраняем ответ
        answers[question["id"]] = message.text
        await state.update_data(answers=answers)

        # Переходим к следующему вопросу
        await state.update_data(current_question=current_question + 1)

        # Задаем следующий вопрос
        await edit_template_question(message, state)

    except Exception as e:
        logger.error(f"Ошибка при обработке ответа редактирования: {e}", exc_info=True)
        await message.answer("⚠️ Произошла ошибка", reply_markup=None)


async def edit_template_question(message: Message, state: FSMContext):
    try:
        data = await state.get_data()
        questions = data.get('questions', [])
        current_question = data.get('current_question', 0)
        answers = data.get('answers', {})

        if current_question >= len(questions):
            await save_edited_template(message, state)
            return

        # Получаем текущий вопрос
        question = questions[current_question]
        current_answer = answers.get(question["id"], "")

        # Формируем текст вопроса
        question_text = (
            f"🔖 <b>Редактирование шаблона</b>\n\n"
            f"Вопрос {current_question + 1}/{len(questions)}:\n\n"
            f"<b>{question['label']}</b>\n"
            f"{question['description']}\n\n"
            f"Текущее значение: {current_answer if current_answer else 'не задано'}"
        )

        # Создаем клавиатуру
        buttons = []

        # Кнопка "Назад" если это не первый вопрос
        if current_question > 0:
            buttons.append([
                InlineKeyboardButton(
                    text="⬅️ Назад",
                    callback_data="prev_edit_question"
                )
            ])

        # Кнопка "Пропустить"
        buttons.append([
            InlineKeyboardButton(
                text="➡️ Пропустить",
                callback_data="skip_edit_question"
            )
        ])

        # Кнопка "Отмена"
        buttons.append([
            InlineKeyboardButton(
                text="❌ Отмена",
                callback_data="templates"
            )
        ])

        markup = InlineKeyboardMarkup(inline_keyboard=buttons)

        await message.answer(
            text=question_text,
            parse_mode="HTML",
            reply_markup=markup
        )

    except Exception as e:
        logger.error(f"Ошибка при показе вопроса редактирования: {e}", exc_info=True)
        await message.answer("⚠️ Произошла ошибка", reply_markup=None)


async def save_edited_template(callback: CallbackQuery, state: FSMContext):
    """Сохраняет отредактированный шаблон"""
    user_id = callback.from_user.id
    logger.info(f"Пользователь {user_id} сохраняет отредактированный шаблон")

    try:
        # Получаем данные из состояния
        data = await state.get_data()
        template_id = data.get('editing_template_id')
        answers = data.get('answers', {})

        if not template_id:
            await callback.answer("⚠️ Не удалось найти шаблон", show_alert=True)
            await callback.answer()
            return

        # Обновляем шаблон в базе данных
        success = update_user_template(
            template_id=template_id,
            data=answers
        )

        if success:
            await callback.message.edit_text(
                "✅ Шаблон успешно обновлен!",
                reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                    [
                        InlineKeyboardButton(
                            text="🔖 Перейти к шаблонам",
                            callback_data="templates"
                        )
                    ]
                ])
            )
        else:
            await callback.message.edit_text(
                "⚠️ Не удалось обновить шаблон. Попробуйте еще раз.",
                reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                    [
                        InlineKeyboardButton(
                            text="🔖 Перейти к шаблонам",
                            callback_data="templates"
                        )
                    ]
                ])
            )

        # Сбрасываем состояние
        await state.clear()
        await callback.answer()

    except Exception as e:
        logger.error(f"Ошибка при сохранении отредактированного шаблона: {e}", exc_info=True)
        await callback.answer("⚠️ Произошла ошибка при сохранении шаблона", show_alert=True)
        await callback.answer()


@router.callback_query(F.data.startswith("delete_template_"))
async def delete_template(callback: CallbackQuery):
    """Удаляет шаблон"""
    template_id = int(callback.data.split("_")[2])
    user_id = callback.from_user.id
    logger.info(f"Пользователь {user_id} удаляет шаблон {template_id}")

    try:
        # Удаляем шаблон
        success = delete_user_template(user_id, template_id)

        if success:
            await callback.answer("✅ Шаблон успешно удален!", show_alert=True)
        else:
            await callback.answer("⚠️ Не удалось удалить шаблон", show_alert=True)

        # Показываем обновленный список шаблонов
        await show_templates(callback)

    except Exception as e:
        logger.error(f"Ошибка при удалении шаблона: {e}", exc_info=True)
        await callback.answer("⚠️ Произошла ошибка при удалении шаблона", show_alert=True)
        await callback.answer()