import re
from datetime import datetime, timedelta
import logging

logger = logging.getLogger('doc_bot.validators')


def validate_email(email_str):
    """Проверяет email на корректность формата"""
    if not email_str or not isinstance(email_str, str):
        return False

    # Улучшенное регулярное выражение для email
    pattern = r'^[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+$'
    return re.match(pattern, email_str) is not None


def validate_phone(phone_str):
    if not phone_str or not isinstance(phone_str, str):
        return False

    # Удаляем все нецифровые символы
    digits = re.sub(r'\D', '', phone_str)

    # Проверяем длину
    if len(digits) < 10:
        return False

    # Проверяем на соответствие российскому формату
    if len(digits) == 10 and digits.startswith('9'):
        return True

    # Проверяем на наличие кода страны
    if len(digits) == 11 and (digits.startswith('7') or digits.startswith('8')):
        return True

    # Проверяем международный формат
    if len(digits) >= 10 and digits.startswith('49'):  # Германия
        return True
    if len(digits) >= 10 and digits.startswith('33'):  # Франция
        return True
    if len(digits) >= 10 and digits.startswith('39'):  # Италия
        return True
    if len(digits) >= 10 and digits.startswith('44'):  # Великобритания
        return True
    if len(digits) >= 10 and digits.startswith('1'):   # США/Канада
        return True

    return False


def validate_inn(inn_str):
    """Проверяет ИНН на корректность длины и контрольной суммы"""
    if not inn_str or not isinstance(inn_str, str) or not inn_str.isdigit():
        return False

    # Проверяем длину
    if len(inn_str) not in [10, 12]:
        return False

    # Проверка контрольной суммы для ИНН 10 цифр (юрлицо)
    if len(inn_str) == 10:
        coefficients = [2, 4, 10, 3, 5, 9, 4, 6, 8]
        checksum = sum(int(inn_str[i]) * coefficients[i] for i in range(9)) % 11 % 10
        return checksum == int(inn_str[9])

    # Проверка контрольных сумм для ИНН 12 цифр (физлицо)
    if len(inn_str) == 12:
        coefficients1 = [7, 2, 4, 10, 3, 5, 9, 4, 6, 8]
        coefficients2 = [3, 7, 2, 4, 10, 3, 5, 9, 4, 6, 8]

        checksum1 = sum(int(inn_str[i]) * coefficients1[i] for i in range(10)) % 11 % 10
        checksum2 = sum(int(inn_str[i]) * coefficients2[i] for i in range(11)) % 11 % 10

        return checksum1 == int(inn_str[10]) and checksum2 == int(inn_str[11])

    return False


def validate_ogrn(ogrn_str):
    """Проверяет ОГРН на корректность длины и контрольной суммы"""
    if not ogrn_str or not isinstance(ogrn_str, str) or not ogrn_str.isdigit():
        return False

    # Проверяем длину
    if len(ogrn_str) not in [13, 15]:
        return False

    # Проверка контрольной суммы для ОГРН 13 цифр (юрлицо)
    if len(ogrn_str) == 13:
        checksum = int(ogrn_str[:-1]) % 11 % 10
        return checksum == int(ogrn_str[-1])

    # Проверка контрольной суммы для ОГРН 15 цифр (ИП)
    if len(ogrn_str) == 15:
        checksum = int(ogrn_str[:-1]) % 13 % 10
        return checksum == int(ogrn_str[-1])

    return False


def validate_okved(okved_str):
    """Проверяет ОКВЭД на корректность формата"""
    if not okved_str or not isinstance(okved_str, str):
        return False

    # Проверяем формат ОКВЭД 2.4 (максимальная длина 7 символов, может содержать точки)
    pattern = r'^\d{1,2}(\.\d{1,2}){0,4}$'
    return re.match(pattern, okved_str) is not None


def validate_date_range(start_date, end_date):
    """Проверяет, что дата окончания не раньше даты начала"""
    try:
        # Если одна из дат пустая, возвращаем False
        if not start_date or not end_date:
            return False, "Обе даты должны быть указаны"

        # Пробуем разные форматы дат
        formats = ["%d.%m.%Y", "%Y-%m-%d", "%Y-%m-%d %H:%M:%S", "%d/%m/%Y"]
        start_dt = None
        end_dt = None

        for fmt in formats:
            try:
                if not start_dt:
                    start_dt = datetime.strptime(str(start_date), fmt)
                if not end_dt:
                    end_dt = datetime.strptime(str(end_date), fmt)
                if start_dt and end_dt:
                    break
            except (ValueError, TypeError):
                continue

        if not start_dt or not end_dt:
            return False, "Неверный формат даты"

        if start_dt > end_dt:
            return False, "Дата окончания не может быть раньше даты начала"

        # Проверяем, что дата не в прошлом (для дат начала)
        if start_dt < datetime.now():
            return False, "Дата начала не может быть в прошлом"

        return True, ""
    except Exception as e:
        logger.warning(f"Ошибка при валидации диапазона дат: {e}")
        return False, "Ошибка при проверке дат"

def validate_future_date(date_str):
    """Проверяет, что дата в будущем"""
    try:
        if not date_str:
            return False, "Дата не указана"

        # Пробуем разные форматы дат
        formats = ["%d.%m.%Y", "%Y-%m-%d", "%Y-%m-%d %H:%M:%S", "%d/%m/%Y"]
        date_dt = None

        for fmt in formats:
            try:
                date_dt = datetime.strptime(str(date_str), fmt)
                break
            except (ValueError, TypeError):
                continue

        if not date_dt:
            return False, "Неверный формат даты"

        if date_dt < datetime.now():
            return False, "Дата не может быть в прошлом"

        return True, ""
    except Exception as e:
        logger.warning(f"Ошибка при валидации даты: {e}")
        return False, "Ошибка при проверке даты"


def get_date_from_step(all_questions, answers, step_path):
    """Получает дату из ответов по пути step[индекс]"""
    try:
        # Проверяем, что входные данные не пустые
        if not all_questions or not answers:
            return None

        if '[' in step_path and ']' in step_path:
            # Используем регулярное выражение для безопасного извлечения шага и индекса
            match = re.match(r'([a-zA-Z0-9_]+)\[(\d+)\]', step_path)
            if match:
                step = match.group(1)
                index = int(match.group(2))

                # Находим нужный индекс в ответах
                count = 0
                for i, q in enumerate(all_questions):
                    if q.get("step") == step:
                        if count == index and i < len(answers):
                            return answers[i]
                        count += 1
        return None
    except Exception as e:
        logger.warning(f"Ошибка при получении даты из шага: {e}")
        return None


def validate_field(question: dict, value: str) -> (bool, str):
    """Валидирует поле формы на основе его типа и параметров"""
    try:
        field_type = question.get("type", "text")
        step = question.get("step", "")
        label = question.get("label", "Это поле")

        # Проверяем, что value является строкой
        if value is None:
            value = ""
        elif not isinstance(value, str):
            value = str(value)

        # Проверка пустых значений для обязательных полей
        if question.get("required", False) and not value.strip():
            return False, f"{label} обязательно для заполнения"

        # Специфичные проверки
        if field_type == "number":
            # Разрешаем отрицательные числа и десятичные дроби
            if not re.match(r'^-?\d+(\.\d+)?$', value):
                return False, f"{label} должен быть числом"

        elif field_type == "email":
            if not validate_email(value):
                return False, f"Неверный формат {label.lower()}"

        elif field_type == "phone":
            if not validate_phone(value):
                return False, f"Неверный формат {label.lower()}"

        elif field_type == "date":
            try:
                datetime.strptime(value, "%d.%m.%Y")
            except ValueError:
                return False, f"Неверный формат даты для {label.lower()}. Используйте ДД.ММ.ГГГГ"

        elif field_type == "inn" or "inn" in step.lower():
            if not validate_inn(value):
                return False, f"Неверный ИНН. {label} должен содержать 10 или 12 цифр"

        elif field_type == "ogrn" or "ogrn" in step.lower():
            if not validate_ogrn(value):
                return False, f"Неверный ОГРН. {label} должен содержать 13 или 15 цифр"

        elif field_type == "okved" or "okved" in step.lower():
            if not validate_okved(value):
                return False, f"Неверный формат ОКВЭД для {label.lower()}"

        return True, ""
    except Exception as e:
        logger.error(f"Ошибка при валидации поля: {e}", exc_info=True)
        return False, "Произошла ошибка при проверке этого поля"