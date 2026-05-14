# History Bot — «Этот день в истории»

Telegram-бот, который раз в день присылает подписчикам один исторический факт о событии, случившемся в этот день. Работает на Vercel (Python serverless) с хранением подписчиков в Upstash Redis.

## Структура

```
.
├── api/
│   ├── webhook.py    # принимает /start, /stop, /today, /help, /stats
│   ├── cron.py       # ежедневная рассылка (вызывается Vercel Cron)
│   └── setup.py      # одноразовая установка webhook
├── lib/
│   ├── storage.py    # Upstash Redis через HTTP REST
│   └── facts.py      # выдача факта на дату
├── data/
│   └── facts.json    # курируемые факты {"MM-DD": [{year, text, link}]}
├── requirements.txt
├── vercel.json       # конфиг Vercel + расписание cron
└── .env.example
```

## Деплой за 10 минут

### 1. Создать бота
- Написать [@BotFather](https://t.me/BotFather) → `/newbot` → получить `BOT_TOKEN`.
- Опционально: `/setcommands` со списком:
  ```
  start - подписаться
  today - факт на сегодня
  stop - отписаться
  help - помощь
  ```

### 2. Завести Upstash Redis
- Регистрация на [upstash.com](https://upstash.com), Create Database → Global.
- Скопировать `UPSTASH_REDIS_REST_URL` и `UPSTASH_REDIS_REST_TOKEN`.

### 3. Задеплоить на Vercel
```bash
npm i -g vercel
vercel deploy
```
После первого деплоя в Vercel Dashboard → Settings → Environment Variables добавить:

| Переменная | Откуда взять |
|---|---|
| `BOT_TOKEN` | от BotFather |
| `WEBHOOK_URL` | `https://<your-app>.vercel.app/api/webhook` |
| `SETUP_SECRET` | `openssl rand -hex 32` |
| `CRON_SECRET` | `openssl rand -hex 32` |
| `UPSTASH_REDIS_REST_URL` | из Upstash |
| `UPSTASH_REDIS_REST_TOKEN` | из Upstash |
| `ADMIN_CHAT_ID` | (опционально) ваш `chat_id` для `/stats` |

После добавления переменных — `vercel deploy --prod`.

### 4. Прописать webhook
Открыть в браузере один раз:
```
https://<your-app>.vercel.app/api/setup?key=<SETUP_SECRET>
```
Должен прийти JSON вида `{"ok": true, "url": "..."}`.

### 5. Проверить
- Написать боту `/start` → должно прийти приветствие.
- Написать `/today` → факт на сегодня.

Cron сам отработает в 09:00 МСК (06:00 UTC) — расписание в `vercel.json`.

## Как добавлять факты

Редактировать `data/facts.json`. Ключ — `MM-DD`, значение — массив фактов:
```json
"04-12": [
  {
    "year": 1961,
    "text": "Юрий Гагарин совершил первый полёт в космос.",
    "link": "https://ru.wikipedia.org/wiki/Восток-1"
  }
]
```

Если на дату несколько фактов, бот ротирует их по году: `year % len(facts)`. Так каждый год на ту же дату подписчик видит разный факт.

Текст поддерживает HTML-форматирование Telegram (`<b>`, `<i>`, `<a>`, `<code>`).

После правки — `vercel deploy --prod`.

## Полезное

**Изменить время рассылки.** В `vercel.json` поле `schedule` — cron-выражение в UTC. Например, `0 5 * * *` = 08:00 МСК.

**Локальная отладка.** `vercel dev` поднимает функции локально, но для cron и webhook нужен публичный URL (ngrok или сразу деплой в preview).

**Масштаб.** При >10K подписчиков 60 секунд cron-функции на free-тарифе перестанет хватать (лимит Telegram ~30 msg/sec → 1800 за минуту). Тогда: разбить рассылку на несколько cron-эндпоинтов или вынести в очередь (Upstash QStash подходит).

**Расширения.** Куда логично двигаться:
- Категории фактов и подписка на одну («только наука», «только Россия»)
- Часовой пояс на пользователя (хранить в Redis рядом с `chat_id`)
- `/random` — случайный факт из любой даты
- Веб-админка для пополнения `facts.json` без редеплоя (тогда переезд фактов в Redis или Postgres)

## Лицензия

MIT — делайте что хотите.
