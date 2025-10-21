# import logging
# from aiogram import Router, F
# from aiogram.types import CallbackQuery, Message, InlineKeyboardButton, InlineKeyboardMarkup
# from aiogram.fsm.context import FSMContext
# from aiogram.fsm.state import State, StatesGroup
# from config import config
# from database.templates import get_templates_by_category, get_template_by_id
# from database.orders import get_user_orders
# from texts.messages import (
#     RECOMMENDATIONS_TEXT,
#     NO_RECOMMENDATIONS_TEXT,
#     DOCUMENT_DESCRIPTION_TEXT,
#     CART_TEXT
# )
# from database.cart import add_to_cart, get_user_cart, clear_cart
# from services.validators import validate_field
#
# logger = logging.getLogger('doc_bot.recommendation')
# router = Router(name="recommendation_router")
#
#
# class RecommendationStates(StatesGroup):
#     ASKING_QUESTIONS = State()
#     SHOWING_RECOMMENDATIONS = State()
#
#
# # Вопросы для рекомендаций
# RECOMMENDATION_QUESTIONS = [
#     {
#         "id": "business_type",
#         "question": "Какой у вас тип бизнеса?",
#         "options": [
#             {"text": "Интернет-магазин", "value": "ecommerce", "weight": 1.0},
#             {"text": "Услуги (юридические, бухгалтерские и др.)", "value": "services", "weight": 0.8},
#             {"text": "Недвижимость", "value": "realestate", "weight": 0.7},
#             {"text": "Грузоперевозки", "value": "logistics", "weight": 0.6},
#             {"text": "Другое", "value": "other", "weight": 0.3}
#         ]
#     },
#     {
#         "id": "business_size",
#         "question": "Какой масштаб вашего бизнеса?",
#         "options": [
#             {"text": "Физическое лицо", "value": "individual", "weight": 0.5},
#             {"text": "ИП", "value": "ip", "weight": 0.7},
#             {"text": "ООО", "value": "ooo", "weight": 1.0},
#             {"text": "Крупная компания", "value": "corporation", "weight": 1.2}
#         ]
#     },
#     {
#         "id": "website",
#         "question": "Есть ли у вас сайт или онлайн-присутствие?",
#         "options": [
#             {"text": "Да, интернет-магазин", "value": "ecommerce_site", "weight": 1.0},
#             {"text": "Да, информационный сайт", "value": "info_site", "weight": 0.8},
#             {"text": "Нет", "value": "no_website", "weight": 0.1}
#         ]
#     },
#     {
#         "id": "data_processing",
#         "question": "Обрабатываете ли вы персональные данные?",
#         "options": [
#             {"text": "Да, активно", "value": "active", "weight": 1.0},
#             {"text": "Да, но немного", "value": "limited", "weight": 0.7},
#             {"text": "Нет", "value": "none", "weight": 0.1}
#         ]
#     }
# ]
#
# # Правила рекомендаций
# RECOMMENDATION_RULES = [
#     {
#         "condition": lambda answers: answers.get("business_type") == "ecommerce" or
#                                      answers.get("website") in ["ecommerce_site", "info_site"] or
#                                      answers.get("data_processing") in ["active", "limited"],
#         "templates": [
#             {"category": "website", "templates": ["privacy_policy_2025", "consent_2025", "cookie_policy_2025"],
#              "priority": 1.0}
#         ]
#     },
#     {
#         "condition": lambda answers: answers.get("business_type") == "services",
#         "templates": [
#             {"category": "business", "templates": ["service_contract_2025", "work_contract_2025", "act_2025"],
#              "priority": 0.9}
#         ]
#     },
#     {
#         "condition": lambda answers: answers.get("business_type") == "realestate",
#         "templates": [
#             {"category": "realestate",
#              "templates": ["rental_contract_2025", "acceptance_transfer_2025", "inventory_2025"], "priority": 0.9}
#         ]
#     },
#     {
#         "condition": lambda answers: answers.get("business_type") == "logistics",
#         "templates": [
#             {"category": "logistics",
#              "templates": ["cargo_transport_2025", "cargo_transport_waybill_2025", "cargo_acceptance_2025"],
#              "priority": 0.9}
#         ]
#     },
#     {
#         "condition": lambda answers: answers.get("business_size") in ["ip", "ooo"],
#         "templates": [
#             {"category": "business", "templates": ["public_offer_2025"], "priority": 0.7}
#         ]
#     },
#     {
#         "condition": lambda answers: answers.get("business_size") == "ooo",
#         "templates": [
#             {"category": "financial", "templates": ["work_acceptance_2025", "work_estimate_2025"], "priority": 0.6}
#         ]
#     },
#     {
#         "condition": lambda answers: answers.get("data_processing") == "active",
#         "templates": [
#             {"category": "website", "templates": ["notification_2025"], "priority": 0.8}
#         ]
#     }
# ]
#
# # Связи между документами (какие документы часто покупают вместе)
# DOCUMENT_RELATIONSHIPS = {
#     "service_contract_2025": ["work_contract_2025", "act_2025", "public_offer_2025"],
#     "work_contract_2025": ["service_contract_2025", "act_2025"],
#     "act_2025": ["service_contract_2025", "work_contract_2025"],
#     "public_offer_2025": ["service_contract_2025"],
#     "privacy_policy_2025": ["consent_2025", "cookie_policy_2025", "notification_2025"],
#     "consent_2025": ["privacy_policy_2025", "cookie_policy_2025"],
#     "cookie_policy_2025": ["privacy_policy_2025", "consent_2025"],
#     "notification_2025": ["privacy_policy_2025"],
#     "rental_contract_2025": ["acceptance_transfer_2025", "inventory_2025"],
#     "acceptance_transfer_2025": ["rental_contract_2025", "inventory_2025"],
#     "inventory_2025": ["rental_contract_2025", "acceptance_transfer_2025"],
#     "cargo_transport_2025": ["cargo_transport_waybill_2025", "cargo_acceptance_2025"],
#     "cargo_transport_waybill_2025": ["cargo_transport_2025", "cargo_acceptance_2025"],
#     "cargo_acceptance_2025": ["cargo_transport_2025", "cargo_transport_waybill_2025"],
#     "work_acceptance_2025": ["work_estimate_2025", "work_technical_task_2025"],
#     "work_estimate_2025": ["work_acceptance_2025", "work_technical_task_2025"]
# }
#
#
# @router.callback_query(F.data == "recommendations")
# async def start_recommendations(callback: CallbackQuery, state: FSMContext):
#     """Начинает процесс рекомендаций"""
#     user_id = callback.from_user.id
#     logger.info(f"Пользователь {user_id} начал процесс рекомендаций")
#
#     try:
#         # Инициализируем данные в состоянии
#         await state.update_data(
#             answers={},
#             current_question=0
#         )
#
#         # Устанавливаем состояние
#         await state.set_state(RecommendationStates.ASKING_QUESTIONS)
#
#         # Задаем первый вопрос
#         await ask_question(callback, state)
#
#     except Exception as e:
#         logger.error(f"Ошибка при начале рекомендаций: {e}", exc_info=True)
#         await callback.answer("⚠️ Произошла ошибка при запуске рекомендаций", show_alert=True)
#         await callback.answer()
#
#
# async def ask_question(callback: CallbackQuery, state: FSMContext):
#     """Задает следующий вопрос пользователю"""
#     try:
#         data = await state.get_data()
#         current_question = data.get('current_question', 0)
#
#         if current_question >= len(RECOMMENDATION_QUESTIONS):
#             await generate_recommendations(callback, state)
#             return
#
#         # Получаем текущий вопрос
#         question = RECOMMENDATION_QUESTIONS[current_question]
#
#         # Формируем текст вопроса
#         question_text = (
#             f"🔍 <b>Подбор документов</b>\\n"
#             f"Вопрос {current_question + 1}/{len(RECOMMENDATION_QUESTIONS)}:\n\n"
#             f"<b>{question['question']}</b>"
#         )
#
#         # Создаем клавиатуру с вариантами ответов
#         buttons = []
#         for option in question['options']:
#             buttons.append([
#                 InlineKeyboardButton(
#                     text=option['text'],
#                     callback_data=f"rec_{question['id']}_{option['value']}"
#                 )
#             ])
#
#         # Добавляем кнопку "Назад" если это не первый вопрос
#         if current_question > 0:
#             buttons.append([
#                 InlineKeyboardButton(
#                     text="⬅️ Назад",
#                     callback_data="rec_prev"
#                 )
#             ])
#
#         # Добавляем кнопку "Пропустить"
#         buttons.append([
#             InlineKeyboardButton(
#                 text="➡️ Пропустить",
#                 callback_data="rec_skip"
#             )
#         ])
#
#         # Добавляем кнопку "Отмена"
#         buttons.append([
#             InlineKeyboardButton(
#                 text="❌ Отмена",
#                 callback_data="rec_cancel"
#             )
#         ])
#
#         markup = InlineKeyboardMarkup(inline_keyboard=buttons)
#
#         await callback.message.edit_text(
#             text=question_text,
#             parse_mode="HTML",
#             reply_markup=markup
#         )
#         await callback.answer()
#
#     except Exception as e:
#         logger.error(f"Ошибка при задавании вопроса: {e}", exc_info=True)
#         await callback.answer("⚠️ Произошла ошибка при загрузке вопроса", show_alert=True)
#         await callback.answer()
#
#
# @router.callback_query(F.data.startswith("rec_"))
# async def process_answer(callback: CallbackQuery, state: FSMContext):
#     """Обрабатывает ответ пользователя на вопрос"""
#     user_id = callback.from_user.id
#     logger.info(f"Пользователь {user_id} дал ответ на вопрос: {callback.data}")
#
#     try:
#         data = await state.get_data()
#         current_question = data.get('current_question', 0)
#         answers = data.get('answers', {})
#
#         # Обрабатываем различные типы callback-данных
#         if callback.data == "rec_prev":
#             # Переход к предыдущему вопросу
#             if current_question > 0:
#                 await state.update_data(current_question=current_question - 1)
#                 await ask_question(callback, state)
#             return
#
#         elif callback.data == "rec_skip":
#             # Пропуск вопроса
#             await state.update_data(current_question=current_question + 1)
#             await ask_question(callback, state)
#             return
#
#         elif callback.data == "rec_cancel":
#             # Отмена рекомендаций
#             await state.clear()
#
#             await callback.message.edit_text(
#                 "❌ Процесс рекомендаций отменен.",
#                 reply_markup=InlineKeyboardMarkup(inline_keyboard=[
#                     [
#                         InlineKeyboardButton(
#                             text="🏠 Главное меню",
#                             callback_data="back_main"
#                         )
#                     ]
#                 ])
#             )
#             await callback.answer()
#             return
#
#         else:
#             # Обработка выбора варианта
#             parts = callback.data.split("_")
#             if len(parts) < 3:
#                 await callback.answer("⚠️ Неверный формат ответа", show_alert=True)
#                 await callback.answer()
#                 return
#
#             question_id = parts[1]
#             option_value = parts[2]
#
#             # Сохраняем ответ
#             answers[question_id] = option_value
#             await state.update_data(
#                 answers=answers,
#                 current_question=current_question + 1
#             )
#
#             # Задаем следующий вопрос
#             await ask_question(callback, state)
#
#     except Exception as e:
#         logger.error(f"Ошибка при обработке ответа: {e}", exc_info=True)
#         await callback.answer("⚠️ Произошла ошибка при обработке ответа", show_alert=True)
#         await callback.answer()
#
#
# async def generate_recommendations(callback: CallbackQuery, state: FSMContext):
#     """Генерирует рекомендации на основе ответов пользователя и истории заказов"""
#     try:
#         user_id = callback.from_user.id
#         data = await state.get_data()
#         answers = data.get('answers', {})
#
#         # Собираем рекомендации на основе правил
#         recommendations = []
#         template_ids = set()  # Для отслеживания уникальных шаблонов
#
#         # 1. Рекомендации на основе ответов на вопросы
#         for rule in RECOMMENDATION_RULES:
#             if rule["condition"](answers):
#                 for template_group in rule["templates"]:
#                     category = template_group["category"]
#                     base_priority = template_group["priority"]
#
#                     for template_name in template_group["templates"]:
#                         # Получаем шаблон по имени
#                         templates = get_templates_by_category(category)
#                         for template in templates:
#                             if template["template_name"] == template_name and template["id"] not in template_ids:
#                                 # Базовый приоритет из правил
#                                 priority = base_priority
#
#                                 # 2. Увеличиваем приоритет на основе прошлых заказов
#                                 past_orders = get_user_orders(user_id)
#                                 if past_orders:
#                                     for order in past_orders:
#                                         for item in order["items"]:
#                                             # Если пользователь уже покупал похожий документ
#                                             if item["category"] == category:
#                                                 priority += 0.2
#
#                                             # Проверяем связи между документами
#                                             if item["template_name"] in DOCUMENT_RELATIONSHIPS:
#                                                 related_templates = DOCUMENT_RELATIONSHIPS[item["template_name"]]
#                                                 if template_name in related_templates:
#                                                     priority += 0.3
#
#                                 recommendations.append({
#                                     "id": template["id"],
#                                     "name": template["name"],
#                                     "price": template["price"],
#                                     "category": category,
#                                     "priority": priority,
#                                     "source": "question_based"
#                                 })
#                                 template_ids.add(template["id"])
#                                 break
#
#         # 3. Рекомендации на основе прошлых заказов (если не было ответов на вопросы)
#         if not recommendations and answers:
#             past_orders = get_user_orders(user_id)
#             if past_orders:
#                 for order in past_orders:
#                     for item in order["items"]:
#                         if item["template_name"] in DOCUMENT_RELATIONSHIPS:
#                             related_templates = DOCUMENT_RELATIONSHIPS[item["template_name"]]
#
#                             for related_template in related_templates:
#                                 # Находим категорию по имени шаблона
#                                 category = None
#                                 for cat, templates_list in get_templates_by_category("all").items():
#                                     for t in templates_list:
#                                         if t["template_name"] == related_template:
#                                             category = cat
#                                             break
#                                     if category:
#                                         break
#
#                                 if category:
#                                     templates = get_templates_by_category(category)
#                                     for template in templates:
#                                         if template["template_name"] == related_template and template[
#                                             "id"] not in template_ids:
#                                             # Проверяем, не был ли этот документ уже в рекомендациях
#                                             if not any(r["id"] == template["id"] for r in recommendations):
#                                                 recommendations.append({
#                                                     "id": template["id"],
#                                                     "name": template["name"],
#                                                     "price": template["price"],
#                                                     "category": category,
#                                                     "priority": 0.7,
#                                                     # Приоритет для рекомендаций на основе прошлых заказов
#                                                     "source": "past_orders"
#                                                 })
#                                                 template_ids.add(template["id"])
#
#         # Сортируем рекомендации по приоритету
#         recommendations.sort(key=lambda x: x["priority"], reverse=True)
#
#         # Сохраняем рекомендации в состоянии
#         await state.update_data(recommendations=recommendations)
#
#         # Показываем рекомендации
#         await show_recommendations(callback, state)
#
#     except Exception as e:
#         logger.error(f"Ошибка при генерации рекомендаций: {e}", exc_info=True)
#         await callback.answer("⚠️ Произошла ошибка при генерации рекомендаций", show_alert=True)
#         await callback.answer()
#
#
# async def show_recommendations(callback: CallbackQuery, state: FSMContext):
#     """Показывает рекомендованные документы"""
#     try:
#         data = await state.get_data()
#         recommendations = data.get('recommendations', [])
#
#         if not recommendations:
#             await callback.message.edit_text(
#                 NO_RECOMMENDATIONS_TEXT,
#                 parse_mode="HTML",
#                 reply_markup=InlineKeyboardMarkup(inline_keyboard=[
#                     [
#                         InlineKeyboardButton(
#                             text="🔄 Попробовать еще раз",
#                             callback_data="recommendations"
#                         )
#                     ],
#                     [
#                         InlineKeyboardButton(
#                             text="🛍️ Перейти в каталог",
#                             callback_data="catalog"
#                         )
#                     ],
#                     [
#                         InlineKeyboardButton(
#                             text="🏠 Главное меню",
#                             callback_data="back_main"
#                         )
#                     ]
#                 ])
#             )
#             await callback.answer()
#             return
#
#         # Формируем список рекомендованных документов
#         documents_list = ""
#         for i, doc in enumerate(recommendations, 1):
#             documents_list += f"{i}. {doc['name']} — {doc['price']} ₽\n"
#
#         # Формируем текст
#         recommendations_text = RECOMMENDATIONS_TEXT.format(
#             documents_list=documents_list
#         )
#
#         # Добавляем информацию об источнике рекомендаций
#         if any(doc["source"] == "past_orders" for doc in recommendations):
#             recommendations_text += (
#                 "\n\n<i>Подсказка: Некоторые рекомендации основаны на ваших прошлых заказах. "
#                 "Мы подобрали документы, которые часто покупают вместе с теми, что вы уже приобрели.</i>"
#             )
#
#         # Создаем клавиатуру
#         buttons = []
#
#         # Добавляем кнопки для каждого документа
#         for i, doc in enumerate(recommendations, 1):
#             buttons.append([
#                 InlineKeyboardButton(
#                     text=f"📄 {doc['name']}",
#                     callback_data=f"rec_doc_{doc['id']}"
#                 )
#             ])
#
#         # Добавляем общие кнопки
#         buttons.append([
#             InlineKeyboardButton(
#                 text="✅ Добавить все в корзину",
#                 callback_data="rec_add_all"
#             )
#         ])
#         buttons.append([
#             InlineKeyboardButton(
#                 text="🔄 Начать заново",
#                 callback_data="recommendations"
#             )
#         ])
#         buttons.append([
#             InlineKeyboardButton(
#                 text="🏠 Главное меню",
#                 callback_data="back_main"
#             )
#         ])
#
#         markup = InlineKeyboardMarkup(inline_keyboard=buttons)
#
#         await callback.message.edit_text(
#             text=recommendations_text,
#             parse_mode="HTML",
#             reply_markup=markup
#         )
#         await callback.answer()
#
#     except Exception as e:
#         logger.error(f"Ошибка при показе рекомендаций: {e}", exc_info=True)
#         await callback.answer("⚠️ Произошла ошибка при отображении рекомендаций", show_alert=True)
#         await callback.answer()
#
#
# @router.callback_query(F.data.startswith("rec_doc_"))
# async def show_recommendation_document(callback: CallbackQuery, state: FSMContext):
#     """Показывает детали рекомендованного документа"""
#     try:
#         doc_id = int(callback.data.split("_")[2])
#         data = await state.get_data()
#         recommendations = data.get('recommendations', [])
#
#         # Находим документ в рекомендациях
#         doc = None
#         for rec in recommendations:
#             if rec['id'] == doc_id:
#                 doc = rec
#                 break
#
#         if not doc:
#             await callback.answer("⚠️ Документ не найден", show_alert=True)
#             await callback.answer()
#             return
#
#         # Формируем текст с описанием документа
#         document_text = DOCUMENT_DESCRIPTION_TEXT.format(
#             doc_name=doc['name'],
#             description="Этот документ рекомендован специально для вашего бизнеса.",
#             price=doc['price']
#         )
#
#         # Добавляем информацию о том, почему рекомендован документ
#         if doc.get("source") == "past_orders":
#             document_text += (
#                 "\n\n<i>Этот документ часто покупают вместе с теми, что вы уже приобрели ранее.</i>"
#             )
#
#         # Создаем клавиатуру
#         markup = InlineKeyboardMarkup(inline_keyboard=[
#             [
#                 InlineKeyboardButton(
#                     text="📝 Начать заполнение",
#                     callback_data=f"fill_{doc['id']}"
#                 )
#             ],
#             [
#                 InlineKeyboardButton(
#                     text="➕ Добавить в корзину",
#                     callback_data=f"rec_add_{doc['id']}"
#                 )
#             ],
#             [
#                 InlineKeyboardButton(
#                     text="⬅️ Назад к рекомендациям",
#                     callback_data="show_recommendations"
#                 )
#             ]
#         ])
#
#         await callback.message.edit_text(
#             text=document_text,
#             parse_mode="HTML",
#             reply_markup=markup
#         )
#         await callback.answer()
#
#     except Exception as e:
#         logger.error(f"Ошибка при показе рекомендованного документа: {e}", exc_info=True)
#         await callback.answer("⚠️ Произошла ошибка", show_alert=True)
#         await callback.answer()
#
#
# @router.callback_query(F.data == "show_recommendations")
# async def back_to_recommendations(callback: CallbackQuery, state: FSMContext):
#     """Возвращается к списку рекомендаций"""
#     await show_recommendations(callback, state)
#
#
# @router.callback_query(F.data.startswith("rec_add_"))
# async def add_to_cart_handler(callback: CallbackQuery, state: FSMContext):
#     """Добавляет документ в корзину"""
#     try:
#         if callback.data == "rec_add_all":
#             # Добавляем все рекомендованные документы
#             data = await state.get_data()
#             recommendations = data.get('recommendations', [])
#
#             if not recommendations:
#                 await callback.answer("⚠️ Нет рекомендованных документов", show_alert=True)
#                 await callback.answer()
#                 return
#
#             # Добавляем все документы в корзину
#             for doc in recommendations:
#                 add_to_cart(callback.from_user.id, doc['id'])
#
#             await callback.answer(f"✅ {len(recommendations)} документов добавлено в корзину!", show_alert=True)
#         else:
#             # Добавляем один документ
#             doc_id = int(callback.data.split("_")[2])
#             add_to_cart(callback.from_user.id, doc_id)
#
#             await callback.answer("✅ Документ добавлен в корзину!", show_alert=True)
#
#         # Показываем обновленную корзину
#         cart = get_user_cart(callback.from_user.id)
#         total_price = sum(item['price'] for item in cart['items'])
#
#         cart_text = CART_TEXT.format(
#             item_count=cart['item_count'],
#             total_price=total_price
#         )
#
#         # Создаем клавиатуру
#         buttons = [
#             [
#                 InlineKeyboardButton(
#                     text="💳 Оформить заказ",
#                     callback_data="checkout"
#                 )
#             ],
#             [
#                 InlineKeyboardButton(
#                     text="🛍️ Продолжить покупки",
#                     callback_data="catalog"
#                 )
#             ],
#             [
#                 InlineKeyboardButton(
#                     text="🏠 Главное меню",
#                     callback_data="back_main"
#                 )
#             ]
#         ]
#
#         markup = InlineKeyboardMarkup(inline_keyboard=buttons)
#
#         await callback.message.edit_text(
#             text=cart_text,
#             parse_mode="HTML",
#             reply_markup=markup
#         )
#         await callback.answer()
#
#     except Exception as e:
#         logger.error(f"Ошибка при добавлении в корзину: {e}", exc_info=True)
#         await callback.answer("⚠️ Произошла ошибка при добавлении в корзину", show_alert=True)
#         await callback.answer()