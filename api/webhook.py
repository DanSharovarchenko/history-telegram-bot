"""
Webhook-эндпоинт с полным набором команд:
/start, /stop, /help, /today, /random,
/quiz, /category, /subscribe, /compare, /stats

Callback-кнопки: quiz_N (ответ на квиз), random_fact, next_quiz,
cat_set_X, cat_clear, hour_N.
"""

import os
import sys
import re
import json
import asyncio
from http.server import BaseHTTPRequestHandler

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from telegram import Bot, Update, InlineKeyboardButton, InlineKeyboardMarkup  # noqa: E402

from telegram.error import Forbidden, BadRequest, TelegramError

from lib.storage import (  # noqa: E402
    add_subscriber, remove_subscriber, count_subscribers,
    get_subscriber_hour, set_subscriber_hour,
    get_user_categories, set_user_categories,
    quiz_record_answer, get_quiz_stats,
    increment_fact_count, get_fact_count,
    is_subscribed
)
from lib.facts import (  # noqa: E402
    get_today_fact, get_random_fact, get_fact_for_date,
    get_today_fact_filtered, get_facts_by_category,
    get_compare, get_quiz, get_random_quiz,
    ALL_CATEGORIES, get_total_facts_count
)

CHANNEL_ID = -1003947095628          # ID вашего канала (с минусом)
CHANNEL_LINK = "https://t.me/historybotnews"  # Ссылка на канал

BOT_TOKEN = os.environ["BOT_TOKEN"]
ADMIN_CHAT_ID = int(os.environ.get("ADMIN_CHAT_ID", "0"))

HELP_TEXT = (
    "👋 Привет! Я бот «<b>Этот день в истории</b>».\n\n"
    "Каждый день я присылаю исторический факт о событии, "
    "которое произошло именно в этот день.\n\n"
    "<b>Команды:</b>\n"
    "/today — факт на сегодня\n"
    "/random — случайный факт\n"
    "/quiz — викторина по факту дня\n"
    "/compare — этот день в разных странах\n"
    "/fact 05-09 — факт на конкретную дату\n"
    "/category — настроить категории\n"
    "/mystats — моя статистика (сколько фактов просмотрено)\n"
    "/subscribe — подписаться\n"
    "/stop — отписаться\n"
    "/help — это сообщение"
)


# ── Клавиатуры ───────────────────────────────────────────────────

def _quiz_keyboard(quiz_data: dict) -> InlineKeyboardMarkup:
    """Кнопки с вариантами ответа на квиз."""
    buttons = []
    for i, option in enumerate(quiz_data["options"]):
        buttons.append([InlineKeyboardButton(
            option, callback_data=f"quiz_{quiz_data['correct']}_{i}",
        )])
    return InlineKeyboardMarkup(buttons)


def _after_quiz_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🎲 Ещё квиз", callback_data="next_quiz")],
    ])


def _random_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🎲 Ещё факт", callback_data="random_fact")],
    ])


def _category_keyboard(current: list[str]) -> InlineKeyboardMarkup:
    """Кнопки выбора категорий. Выбранные отмечены галочкой."""
    is_all = "all" in current
    rows = []
    for cat in ALL_CATEGORIES:
        if is_all or cat in current:
            label = f"✅ {cat}"
        else:
            label = f"  {cat}"
        rows.append([InlineKeyboardButton(label, callback_data=f"cat_toggle_{cat}")])
    rows.append([
        InlineKeyboardButton(
            "🔄 Сбросить (все)" if not is_all else "✅ Все категории",
            callback_data="cat_clear",
        ),
    ])
    rows.append([InlineKeyboardButton("✏️ Готово", callback_data="cat_done")])
    return InlineKeyboardMarkup(rows)


def _subscribe_keyboard(current_hour: int | None) -> InlineKeyboardMarkup:
    """Кнопки выбора часа рассылки (МСК) от 0 до 23."""
    rows = []
    # Разбиваем часы на строки по 6 кнопок
    for i in range(0, 24, 6):
        row = []
        for h in range(i, i + 6):
            label = f"{'✅ ' if current_hour == h else ''}{h:02d}:00"
            row.append(InlineKeyboardButton(label, callback_data=f"hour_{h}"))
        rows.append(row)
    return InlineKeyboardMarkup(rows)


async def is_subscribed_to_channel(user_id: int, bot: Bot) -> bool:
    """Проверяет, подписан ли пользователь на канал."""
    try:
        member = await bot.get_chat_member(chat_id=CHANNEL_ID, user_id=user_id)
        return member.status in ('member', 'administrator', 'creator')
    except TelegramError as e:
        print(f"[ERROR] Проверка подписки для {user_id} не удалась: {e}", file=sys.stderr)
        return False

async def require_subscription(chat_id: int, user_id: int, bot: Bot) -> bool:
    """Если не подписан – отправляет сообщение с кнопкой и возвращает False. Иначе True."""
    if await is_subscribed_to_channel(user_id, bot):
        return True
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("➕ ПОДПИСАТЬСЯ", url=CHANNEL_LINK)]
    ])
    await bot.send_message(
        chat_id,
        "🚫 **Для использования бота необходимо подписаться на наш канал.**\n\n"
        "Нажмите кнопку ниже, подпишитесь, а затем повторите команду.",
        parse_mode="Markdown",
        reply_markup=keyboard
    )
    return False

# ── Обработка callback-кнопок ────────────────────────────────────

async def handle_callback(query, bot: Bot) -> None:
    chat_id = query.message.chat_id
    user_id = query.from_user.id

    if not await require_subscription(chat_id, user_id, bot):
        await query.answer("Доступ запрещён. Подпишитесь на канал.", show_alert=True)
        return
    data = query.data


    # ── Квиз: ответ ──
    if data.startswith("quiz_"):
        # Формат: quiz_{correct}_{chosen}
        parts = data.split("_")
        correct_idx = int(parts[1])
        chosen_idx = int(parts[2])
        is_correct = correct_idx == chosen_idx

        stats = await quiz_record_answer(chat_id, is_correct)
        pct = round(stats["correct"] / stats["total"] * 100) if stats["total"] else 0

        if is_correct:
            text = "✅ <b>Правильно!</b>"
        else:
            text = "❌ <b>Неправильно.</b>"
        text += f"\n\n📊 Ваш счёт: {stats['correct']}/{stats['total']} ({pct}%)"


        await query.answer("✅ Верно!" if is_correct else "❌ Неверно")
        await bot.send_message(
            chat_id, text,
            parse_mode="HTML",
            reply_markup=_after_quiz_keyboard(),
        )
        # Убираем кнопки со старого сообщения
        try:
            await query.edit_message_reply_markup(reply_markup=None)
        except Exception:
            pass
        return

    # ── Следующий квиз ──
    if data == "next_quiz":
        await query.answer()
        quiz_data = await get_random_quiz()
        if not quiz_data:
            await bot.send_message(chat_id, "В базе пока нет вопросов для квиза.")
            return
        text = (
            f"❓ <b>Квиз — {quiz_data['date_str']}</b>\n\n"
            f"{quiz_data['question']}"
        )
        await bot.send_message(
            chat_id, text,
            parse_mode="HTML",
            reply_markup=_quiz_keyboard(quiz_data),
        )
        return

    # ── Ещё случайный факт ──
    if data == "random_fact":
        await query.answer()
        fact = await get_random_fact()
        await increment_fact_count(chat_id)
        await bot.send_message(
            chat_id, fact,
            parse_mode="HTML",
            disable_web_page_preview=True,
            reply_markup=_random_keyboard(),
        )
        try:
            await query.message.delete()
        except Exception:
            pass
        return

    # ── Категории: toggle ──
    if data.startswith("cat_toggle_"):
        cat = data[len("cat_toggle_"):]
        current = await get_user_categories(chat_id)
        if "all" in current:
            # Переключаемся с «все» на конкретные — убираем нажатую
            current = [c for c in ALL_CATEGORIES if c != cat]
        elif cat in current:
            current.remove(cat)
            if not current:
                current = ["all"]
        else:
            current.append(cat)
            if set(current) >= set(ALL_CATEGORIES):
                current = ["all"]
        await set_user_categories(chat_id, current)
        await query.answer(f"{cat}: {'✅' if cat in current or 'all' in current else '❌'}")
        try:
            await query.edit_message_reply_markup(
                reply_markup=_category_keyboard(current),
            )
        except Exception:
            pass
        return

    # ── Категории: сброс на «все» ──
    if data == "cat_clear":
        await set_user_categories(chat_id, ["all"])
        await query.answer("Сброшено: все категории")
        try:
            await query.edit_message_reply_markup(
                reply_markup=_category_keyboard(["all"]),
            )
        except Exception:
            pass
        return

    # ── Категории: готово ──
    if data == "cat_done":
        current = await get_user_categories(chat_id)
        if "all" in current:
            label = "все"
        else:
            label = ", ".join(current)
        await query.answer("Сохранено!")
        try:
            await query.edit_message_text(
                f"✅ Категории сохранены: <b>{label}</b>\n\n"
                "Ежедневная рассылка будет учитывать ваш выбор.",
                parse_mode="HTML",
            )
        except Exception:
            pass
        return

    # ── Время рассылки ──
    if data.startswith("hour_"):
        hour = int(data[5:])
        await set_subscriber_hour(chat_id, hour)
        await query.answer(f"Рассылка в {hour:02d}:00 МСК")
        try:
            await query.edit_message_text(
                f"✅ Рассылка установлена на <b>{hour:02d}:00 МСК</b>.\n\n"
                "Изменить: /subscribe",
                parse_mode="HTML",
            )
        except Exception:
            pass
        return

    await query.answer()


# ── Обработка текстовых команд ───────────────────────────────────

async def handle_message(update: Update, bot: Bot) -> None:
    msg = update.effective_message
    if msg is None or not msg.text:
        return
    chat_id = update.effective_chat.id
    user_id = update.effective_user.id

    # Проверка подписки
    if not await require_subscription(chat_id, user_id, bot):
        return
    text = msg.text.strip()
    cmd = text.split()[0].split("@")[0].lower()

    # /start
    if cmd == "/start":
        await add_subscriber(chat_id)
        await bot.send_message(chat_id, HELP_TEXT, parse_mode="HTML")

    # /stop
    elif cmd == "/stop":
        await remove_subscriber(chat_id)
        await bot.send_message(chat_id, "Вы отписались. Возвращайтесь через /start 👋")

    # /today
    elif cmd == "/today":
        cats = await get_user_categories(chat_id)
        fact = await get_today_fact_filtered(categories=cats)
        await increment_fact_count(chat_id)
        await bot.send_message(
            chat_id, fact,
            parse_mode="HTML", disable_web_page_preview=True,
        )
    elif cmd == "/help":
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("📩 Связаться с автором", url="https://t.me/yan3danya")]
        ])
        await bot.send_message(chat_id, HELP_TEXT, parse_mode="HTML", reply_markup=keyboard)
    # /random
    elif cmd == "/random":
        fact = await get_random_fact()
        await increment_fact_count(chat_id)
        await bot.send_message(
            chat_id, fact,
            parse_mode="HTML",
            disable_web_page_preview=True,
            reply_markup=_random_keyboard(),
        )

    # /quiz
    elif cmd == "/quiz":
        quiz_data = await get_quiz()
        if not quiz_data:
            # Если на сегодня нет — берём случайный
            quiz_data = await get_random_quiz()
        if not quiz_data:
            await bot.send_message(chat_id, "В базе пока нет вопросов для квиза. Скоро добавим!")
            return
        text_out = (
            f"❓ <b>Квиз — {quiz_data['date_str']}</b>\n\n"
            f"{quiz_data['question']}"
        )
        await bot.send_message(
            chat_id, text_out,
            parse_mode="HTML",
            reply_markup=_quiz_keyboard(quiz_data),
        )

    # /compare [MM-DD]
    elif cmd == "/compare":
        parts = text.split()
        date = None
        if len(parts) >= 2:
            date_arg = parts[1].replace(".", "-")
            m_match = re.match(r"^(\d{2})-(\d{2})$", date_arg)
            if m_match:
                import datetime
                try:
                    date = datetime.date(
                        datetime.date.today().year,
                        int(m_match.group(1)),
                        int(m_match.group(2)),
                    )
                except ValueError:
                    pass
        result = await get_compare(date)
        await bot.send_message(
            chat_id, result,
            parse_mode="HTML", disable_web_page_preview=True,
        )
    elif cmd == "/mystats":
        fact_count = await get_fact_count(chat_id)
        total_facts = await get_total_facts_count()
        quiz_stats = await get_quiz_stats(chat_id)
        quiz_correct = quiz_stats["correct"]
        quiz_total = quiz_stats["total"]
        quiz_pct = round(quiz_correct / quiz_total * 100) if quiz_total else 0

        await bot.send_message(
            chat_id,
            f"📊 <b>Ваша статистика</b>\n\n"
            f"📖 Просмотрено фактов: <b>{fact_count}</b>\n"
            f"🧠 Квизы: <b>{quiz_correct}</b> / {quiz_total} правильных ({quiz_pct}%)\n\n"
            f"📚 Всего фактов в базе: <b>{total_facts}</b>\n\n"
            f"Продолжайте узнавать новое! 🚀",
            parse_mode="HTML",
        )
    # /fact MM-DD
    elif cmd == "/fact":
        parts = text.split()
        if len(parts) < 2:
            await bot.send_message(chat_id, "📅 Укажите дату: /fact 05-09")
            return
        date_arg = parts[1].replace(".", "-")
        if not re.match(r"^(0[1-9]|1[0-2])-(0[1-9]|[12]\d|3[01])$", date_arg):
            await bot.send_message(chat_id, "❌ Неверный формат. Используйте: /fact 05-09 (месяц-день)")
            return
        fact = await get_fact_for_date(date_arg)
        if fact is None:
            await bot.send_message(chat_id, f"📭 На {date_arg} фактов пока нет.")
            return
        await increment_fact_count(chat_id)
        await bot.send_message(
            chat_id, fact,
            parse_mode="HTML", disable_web_page_preview=True,
        )

    # /category
    elif cmd == "/category":
        current = await get_user_categories(chat_id)
        if "all" in current:
            label = "все"
        else:
            label = ", ".join(current)
        await bot.send_message(
            chat_id,
            f"📂 <b>Ваши категории:</b> {label}\n\n"
            "Нажимайте, чтобы включить/выключить:",
            parse_mode="HTML",
            reply_markup=_category_keyboard(current),
        )

    # /subscribe
    elif cmd == "/subscribe":
        if await is_subscribed(chat_id):
            await remove_subscriber(chat_id)
            await bot.send_message(chat_id,
                                   "❌ Вы отписались от ежедневной рассылки. Чтобы снова подписаться, используйте /subscribe.")
        else:
            await add_subscriber(chat_id)
            await bot.send_message(chat_id,
                                   "✅ Вы подписались на ежедневную рассылку! Каждый день в 12:00 МСК я буду присылать исторический факт.")

    # /help
    elif cmd == "/help":
        await bot.send_message(chat_id, HELP_TEXT, parse_mode="HTML")

    # /stats (только админу)
    elif cmd == "/stats" and ADMIN_CHAT_ID and chat_id == ADMIN_CHAT_ID:
        n = await count_subscribers()
        my_stats = await get_quiz_stats(chat_id)
        await bot.send_message(
            chat_id,
            f"📊 Подписчиков: <b>{n}</b>\n"
            f"🧠 Ваш квиз: {my_stats['correct']}/{my_stats['total']}",
            parse_mode="HTML",
        )

    else:
        await bot.send_message(chat_id, "Не понимаю команду. /help — список команд.")


# ── Точка входа ──────────────────────────────────────────────────

async def handle_update(update: Update, bot: Bot) -> None:
    if update.callback_query:
        await handle_callback(update.callback_query, bot)
        return
    await handle_message(update, bot)


async def process(body: dict) -> None:
    bot = Bot(token=BOT_TOKEN)
    async with bot:
        update = Update.de_json(body, bot)
        if update is not None:
            await handle_update(update, bot)


class handler(BaseHTTPRequestHandler):
    def do_POST(self):
        n = int(self.headers.get("Content-Length", 0))
        raw = self.rfile.read(n).decode("utf-8") if n else "{}"
        try:
            body = json.loads(raw)
            asyncio.run(process(body))
        except Exception as e:
            print(f"[webhook] error: {e!r}", file=sys.stderr)
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(b'{"ok":true}')

    def do_GET(self):
        self.send_response(200)
        self.send_header("Content-Type", "text/plain; charset=utf-8")
        self.end_headers()
        self.wfile.write(b"History bot webhook is alive.")
