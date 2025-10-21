import logging
from datetime import datetime
from aiogram import Router, F
from aiogram.types import CallbackQuery, Message, InlineKeyboardButton, InlineKeyboardMarkup
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from config import config
from services.document_service import get_template_by_id_from_filesystem, get_template_info, load_questions
from services.pricing import get_template_price, get_autogeneration_price
from services.validators import validate_field
from database.cart import add_to_cart, get_user_cart
from database.drafts import save_draft, delete_draft, get_last_template_draft, save_last_template_draft
from texts.messages import (
    FILLING_QUESTION_TEXT,
    FILLING_REVIEW_TEXT,
    CART_TEXT
)

logger = logging.getLogger('doc_bot.filling')
router = Router(name="filling_router")


FIELDS_NEVER_FROM_DRAFT = {
    "contract_date",
    "contract_end_date",
    "contract_number",
    "inventory_date",
    "acceptance_date",
    "act_date",
    "waybill_date",
    "order_id",
    "document_number",
    "current_date",
    "date_of_signature"
}


class FillingStates(StatesGroup):
    WAITING_FOR_ANSWER = State()
    REVIEWING = State()
    SELECTING_MULTI = State()
    WAITING_FOR_CHOICE = State()
    USE_LAST_DRAFT_DECISION = State()
    INVENTORY_ASKING_NAME = State()
    INVENTORY_ASKING_QUANTITY = State()
    INVENTORY_ASKING_CONDITION = State()


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
        doc_type = "автогенерация" if item.get('price_type') == 'autogen' else "шаблон"
        price = item['price']
        items_list += f"{i}. {item['doc_name']} ({doc_type}) - {price} ₽\n"
    return items_list


def create_multiselect_keyboard(selected: list, options: list, step: str) -> InlineKeyboardMarkup:
    buttons = []
    for option in options:
        text = f"✅ {option}" if option in selected else f"⬜ {option}"
        buttons.append([InlineKeyboardButton(text=text, callback_data=f"multi_{step}:{option}")])
    buttons.append([InlineKeyboardButton(text="✅ Готово", callback_data=f"multi_{step}:done")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def create_choice_keyboard(options: list, step: str) -> InlineKeyboardMarkup:
    buttons = []
    for option in options:
        buttons.append([InlineKeyboardButton(text=option, callback_data=f"ch_{step}:{option}")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def create_prefill_keyboard(step_index: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="✅ Оставить", callback_data=f"prefill_keep_{step_index}"),
            InlineKeyboardButton(text="✏️ Изменить", callback_data=f"prefill_edit_{step_index}")
        ],
        [
            InlineKeyboardButton(text="⏭ Пропустить", callback_data=f"skip_{step_index}")
        ],
        [
            InlineKeyboardButton(text="🗑️ Отменить", callback_data="cancel_filling")
        ]
    ])


@router.callback_query(F.data.startswith("fill_"))
async def start_filling(callback: CallbackQuery, state: FSMContext):
    """Начинает процесс заполнения документа"""
    user_id = callback.from_user.id
    logger.info(f"Пользователь {user_id} начал заполнение документа: {callback.data}")

    try:
        parts = callback.data.split("_")
        if len(parts) < 4:
            await callback.answer("⚠️ Некорректный запрос", show_alert=True)
            return

        category_key = parts[1]
        doc_id = "_".join(parts[2:-1])
        fill_type = parts[-1]

        logger.info(f"Пользователь {user_id} начал заполнение документа {doc_id} (тип: {fill_type})")

        template = get_template_by_id_from_filesystem(category_key, doc_id)
        if not template:
            logger.error(f"Шаблон {doc_id} в категории {category_key} не найден")
            await callback.answer("❌ Шаблон не найден", show_alert=True)
            return

        template_info = get_template_info(template['template_name'], category_key)
        questions = load_questions(template['template_name'])
        if not questions:
            logger.error(f"Вопросы для шаблона {template['template_name']} не найдены")
            await callback.answer("❌ Не удалось загрузить вопросы для заполнения", show_alert=True)
            return

        last_draft = get_last_template_draft(user_id, doc_id)
        if last_draft is not None:
            await state.update_data(
                category=category_key,
                doc_id=doc_id,
                doc_info=template_info,
                fill_type=fill_type,
                questions=questions,
                last_draft=last_draft
            )
            await callback.message.edit_text(
                "📝 Найден ваш последний договор.\nИспользовать его данные как основу?",
                reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                    [InlineKeyboardButton(text="✅ Да", callback_data="use_last_draft_yes")],
                    [InlineKeyboardButton(text="❌ Нет", callback_data="use_last_draft_no")]
                ])
            )
            await state.set_state(FillingStates.USE_LAST_DRAFT_DECISION)
        else:
            await state.update_data(
                category=category_key,
                doc_id=doc_id,
                doc_info=template_info,
                fill_type=fill_type,
                questions=questions,
                current_question=0,
                answers={},
                use_last_draft=False
            )
            await ask_question_callback(callback, state)

    except Exception as e:
        logger.error(f"Ошибка при начале заполнения: {e}", exc_info=True)
        await callback.answer("⚠️ Произошла ошибка при начале заполнения документа", show_alert=True)


@router.callback_query(F.data == "use_last_draft_yes")
async def use_last_draft_yes(callback: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    await state.update_data(
        current_question=0,
        answers={},
        use_last_draft=True
    )
    await ask_question_callback(callback, state)
    await callback.answer()


@router.callback_query(F.data == "use_last_draft_no")
async def use_last_draft_no(callback: CallbackQuery, state: FSMContext):
    await state.update_data(
        current_question=0,
        answers={},
        use_last_draft=False
    )
    await ask_question_callback(callback, state)
    await callback.answer()


async def check_condition_and_get_next_valid_question_index(questions: list, answers: dict, current_index: int) -> int:
    index = current_index
    while index < len(questions):
        question = questions[index]
        condition_str = question.get("condition")

        if condition_str:
            if "==" in condition_str:
                left_side, right_side = condition_str.split("==", 1)
                left_side = left_side.strip()
                right_side = right_side.strip().strip("'\"")

                dependent_question_index = None
                for idx, q in enumerate(questions):
                    if q.get("step") == left_side:
                        dependent_question_index = str(idx)
                        break

                if dependent_question_index is not None:
                    user_answer = answers.get(dependent_question_index)
                    if user_answer != right_side:
                        logger.debug(f"Условие '{condition_str}' не выполнено для вопроса {index}, пропускаем.")
                        index += 1
                        continue
                    else:
                        logger.debug(f"Условие '{condition_str}' выполнено для вопроса {index}.")
                        break
                else:
                    logger.warning(f"Зависимый вопрос '{left_side}' не найден для условия '{condition_str}' в вопросе {index}.")
                    index += 1
                    continue
            else:
                logger.warning(f"Неподдерживаемый формат условия '{condition_str}' в вопросе {index}.")
                index += 1
                continue
        else:
            logger.debug(f"Нет условия для вопроса {index}, задаём его.")
            break

    return index


async def ask_question_callback(callback: CallbackQuery, state: FSMContext):
    try:
        data = await state.get_data()
        doc_id = data.get("doc_id")
        questions = data["questions"]
        current_question_index = data["current_question"]

        # === СПЕЦИАЛЬНАЯ ЛОГИКА ДЛЯ ОПИСИ ИМУЩЕСТВА ===
        if doc_id == "inventory_2025":
            if current_question_index >= len(questions):
                # Перешли к динамической части
                add_first = data["answers"].get("6")  # индекс вопроса add_first_item
                if add_first == "Нет":
                    await finalize_inventory_filling(callback, state)
                    return
                else:
                    await state.update_data(inventory_item_index=1)
                    await ask_inventory_name(callback, state, 1)
                    return

        # === СТАНДАРТНАЯ ЛОГИКА ===
        use_last_draft = data.get("use_last_draft", False)
        last_draft = data.get("last_draft", {})
        next_valid_question_index = await check_condition_and_get_next_valid_question_index(
            questions, data["answers"], current_question_index
        )

        if next_valid_question_index >= len(questions):
            await save_draft_to_db(callback.from_user.id, data)
            save_last_template_draft(callback.from_user.id, data["doc_id"], data["answers"])
            await show_review_message(callback, state)
            return

        if next_valid_question_index != current_question_index:
            await state.update_data(current_question=next_valid_question_index)
            current_question_index = next_valid_question_index

        question = questions[current_question_index]
        step_name = question.get("step")

        should_use_prefill = (
            use_last_draft
            and step_name is not None
            and step_name not in FIELDS_NEVER_FROM_DRAFT
            and str(current_question_index) not in data["answers"]
        )

        prefill_value = None
        if should_use_prefill:
            prefill_value = last_draft.get(str(current_question_index)) or last_draft.get(step_name)

        if question.get("type") == "choice":
            markup = create_choice_keyboard(question["options"], str(current_question_index))
            question_text = FILLING_QUESTION_TEXT.format(
                question_number=current_question_index + 1,
                total_questions=len(questions),
                question_text=question['text'],
                description=question.get('hint', ''),
                example_section=""
            )
            await callback.message.edit_text(text=question_text, parse_mode="HTML", reply_markup=markup)
            await state.set_state(FillingStates.WAITING_FOR_CHOICE)
            return

        if question.get("type") == "multi_select":
            selected = data["answers"].get(str(current_question_index), [])
            markup = create_multiselect_keyboard(selected, question["options"], str(current_question_index))
            await callback.message.edit_text(
                text=question["text"] + f"\n\n{question.get('hint', '')}",
                reply_markup=markup
            )
            await state.set_state(FillingStates.SELECTING_MULTI)
            return

        example_section = ""
        if question.get("example"):
            example_section = f"Пример: <i>{question['example']}</i>"

        question_text = FILLING_QUESTION_TEXT.format(
            question_number=current_question_index + 1,
            total_questions=len(questions),
            question_text=question['text'],
            description=question.get('hint', ''),
            example_section=example_section
        )

        if prefill_value and prefill_value != "______":
            question_text += f"\n\n<b>Текущее значение:</b> <i>{prefill_value}</i>"
            markup = create_prefill_keyboard(str(current_question_index))
            await callback.message.edit_text(text=question_text, parse_mode="HTML", reply_markup=markup)
            await state.set_state(FillingStates.WAITING_FOR_ANSWER)
        else:
            buttons = [
                [InlineKeyboardButton(text="⏭ Пропустить", callback_data=f"skip_{current_question_index}")],
                [InlineKeyboardButton(text="🗑️ Отменить", callback_data="cancel_filling")]
            ]
            markup = InlineKeyboardMarkup(inline_keyboard=buttons)
            if current_question_index == 0:
                await callback.message.edit_text(text=question_text, parse_mode="HTML", reply_markup=markup)
            else:
                await callback.message.answer(text=question_text, parse_mode="HTML", reply_markup=markup)
            await state.set_state(FillingStates.WAITING_FOR_ANSWER)

    except Exception as e:
        logger.error(f"Ошибка при задавании вопроса: {e}", exc_info=True)
        await callback.answer("⚠️ Произошла ошибка при задавании вопроса", show_alert=True)


async def finalize_inventory_filling(callback: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    await save_draft_to_db(callback.from_user.id, data)
    save_last_template_draft(callback.from_user.id, data["doc_id"], data["answers"])
    await show_review_message(callback, state)


async def ask_inventory_name(callback: CallbackQuery, state: FSMContext, item_index: int):
    text = f"➕ <b>{item_index}. Название предмета:</b>\nНапример: диван, холодильник, шкаф"
    markup = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="⏭ Пропустить всё", callback_data="inventory_skip_all")],
        [InlineKeyboardButton(text="🗑️ Отменить", callback_data="cancel_filling")]
    ])
    await callback.message.edit_text(text=text, parse_mode="HTML", reply_markup=markup)
    await state.set_state(FillingStates.INVENTORY_ASKING_NAME)


async def ask_inventory_quantity(message: Message, state: FSMContext, item_index: int):
    text = f"➕ <b>{item_index}. Количество:</b>\nЦелое число (например: 1, 2)"
    markup = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="⏭ Пропустить всё", callback_data="inventory_skip_all")],
        [InlineKeyboardButton(text="🗑️ Отменить", callback_data="cancel_filling")]
    ])
    await message.answer(text=text, parse_mode="HTML", reply_markup=markup)
    await state.set_state(FillingStates.INVENTORY_ASKING_QUANTITY)


async def ask_inventory_condition(message: Message, state: FSMContext, item_index: int):
    text = f"➕ <b>{item_index}. Состояние:</b>\nОпишите состояние (например: «хорошее, без повреждений»)"
    markup = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="⏭ Пропустить всё", callback_data="inventory_skip_all")],
        [InlineKeyboardButton(text="🗑️ Отменить", callback_data="cancel_filling")]
    ])
    await message.answer(text=text, parse_mode="HTML", reply_markup=markup)
    await state.set_state(FillingStates.INVENTORY_ASKING_CONDITION)


async def ask_add_more(message: Message, state: FSMContext, item_index: int):
    markup = create_choice_keyboard(["Да", "Нет"], "inventory_add_more")
    await message.answer("➕ <b>Добавить ещё предмет?</b>", reply_markup=markup, parse_mode="HTML")
    await state.update_data(inventory_item_index=item_index)


@router.callback_query(F.data == "inventory_skip_all")
async def inventory_skip_all(callback: CallbackQuery, state: FSMContext):
    await finalize_inventory_filling(callback, state)
    await callback.answer()


@router.callback_query(F.data.startswith("ch_inventory_add_more"))
async def handle_inventory_add_more(callback: CallbackQuery, state: FSMContext):
    choice = callback.data.split(":")[1]
    if choice == "Нет":
        await finalize_inventory_filling(callback, state)
    else:
        data = await state.get_data()
        item_index = data.get("inventory_item_index", 1) + 1
        await state.update_data(inventory_item_index=item_index)
        await ask_inventory_name(callback, state, item_index)
    await callback.answer()


@router.message(FillingStates.INVENTORY_ASKING_NAME)
async def process_inventory_name(message: Message, state: FSMContext):
    data = await state.get_data()
    item_index = data["inventory_item_index"]
    answers = data.get("answers", {})
    answers[f"item_{item_index}_name"] = message.text
    await state.update_data(answers=answers)
    await ask_inventory_quantity(message, state, item_index)


@router.message(FillingStates.INVENTORY_ASKING_QUANTITY)
async def process_inventory_quantity(message: Message, state: FSMContext):
    data = await state.get_data()
    item_index = data["inventory_item_index"]
    answers = data.get("answers", {})
    answers[f"item_{item_index}_quantity"] = message.text
    await state.update_data(answers=answers)
    await ask_inventory_condition(message, state, item_index)


@router.message(FillingStates.INVENTORY_ASKING_CONDITION)
async def process_inventory_condition(message: Message, state: FSMContext):
    data = await state.get_data()
    item_index = data["inventory_item_index"]
    answers = data.get("answers", {})
    answers[f"item_{item_index}_condition"] = message.text
    await state.update_data(answers=answers)
    await ask_add_more(message, state, item_index)


@router.callback_query(F.data.startswith("prefill_keep_"))
async def prefill_keep(callback: CallbackQuery, state: FSMContext):
    question_index = callback.data.split("_")[-1]
    data = await state.get_data()
    last_draft = data.get("last_draft", {})
    question = data["questions"][int(question_index)]
    step_name = question.get("step")
    value = last_draft.get(question_index) or last_draft.get(step_name) or "______"

    answers = data.get("answers", {})
    answers[question_index] = value
    await state.update_data(answers=answers, current_question=int(question_index) + 1)
    await ask_question_callback(callback, state)
    await callback.answer()


@router.callback_query(F.data.startswith("prefill_edit_"))
async def prefill_edit(callback: CallbackQuery, state: FSMContext):
    question_index = callback.data.split("_")[-1]
    await state.update_data(editing_prefill_index=question_index)
    question = (await state.get_data())["questions"][int(question_index)]
    await callback.message.answer(
        f"✏️ Введите новое значение для:\n{question['text']}",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="⏭ Пропустить", callback_data=f"skip_{question_index}")],
            [InlineKeyboardButton(text="🗑️ Отменить", callback_data="cancel_filling")]
        ])
    )
    await state.set_state(FillingStates.WAITING_FOR_ANSWER)
    await callback.answer()


@router.callback_query(F.data.startswith("ch_"))
async def handle_choice_selection(callback: CallbackQuery, state: FSMContext):
    try:
        data = await state.get_data()
        questions = data["questions"]
        answers = data.get("answers", {})

        parts = callback.data.split(":", 1)
        if len(parts) < 2 or parts[0].split('_')[0] != "ch":
            await callback.answer("⚠️ Некорректный запрос", show_alert=True)
            return

        question_index_str = parts[0].split('_', 1)[1]
        selected_option_text = parts[1]

        question = questions[int(question_index_str)]
        if selected_option_text not in question.get("options", []):
             await callback.answer("⚠️ Некорректный вариант", show_alert=True)
             return

        answers[question_index_str] = selected_option_text
        await state.update_data(answers=answers, current_question=int(question_index_str) + 1)
        await ask_question_callback(callback, state)
        await callback.answer()

    except Exception as e:
        logger.error(f"Ошибка при обработке выбора: {e}", exc_info=True)
        await callback.answer("⚠️ Ошибка выбора", show_alert=True)


@router.callback_query(F.data.startswith("multi_"))
async def handle_multiselect(callback: CallbackQuery, state: FSMContext):
    try:
        data = await state.get_data()
        answers = data.get("answers", {})
        current_question = callback.data.split(":", 1)[0].split("_", 1)[1]
        action = callback.data.split(":", 1)[1]

        selected = answers.get(current_question, [])

        if action == "done":
            answers[current_question] = selected
            await state.update_data(answers=answers, current_question=int(current_question) + 1)
            await ask_question_callback(callback, state)
            return

        if action in selected:
            selected.remove(action)
        else:
            selected.append(action)

        answers[current_question] = selected
        await state.update_data(answers=answers)

        question = data["questions"][int(current_question)]
        markup = create_multiselect_keyboard(selected, question["options"], current_question)
        await callback.message.edit_reply_markup(reply_markup=markup)
        await callback.answer()
    except Exception as e:
        logger.error(f"Ошибка при обработке multi_select: {e}", exc_info=True)
        await callback.answer("⚠️ Ошибка выбора", show_alert=True)


@router.message(FillingStates.WAITING_FOR_CHOICE)
async def process_choice_answer(message: Message, state: FSMContext):
    await message.answer("Пожалуйста, используйте кнопки для выбора.")


@router.message(FillingStates.WAITING_FOR_ANSWER)
async def process_answer(message: Message, state: FSMContext):
    try:
        data = await state.get_data()
        editing_index = data.get("editing_prefill_index")
        if editing_index is not None:
            current_question = int(editing_index)
            await state.update_data(editing_prefill_index=None)
        else:
            current_question = data["current_question"]

        questions = data["questions"]
        answers = data["answers"]
        question = questions[current_question]

        is_valid, error_message = validate_field(question, message.text)
        if not is_valid:
            await message.answer(
                f"❌ {error_message}\n\nПожалуйста, введите корректное значение:",
                reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                    [InlineKeyboardButton(text="⏭ Пропустить", callback_data=f"skip_{current_question}")],
                    [InlineKeyboardButton(text="🗑️ Отменить", callback_data="cancel_filling")]
                ])
            )
            return

        answers[str(current_question)] = message.text
        await state.update_data(current_question=current_question + 1, answers=answers)
        await ask_next_question_from_message(message, state)

    except Exception as e:
        logger.error(f"Ошибка при обработке ответа: {e}", exc_info=True)
        await message.answer("⚠️ Произошла ошибка при обработке ответа")


async def ask_next_question_from_message(message: Message, state: FSMContext):
    try:
        data = await state.get_data()
        doc_id = data.get("doc_id")
        questions = data["questions"]
        current_question_index = data["current_question"]

        # === СПЕЦИАЛЬНАЯ ЛОГИКА ДЛЯ ОПИСИ ИМУЩЕСТВА ===
        if doc_id == "inventory_2025":
            if current_question_index >= len(questions):
                add_first = data["answers"].get("6")
                if add_first == "Нет":
                    await finalize_inventory_filling_from_message(message, state)
                    return
                else:
                    await state.update_data(inventory_item_index=1)
                    await message.answer("➕ <b>1. Название предмета:</b>\nНапример: диван, холодильник", parse_mode="HTML")
                    await state.set_state(FillingStates.INVENTORY_ASKING_NAME)
                    return

        # === СТАНДАРТНАЯ ЛОГИКА ===
        next_valid_question_index = await check_condition_and_get_next_valid_question_index(
            questions, data["answers"], current_question_index
        )

        if next_valid_question_index >= len(questions):
            await save_draft_to_db(message.from_user.id, data)
            save_last_template_draft(message.from_user.id, data["doc_id"], data["answers"])
            answers_summary = ""
            for i, question in enumerate(questions, 1):
                answer = data["answers"].get(str(i - 1), "Не указано")
                answers_summary += f"{i}. {question['text']}\n   ➤ {answer}\n\n"
            review_text = FILLING_REVIEW_TEXT.format(answers_summary=answers_summary)
            buttons = [
                [InlineKeyboardButton(text="✅ Все верно", callback_data="confirm_document")],
                [InlineKeyboardButton(text="🔄 Изменить", callback_data="change_document")],
                [InlineKeyboardButton(text="🗑️ Отменить", callback_data="cancel_filling")]
            ]
            markup = InlineKeyboardMarkup(inline_keyboard=buttons)
            await message.answer(text=review_text, parse_mode="HTML", reply_markup=markup)
            await state.set_state(FillingStates.REVIEWING)
            return

        if next_valid_question_index != current_question_index:
            await state.update_data(current_question=next_valid_question_index)
            current_question_index = next_valid_question_index

        question = questions[current_question_index]
        if question.get("type") == "choice":
            markup = create_choice_keyboard(question["options"], str(current_question_index))
            question_text = FILLING_QUESTION_TEXT.format(
                question_number=current_question_index + 1,
                total_questions=len(questions),
                question_text=question['text'],
                description=question.get('hint', ''),
                example_section=""
            )
            await message.answer(text=question_text, parse_mode="HTML", reply_markup=markup)
            await state.set_state(FillingStates.WAITING_FOR_CHOICE)
            return

        if question.get("type") == "multi_select":
            selected = data["answers"].get(str(current_question_index), [])
            markup = create_multiselect_keyboard(selected, question["options"], str(current_question_index))
            await message.answer(
                text=question["text"] + f"\n\n{question.get('hint', '')}",
                reply_markup=markup
            )
            await state.set_state(FillingStates.SELECTING_MULTI)
            return

        example_section = ""
        if question.get("example"):
            example_section = f"Пример: <i>{question['example']}</i>"

        question_text = FILLING_QUESTION_TEXT.format(
            question_number=current_question_index + 1,
            total_questions=len(questions),
            question_text=question['text'],
            description=question.get('hint', ''),
            example_section=example_section
        )

        use_last_draft = data.get("use_last_draft", False)
        last_draft = data.get("last_draft", {})
        step_name = question.get("step")
        should_use_prefill = (
            use_last_draft
            and step_name is not None
            and step_name not in FIELDS_NEVER_FROM_DRAFT
            and str(current_question_index) not in data["answers"]
        )
        prefill_value = None
        if should_use_prefill:
            prefill_value = last_draft.get(str(current_question_index)) or last_draft.get(step_name)

        if prefill_value and prefill_value != "______":
            question_text += f"\n\n<b>Текущее значение:</b> <i>{prefill_value}</i>"
            markup = create_prefill_keyboard(str(current_question_index))
            await message.answer(text=question_text, parse_mode="HTML", reply_markup=markup)
            await state.set_state(FillingStates.WAITING_FOR_ANSWER)
        else:
            buttons = [
                [InlineKeyboardButton(text="⏭ Пропустить", callback_data=f"skip_{current_question_index}")],
                [InlineKeyboardButton(text="🗑️ Отменить", callback_data="cancel_filling")]
            ]
            markup = InlineKeyboardMarkup(inline_keyboard=buttons)
            await message.answer(text=question_text, parse_mode="HTML", reply_markup=markup)
            await state.set_state(FillingStates.WAITING_FOR_ANSWER)

    except Exception as e:
        logger.error(f"Ошибка при задавании вопроса из сообщения: {e}", exc_info=True)
        await message.answer("⚠️ Произошла ошибка при задавании вопроса")


async def finalize_inventory_filling_from_message(message: Message, state: FSMContext):
    data = await state.get_data()
    await save_draft_to_db(message.from_user.id, data)
    save_last_template_draft(message.from_user.id, data["doc_id"], data["answers"])
    answers_summary = "Опись имущества: не заполнена (выбрано «Нет»)"
    review_text = FILLING_REVIEW_TEXT.format(answers_summary=answers_summary)
    buttons = [
        [InlineKeyboardButton(text="✅ Все верно", callback_data="confirm_document")],
        [InlineKeyboardButton(text="🔄 Изменить", callback_data="change_document")],
        [InlineKeyboardButton(text="🗑️ Отменить", callback_data="cancel_filling")]
    ]
    markup = InlineKeyboardMarkup(inline_keyboard=buttons)
    await message.answer(text=review_text, parse_mode="HTML", reply_markup=markup)
    await state.set_state(FillingStates.REVIEWING)


async def show_review_message(callback: CallbackQuery, state: FSMContext):
    try:
        data = await state.get_data()
        doc_id = data.get("doc_id")
        answers = data["answers"]
        questions = data["questions"]

        if doc_id == "inventory_2025":
            answers_summary = ""
            for i in range(7):
                if i < len(questions):
                    q = questions[i]
                    ans = answers.get(str(i), "Не указано")
                    answers_summary += f"{i+1}. {q['text']}\n   ➤ {ans}\n\n"
            item_index = 1
            while f"item_{item_index}_name" in answers:
                name = answers.get(f"item_{item_index}_name", "")
                qty = answers.get(f"item_{item_index}_quantity", "")
                cond = answers.get(f"item_{item_index}_condition", "")
                answers_summary += f"{7+item_index}. Предмет {item_index}\n   ➤ Название: {name}\n   ➤ Кол-во: {qty}\n   ➤ Состояние: {cond}\n\n"
                item_index += 1
        else:
            answers_summary = ""
            for i, question in enumerate(questions, 1):
                answer = answers.get(str(i - 1), "Не указано")
                answers_summary += f"{i}. {question['text']}\n   ➤ {answer}\n\n"

        review_text = FILLING_REVIEW_TEXT.format(answers_summary=answers_summary)

        buttons = [
            [
                InlineKeyboardButton(text="✅ Все верно", callback_data="confirm_document"),
                InlineKeyboardButton(text="🔄 Изменить", callback_data="change_document")
            ],
            [InlineKeyboardButton(text="🗑️ Отменить", callback_data="cancel_filling")]
        ]
        markup = InlineKeyboardMarkup(inline_keyboard=buttons)

        await callback.message.edit_text(text=review_text, parse_mode="HTML", reply_markup=markup)
        await state.set_state(FillingStates.REVIEWING)

    except Exception as e:
        logger.error(f"Ошибка при отображении проверки данных: {e}", exc_info=True)
        await callback.answer("⚠️ Произошла ошибка при отображении проверки данных", show_alert=True)


@router.callback_query(F.data == "confirm_document")
async def confirm_document(callback: CallbackQuery, state: FSMContext):
    user_id = callback.from_user.id
    logger.info(f"Пользователь {user_id} подтвердил заполнение документа")

    try:
        data = await state.get_data()
        category = data["category"]
        doc_id = data["doc_id"]
        doc_info = data["doc_info"]
        fill_type = data["fill_type"]
        answers = data["answers"]

        save_last_template_draft(user_id, doc_id, answers)

        price = get_autogeneration_price() if fill_type == "autogen" else get_template_price()
        now = datetime.now()
        suffix = now.strftime("%d.%m/%H:%M")
        cart_item_id = f"{doc_info['template_name']}__{suffix}"

        add_to_cart(
            user_id=user_id,
            cart_item_id=cart_item_id,
            doc_id=doc_info['id'],
            doc_name=doc_info['name'],
            category=category,
            template_name=doc_info['template_name'],
            price=price,
            price_type=fill_type,
            filled_data=answers
        )

        delete_draft(user_id, doc_id)
        await state.clear()

        cart = get_user_cart(user_id)
        items_list = format_cart_items(cart['items'])
        item_count_str = format_item_count(cart['item_count'])
        cart_text = CART_TEXT.format(
            items_list=items_list,
            item_count=item_count_str,
            total_price=cart['total']
        )

        buttons = [
            [InlineKeyboardButton(text="✅ Оформить заказ", callback_data="checkout")],
            [InlineKeyboardButton(text="🛍️ Продолжить покупки", callback_data="catalog")]
        ]
        for i, item in enumerate(cart['items'], 1):
            buttons.append([
                InlineKeyboardButton(
                    text=f"🗑 Очистить {i}",
                    callback_data=f"remove_from_cart_{item['cart_item_id']}"
                )
            ])
        buttons.append([InlineKeyboardButton(text="🏠 Главное меню", callback_data="back_main")])

        markup = InlineKeyboardMarkup(inline_keyboard=buttons)
        await callback.message.edit_text(text=cart_text, parse_mode="HTML", reply_markup=markup)
        await callback.answer("✅ Документ добавлен в корзину!")

    except Exception as e:
        logger.error(f"Ошибка при подтверждении документа: {e}", exc_info=True)
        await callback.answer("⚠️ Произошла ошибка при добавлении документа в корзину", show_alert=True)


@router.callback_query(F.data == "change_document")
async def change_document(callback: CallbackQuery, state: FSMContext):
    await state.update_data(current_question=0)
    await ask_question_callback(callback, state)
    await callback.answer()


@router.callback_query(F.data == "cancel_filling")
async def cancel_filling(callback: CallbackQuery, state: FSMContext):
    await state.clear()
    await callback.message.edit_text(
        "❌ Заполнение документа отменено",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🛍️ Перейти в каталог", callback_data="catalog")],
            [InlineKeyboardButton(text="🏠 Главное меню", callback_data="back_main")]
        ])
    )
    await callback.answer()


@router.callback_query(F.data.startswith("skip_"))
async def skip_question(callback: CallbackQuery, state: FSMContext):
    try:
        question_index = int(callback.data.split("_")[1])
        data = await state.get_data()
        current_question = data.get("current_question", 0)

        if question_index != current_question:
            await callback.answer("❌ Устаревший запрос", show_alert=True)
            return

        answers = data.get("answers", {})
        answers[str(current_question)] = "______"
        await state.update_data(
            current_question=current_question + 1,
            answers=answers
        )

        await ask_question_callback(callback, state)
        await callback.answer()

    except Exception as e:
        logger.error(f"Ошибка при пропуске вопроса: {e}", exc_info=True)
        await callback.answer("⚠️ Не удалось пропустить вопрос", show_alert=True)


async def save_draft_to_db(user_id: int, data: dict):
    try:
        draft_id = save_draft(
            user_id=user_id,
            template_id=data["doc_id"],
            answers=data["answers"],
            category=data["category"],
            doc_info=data["doc_info"]
        )
        if draft_id:
            logger.info(f"✅ Черновик {draft_id} сохранен для пользователя {user_id}")
        else:
            logger.error(f"❌ Не удалось сохранить черновик для пользователя {user_id}")
    except Exception as e:
        logger.error(f"Ошибка при сохранении черновика: {e}", exc_info=True)