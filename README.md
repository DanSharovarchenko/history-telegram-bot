# History Bot — «Этот день в истории»

Telegram-бот, который раз в день присылает подписчикам один исторический факт о событии, случившемся в этот день. Работает на Vercel (Python serverless) с хранением подписчиков в Upstash Redis.

## Структура

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


