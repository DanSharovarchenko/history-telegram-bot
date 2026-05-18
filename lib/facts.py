"""
Выдача исторических фактов: по дате, категории, случайный, сравнение регионов, квиз.
"""

import datetime
import json
import random
from pathlib import Path

FACTS_PATH = Path(__file__).parent.parent / "data" / "facts.json"

RU_MONTHS = {
    1: "января", 2: "февраля", 3: "марта", 4: "апреля",
    5: "мая", 6: "июня", 7: "июля", 8: "августа",
    9: "сентября", 10: "октября", 11: "ноября", 12: "декабря",
}

# Все допустимые категории (для подсказки пользователю)
ALL_CATEGORIES = [
    "Россия", "Европа", "Америка", "Азия",
    "Война", "Политика", "Наука", "Космос",
    "Культура", "Образование", "Медицина", "Технологии", "Африка"
]


def _load_facts() -> dict:
    with open(FACTS_PATH, encoding="utf-8") as f:
        return json.load(f)


def _msk_today() -> datetime.date:
    msk = datetime.timezone(datetime.timedelta(hours=3))
    return datetime.datetime.now(msk).date()


def _format_date_ru(date: datetime.date) -> str:
    return f"{date.day} {RU_MONTHS[date.month]}"


def _date_key(date: datetime.date) -> str:
    return f"{date.month:02d}-{date.day:02d}"


def _format_fact(item: dict, date: datetime.date, prefix: str = "📜") -> str:
    year = item.get("year", "")
    text = item.get("text", "")
    link = item.get("link")
    out = f"{prefix} <b>{_format_date_ru(date)} в истории</b>\n\n"
    if year:
        out += f"<b>{year}</b> — {text}"
    else:
        out += text
    if link:
        out += f'\n\n<a href="{link}">Подробнее</a>'
    return out


def _key_to_date(key: str) -> datetime.date:
    """MM-DD → date (год текущий, для форматирования)."""
    m, d = key.split("-")
    return datetime.date(datetime.date.today().year, int(m), int(d))


# ── Основные функции ─────────────────────────────────────────────

async def get_today_fact(date: datetime.date | None = None) -> str:
    date = date or _msk_today()
    key = _date_key(date)
    facts = _load_facts()
    items = facts.get(key, [])
    if not items:
        return (
            f"📅 На <b>{_format_date_ru(date)}</b> в архиве пока ничего нет.\n\n"
            "Возвращайтесь завтра — или предложите факт автору бота."
        )
    idx = date.year % len(items)
    return _format_fact(items[idx], date)


async def get_fact_for_date(date_str: str) -> str | None:
    """Факт по ключу MM-DD. None если дата пуста."""
    try:
        m, d = map(int, date_str.split("-"))
        date = datetime.date(datetime.date.today().year, m, d)
    except (ValueError, IndexError):
        return None
    facts = _load_facts()
    items = facts.get(date_str, [])
    if not items:
        return None
    idx = date.year % len(items)
    return _format_fact(items[idx], date)


async def get_random_fact() -> str:
    facts = _load_facts()
    pool = []
    for key, items in facts.items():
        for item in items:
            pool.append((key, item))
    if not pool:
        return "Фактов пока нет."
    key, item = random.choice(pool)
    date = _key_to_date(key)
    return _format_fact(item, date, prefix="🎲")


# ── /category ────────────────────────────────────────────────────

async def get_today_fact_filtered(
    date: datetime.date | None = None,
    categories: list[str] | None = None,
) -> str:
    """Факт дня, отфильтрованный по категориям пользователя."""
    date = date or _msk_today()
    key = _date_key(date)
    facts = _load_facts()
    items = facts.get(key, [])

    if categories and "all" not in categories:
        items = [
            it for it in items
            if any(t in categories for t in it.get("tags", []))
        ]

    if not items:
        cats_str = ", ".join(categories or [])
        return (
            f"📅 На <b>{_format_date_ru(date)}</b> нет фактов "
            f"в категориях: {cats_str}.\n\n"
            "Попробуйте /today для факта без фильтра."
        )
    idx = date.year % len(items)
    return _format_fact(items[idx], date)


async def get_facts_by_category(category: str) -> list[tuple[str, dict]]:
    """Все факты с заданным тегом. Возвращает [(date_key, item), ...]."""
    facts = _load_facts()
    result = []
    for key, items in facts.items():
        for item in items:
            if category in item.get("tags", []):
                result.append((key, item))
    return result


# ── /compare ─────────────────────────────────────────────────────

async def get_compare(date: datetime.date | None = None) -> str:
    """Что происходило в этот день в разных регионах мира."""
    date = date or _msk_today()
    key = _date_key(date)
    facts = _load_facts()
    items = facts.get(key, [])

    if len(items) < 2:
        return (
            f"🌍 На <b>{_format_date_ru(date)}</b> в архиве недостаточно "
            "фактов из разных регионов для сравнения.\n\n"
            "Попробуйте другую дату: /compare MM-DD"
        )

    # Группируем по региону
    by_region: dict[str, list[dict]] = {}
    for item in items:
        region = item.get("region", "Мир")
        by_region.setdefault(region, []).append(item)

    region_emoji = {
        "Россия": "🇷🇺", "Европа": "🇪🇺", "Америка": "🌎",
        "Азия": "🌏", "Африка": "🌍", "Мир": "🌐",
    }

    out = f"🌍 <b>{_format_date_ru(date)}: мир в этот день</b>\n"
    for region, ritems in by_region.items():
        emoji = region_emoji.get(region, "📌")
        out += f"\n{emoji} <b>{region}</b>\n"
        for it in ritems:
            year = it.get("year", "")
            text = it.get("text", "")
            if year:
                out += f"  • <b>{year}</b> — {text}\n"
            else:
                out += f"  • {text}\n"
    return out


# ── /quiz ────────────────────────────────────────────────────────

async def get_quiz(date: datetime.date | None = None) -> dict | None:
    """
    Вернуть квиз-данные для факта дня.
    Возвращает dict {question, options, correct, fact_text} или None.
    """
    date = date or _msk_today()
    key = _date_key(date)
    facts = _load_facts()
    items = facts.get(key, [])

    # Собираем все факты с квизом на эту дату
    with_quiz = [it for it in items if it.get("quiz")]
    if not with_quiz:
        return None

    item = random.choice(with_quiz)
    quiz = item["quiz"]
    year = item.get("year", "")
    text = item.get("text", "")
    fact_line = f"<b>{year}</b> — {text}" if year else text

    return {
        "question": quiz["question"],
        "options": quiz["options"],
        "correct": quiz["correct"],
        "fact_text": fact_line,
        "date_str": _format_date_ru(date),
    }


async def get_random_quiz() -> dict | None:
    """Случайный квиз из любой даты."""
    facts = _load_facts()
    pool = []
    for key, items in facts.items():
        for item in items:
            if item.get("quiz"):
                pool.append((key, item))
    if not pool:
        return None
    key, item = random.choice(pool)
    date = _key_to_date(key)
    quiz = item["quiz"]
    year = item.get("year", "")
    text = item.get("text", "")
    fact_line = f"<b>{year}</b> — {text}" if year else text
    return {
        "question": quiz["question"],
        "options": quiz["options"],
        "correct": quiz["correct"],
        "fact_text": fact_line,
        "date_str": _format_date_ru(date),
    }
async def get_total_facts_count() -> int:
    """Возвращает общее количество фактов (включая все даты и множественные записи)."""
    facts = _load_facts()
    total = sum(len(items) for items in facts.values())
    return total
def get_random_fact_structured():
    """Возвращает случайный факт в виде словаря для JSON API (синхронная версия)."""
    facts = _load_facts()
    all_items = []
    for date_key, items in facts.items():
        for item in items:
            copy = item.copy()
            copy['date_key'] = date_key
            all_items.append(copy)
    if not all_items:
        return {"error": "Нет фактов"}
    chosen = random.choice(all_items)
    month, day = chosen['date_key'].split('-')
    # Используем текущий год для корректного создания date, но для форматирования важен только месяц и день
    date_obj = datetime.date(2000, int(month), int(day))
    date_str = _format_date_ru(date_obj)
    return {
        "text": chosen['text'],
        "year": chosen.get('year'),
        "link": chosen.get('link'),
        "date_str": date_str,
        "date_key": chosen['date_key']
    }
def get_fact_for_date_structured(date_str: str):
    """
    Принимает дату в формате YYYY-MM-DD или MM-DD.
    Возвращает структурированный словарь для JSON API или None.
    """
    # Преобразуем YYYY-MM-DD в MM-DD
    if len(date_str) == 10 and date_str[4] == '-':
        mmdd = date_str[5:7] + '-' + date_str[8:10]
    else:
        mmdd = date_str
    facts = _load_facts()
    items = facts.get(mmdd, [])
    if not items:
        return None
    # Берём первый факт (или можно ротировать по году, но для простоты первый)
    item = items[0]
    return {
        "text": item['text'],
        "year": item.get('year'),
        "link": item.get('link'),
        "date": mmdd
    }

def get_random_quiz_structured():
    """Возвращает случайный вопрос викторины (структурированный) или None."""
    facts = _load_facts()
    all_quizzes = []
    for date_key, items in facts.items():
        for item in items:
            if "quiz" in item:
                q = item["quiz"].copy()
                # Формируем дату для отображения
                month, day = date_key.split('-')
                date_obj = datetime.date(2000, int(month), int(day))
                q["date_str"] = _format_date_ru(date_obj)
                q["question_id"] = f"{date_key}_{item.get('year',0)}"
                all_quizzes.append(q)
    if not all_quizzes:
        return None
    chosen = random.choice(all_quizzes)
    return {
        "question": chosen["question"],
        "options": chosen["options"],
        "correct_index": chosen["correct"],
        "date_str": chosen["date_str"],
        "question_id": chosen["question_id"]
    }