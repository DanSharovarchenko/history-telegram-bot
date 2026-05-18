"""
Хранение подписчиков и их настроек в Upstash Redis (HTTP REST API).
Добавлены функции для глобальной статистики.
"""

import os
import json
import random
from datetime import date

import httpx

from lib.facts import _format_date_ru, _load_facts

UPSTASH_URL = os.environ["UPSTASH_REDIS_REST_URL"].rstrip("/")
UPSTASH_TOKEN = os.environ["UPSTASH_REDIS_REST_TOKEN"]

DEFAULT_HOUR = 9  # МСК (не используется, но оставлено)

# ── Redis transport ──────────────────────────────────────────────

async def _redis(*command) -> object:
    headers = {"Authorization": f"Bearer {UPSTASH_TOKEN}"}
    payload = [str(x) for x in command]
    async with httpx.AsyncClient(timeout=10) as client:
        r = await client.post(UPSTASH_URL, headers=headers, json=payload)
        r.raise_for_status()
        return r.json().get("result")


async def _pipeline(commands: list[list]) -> list:
    headers = {"Authorization": f"Bearer {UPSTASH_TOKEN}"}
    payload = [[str(x) for x in cmd] for cmd in commands]
    async with httpx.AsyncClient(timeout=10) as client:
        r = await client.post(
            f"{UPSTASH_URL}/pipeline", headers=headers, json=payload,
        )
        r.raise_for_status()
        return [item.get("result") for item in r.json()]


def _hour_key(hour: int) -> str:
    return f"history_bot:hour:{hour:02d}"


def _cats_key(chat_id: int) -> str:
    return f"history_bot:cats:{chat_id}"


def _quiz_key(chat_id: int) -> str:
    return f"history_bot:quiz:{chat_id}"


# ── Подписка / отписка ──────────────────────────────────────────

async def add_subscriber(chat_id: int, hour: int = DEFAULT_HOUR) -> None:
    await _pipeline([
        ["SADD", _hour_key(hour), chat_id],
        ["SET", _cats_key(chat_id), "all"],
    ])


async def remove_subscriber(chat_id: int) -> None:
    cmds = [["SREM", _hour_key(h), chat_id] for h in range(24)]
    cmds.append(["DEL", _cats_key(chat_id)])
    cmds.append(["DEL", _quiz_key(chat_id)])
    await _pipeline(cmds)


async def get_subscribers_for_hour(hour: int) -> list[int]:
    result = await _redis("SMEMBERS", _hour_key(hour))
    return [int(x) for x in (result or [])]


async def count_subscribers() -> int:
    cmds = [["SCARD", _hour_key(h)] for h in range(24)]
    results = await _pipeline(cmds)
    return sum(int(r or 0) for r in results)


# ── Время рассылки ──────────────────────────────────────────────

async def get_subscriber_hour(chat_id: int) -> int | None:
    cmds = [["SISMEMBER", _hour_key(h), chat_id] for h in range(24)]
    results = await _pipeline(cmds)
    for h, r in enumerate(results):
        if int(r or 0):
            return h
    return None


async def set_subscriber_hour(chat_id: int, new_hour: int) -> None:
    old_hour = await get_subscriber_hour(chat_id)
    cmds = []
    if old_hour is not None:
        cmds.append(["SREM", _hour_key(old_hour), chat_id])
    cmds.append(["SADD", _hour_key(new_hour), chat_id])
    await _pipeline(cmds)


# ── Категории ────────────────────────────────────────────────────

async def get_user_categories(chat_id: int) -> list[str]:
    result = await _redis("GET", _cats_key(chat_id))
    if not result or result == "all":
        return ["all"]
    return [c.strip() for c in result.split(",") if c.strip()]


async def set_user_categories(chat_id: int, categories: list[str]) -> None:
    value = ",".join(categories) if categories else "all"
    await _redis("SET", _cats_key(chat_id), value)


# ── Квиз-счёт ───────────────────────────────────────────────────

async def quiz_record_answer(chat_id: int, is_correct: bool) -> dict:
    cmds = [
        ["HINCRBY", _quiz_key(chat_id), "total", 1],
    ]
    if is_correct:
        cmds.append(["HINCRBY", _quiz_key(chat_id), "correct", 1])
    cmds.append(["HGETALL", _quiz_key(chat_id)])
    results = await _pipeline(cmds)
    raw = results[-1] or []
    d = dict(zip(raw[::2], raw[1::2]))
    return {"correct": int(d.get("correct", 0)), "total": int(d.get("total", 0))}


async def get_quiz_stats(chat_id: int) -> dict:
    raw = await _redis("HGETALL", _quiz_key(chat_id))
    if not raw:
        return {"correct": 0, "total": 0}
    d = dict(zip(raw[::2], raw[1::2]))
    return {"correct": int(d.get("correct", 0)), "total": int(d.get("total", 0))}


# ── Счётчик просмотренных фактов ─────────────────────────────────

async def increment_fact_count(chat_id: int) -> int:
    key = f"user_fact_count:{chat_id}"
    new_val = await _redis("INCR", key)
    return int(new_val)


async def get_fact_count(chat_id: int) -> int:
    key = f"user_fact_count:{chat_id}"
    val = await _redis("GET", key)
    return int(val) if val else 0


# ── Глобальная статистика (по всем пользователям) ───────────────

async def get_all_fact_counts() -> int:
    """Суммарное количество просмотренных фактов всеми пользователями."""
    keys = await _redis("KEYS", "user_fact_count:*")
    total = 0
    for key in keys:
        val = await _redis("GET", key)
        if val:
            total += int(val)
    return total


async def get_all_quiz_stats() -> tuple[int, int]:
    """Возвращает (всего правильных ответов, всего ответов) по всем пользователям."""
    keys = await _redis("KEYS", "history_bot:quiz:*")
    total_correct = 0
    total_answers = 0
    for key in keys:
        data = await _redis("HGETALL", key)
        if data:
            d = dict(zip(data[::2], data[1::2]))
            total_correct += int(d.get("correct", 0))
            total_answers += int(d.get("total", 0))
    return total_correct, total_answers
async def is_subscribed(chat_id: int) -> bool:
    """Проверяет, подписан ли пользователь на ежедневную рассылку."""
    # Проверяем по всем часам
    for h in range(24):
        if await _redis("SISMEMBER", _hour_key(h), chat_id):
            return True
    return False
_SUBSCRIBERS_SET = "history_bot:subscribers"
async def get_all_subscribers() -> list[int]:
    """Возвращает список всех подписчиков (без часов)."""
    res = await _redis("SMEMBERS", _SUBSCRIBERS_SET)
    return [int(x) for x in (res or [])]
def get_random_quiz_structured():
    """Возвращает случайный вопрос викторины (структурированный) или None."""
    facts = _load_facts()
    all_quizzes = []
    for date_key, items in facts.items():
        for item in items:
            if "quiz" in item:
                q = item["quiz"].copy()
                month, day = date_key.split('-')
                try:
                    date_obj = date(2000, int(month), int(day))
                    date_str = _format_date_ru(date_obj)
                except:
                    date_str = date_key
                q["date_str"] = date_str
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