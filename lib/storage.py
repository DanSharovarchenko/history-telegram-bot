"""
Хранение подписчиков и их настроек в Upstash Redis (HTTP REST API).

Структура ключей:
  history_bot:hour:{HH}        — SET chat_id-ов, подписанных на рассылку в этот час МСК
  history_bot:cats:{chat_id}   — строка с категориями через запятую ("космос,наука") или "all"
  history_bot:quiz:{chat_id}   — HASH {correct, total}
"""

import os
import json
import httpx

UPSTASH_URL = os.environ["UPSTASH_REDIS_REST_URL"].rstrip("/")
UPSTASH_TOKEN = os.environ["UPSTASH_REDIS_REST_TOKEN"]

DEFAULT_HOUR = 9  # МСК


# ── Redis transport ──────────────────────────────────────────────

async def _redis(*command) -> object:
    headers = {"Authorization": f"Bearer {UPSTASH_TOKEN}"}
    payload = [str(x) for x in command]
    async with httpx.AsyncClient(timeout=10) as client:
        r = await client.post(UPSTASH_URL, headers=headers, json=payload)
        r.raise_for_status()
        return r.json().get("result")


async def _pipeline(commands: list[list]) -> list:
    """Выполнить несколько команд за один HTTP-запрос (Upstash pipeline)."""
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
    """Добавить подписчика в SET нужного часа и поставить категории = all."""
    await _pipeline([
        ["SADD", _hour_key(hour), chat_id],
        ["SET", _cats_key(chat_id), "all"],
    ])


async def remove_subscriber(chat_id: int) -> None:
    """Удалить подписчика из всех часовых SET-ов и очистить настройки."""
    cmds = [["SREM", _hour_key(h), chat_id] for h in range(24)]
    cmds.append(["DEL", _cats_key(chat_id)])
    cmds.append(["DEL", _quiz_key(chat_id)])
    await _pipeline(cmds)


async def get_subscribers_for_hour(hour: int) -> list[int]:
    """Вернуть chat_id-ы, подписанные на конкретный час МСК."""
    result = await _redis("SMEMBERS", _hour_key(hour))
    return [int(x) for x in (result or [])]


async def count_subscribers() -> int:
    """Общее число подписчиков (сумма по всем часам)."""
    cmds = [["SCARD", _hour_key(h)] for h in range(24)]
    results = await _pipeline(cmds)
    return sum(int(r or 0) for r in results)


# ── Время рассылки ──────────────────────────────────────────────

async def get_subscriber_hour(chat_id: int) -> int | None:
    """Найти, в каком часовом SET-е состоит подписчик. None = не подписан."""
    cmds = [["SISMEMBER", _hour_key(h), chat_id] for h in range(24)]
    results = await _pipeline(cmds)
    for h, r in enumerate(results):
        if int(r or 0):
            return h
    return None


async def set_subscriber_hour(chat_id: int, new_hour: int) -> None:
    """Перенести подписчика в другой часовой SET."""
    old_hour = await get_subscriber_hour(chat_id)
    cmds = []
    if old_hour is not None:
        cmds.append(["SREM", _hour_key(old_hour), chat_id])
    cmds.append(["SADD", _hour_key(new_hour), chat_id])
    await _pipeline(cmds)


# ── Категории ────────────────────────────────────────────────────

async def get_user_categories(chat_id: int) -> list[str]:
    """Вернуть список категорий пользователя. ['all'] = все."""
    result = await _redis("GET", _cats_key(chat_id))
    if not result or result == "all":
        return ["all"]
    return [c.strip() for c in result.split(",") if c.strip()]


async def set_user_categories(chat_id: int, categories: list[str]) -> None:
    value = ",".join(categories) if categories else "all"
    await _redis("SET", _cats_key(chat_id), value)


# ── Квиз-счёт ───────────────────────────────────────────────────

async def quiz_record_answer(chat_id: int, is_correct: bool) -> dict:
    """Записать ответ и вернуть обновлённую статистику {correct, total}."""
    cmds = [
        ["HINCRBY", _quiz_key(chat_id), "total", 1],
    ]
    if is_correct:
        cmds.append(["HINCRBY", _quiz_key(chat_id), "correct", 1])
    cmds.append(["HGETALL", _quiz_key(chat_id)])
    results = await _pipeline(cmds)
    raw = results[-1] or []
    # HGETALL возвращает плоский список ["key","val","key","val"]
    d = dict(zip(raw[::2], raw[1::2]))
    return {"correct": int(d.get("correct", 0)), "total": int(d.get("total", 0))}


async def get_quiz_stats(chat_id: int) -> dict:
    raw = await _redis("HGETALL", _quiz_key(chat_id))
    if not raw:
        return {"correct": 0, "total": 0}
    d = dict(zip(raw[::2], raw[1::2]))
    return {"correct": int(d.get("correct", 0)), "total": int(d.get("total", 0))}
async def increment_fact_count(chat_id: int) -> int:
    """Увеличивает счётчик просмотренных фактов пользователя и возвращает новое значение."""
    key = f"user_fact_count:{chat_id}"
    # INCR возвращает новое значение
    new_val = await _redis("INCR", key)
    return int(new_val)

async def get_fact_count(chat_id: int) -> int:
    """Возвращает количество просмотренных фактов пользователем."""
    key = f"user_fact_count:{chat_id}"
    val = await _redis("GET", key)
    return int(val) if val else 0
# lib/storage.py – новые функции

_SUBSCRIBERS_SET = "history_bot:subscribers"  # SET chat_id

async def add_subscriber(chat_id: int) -> None:
    """Подписать пользователя на ежедневную рассылку."""
    await _redis("SADD", _SUBSCRIBERS_SET, chat_id)

async def remove_subscriber(chat_id: int) -> None:
    """Отписать пользователя."""
    await _redis("SREM", _SUBSCRIBERS_SET, chat_id)

async def is_subscribed(chat_id: int) -> bool:
    """Проверить, подписан ли пользователь."""
    res = await _redis("SISMEMBER", _SUBSCRIBERS_SET, chat_id)
    return bool(res)

async def get_all_subscribers() -> list[int]:
    """Получить список всех подписанных chat_id."""
    res = await _redis("SMEMBERS", _SUBSCRIBERS_SET)
    return [int(x) for x in (res or [])]

async def count_subscribers() -> int:
    res = await _redis("SCARD", _SUBSCRIBERS_SET)
    return int(res or 0)