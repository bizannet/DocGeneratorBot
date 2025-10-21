def amount_to_words(amount):
    rub = int(amount)
    kop = int(round((amount - rub) * 100))
    if kop == 100:
        rub += 1
        kop = 0
    amount_formatted = "{:,.0f}".format(rub).replace(",", " ")
    amount_formatted += f" руб. {kop:02d} коп."

    # Словари для преобразования чисел в слова
    units = ["", "один", "два", "три", "четыре", "пять", "шесть", "семь", "восемь", "девять"]
    teens = ["десять", "одиннадцать", "двенадцать", "тринадцать", "четырнадцать", "пятнадцать",
             "шестнадцать", "семнадцать", "восемнадцать", "девятнадцать"]
    tens = ["", "", "двадцать", "тридцать", "сорок", "пятьдесят", "шестьдесят", "семьдесят", "восемьдесят", "девяносто"]
    hundreds = ["", "сто", "двести", "триста", "четыреста", "пятьсот", "шестьсот", "семьсот", "восемьсот", "девятьсот"]

    # Специальные формы для тысяч
    units_thousands = ["", "одна", "две", "три", "четыре", "пять", "шесть", "семь", "восемь", "девять"]

    # Преобразуем рубли в строку прописью
    def convert_number(n, for_thousands=False):
        if n == 0:
            return ""

        words = []

        # Миллионы
        if n >= 1000000:
            millions = n // 1000000
            words.append(convert_number(millions, False))
            # Склонение для миллионов
            last_digit = millions % 10
            last_two_digits = millions % 100
            if 5 <= last_two_digits <= 20 or last_digit == 0 or last_digit >= 5:
                words.append("миллионов")
            elif last_digit == 1:
                words.append("миллион")
            else:
                words.append("миллиона")
            n %= 1000000

        # Тысячи
        if n >= 1000:
            thousands_value = n // 1000

            # Преобразуем тысячи в слова
            if thousands_value >= 100:
                words.append(hundreds[thousands_value // 100])
                thousands_value %= 100
            if thousands_value >= 20:
                words.append(tens[thousands_value // 10])
                thousands_value %= 10
            if 10 <= thousands_value < 20:
                words.append(teens[thousands_value - 10])
            elif thousands_value > 0:
                words.append(units_thousands[thousands_value])

            n %= 1000
            last_digit = (n // 1000) % 10
            last_two_digits = (n // 1000) % 100
            if 5 <= last_two_digits <= 20 or last_digit == 0 or last_digit >= 5:
                words.append("тысяч")
            elif last_digit == 1:
                words.append("тысяча")
            else:
                words.append("тысячи")

        # Сотни
        if n >= 100:
            words.append(hundreds[n // 100])
            n %= 100

        # Десятки и единицы
        if n >= 20:
            words.append(tens[n // 10])
            n %= 10
        if 10 <= n < 20:
            words.append(teens[n - 10])
            n = 0
        if 0 < n < 10:
            words.append(units[n] if not for_thousands else units_thousands[n])

        return " ".join(words).strip()

    # Формы слов для рублей
    rub_word = "рублей"
    last_digit = rub % 10
    last_two_digits = rub % 100

    if 5 <= last_two_digits <= 20:
        rub_word = "рублей"
    elif last_digit == 1:
        rub_word = "рубль"
    elif 2 <= last_digit <= 4:
        rub_word = "рубля"

    # Формы слов для копеек
    kop_word = "копеек"
    last_digit_kop = kop % 10
    last_two_digits_kop = kop % 100

    if 5 <= last_two_digits_kop <= 20:
        kop_word = "копеек"
    elif last_digit_kop == 1:
        kop_word = "копейка"
    elif 2 <= last_digit_kop <= 4:
        kop_word = "копейки"

    # Обрабатываем случай, когда рубли = 0
    if rub == 0 and kop > 0:
        rub_words = ""
    else:
        rub_words = convert_number(rub, False)
        if not rub_words:
            rub_words = "ноль"

    # Формируем итоговую строку
    result = f"{amount_formatted}"

    # Добавляем пропись только если есть рубли или копейки
    if rub > 0 or kop > 0:
        words_parts = []
        if rub > 0:
            words_parts.append(f"{rub_words} {rub_word}")
        if kop > 0:
            kop_words = convert_number(kop, False)
            if not kop_words:
                kop_words = "ноль"
            words_parts.append(f"{kop_words} {kop_word}")

        result += f" ({' '.join(words_parts)})"

    return result