# discord-f1-reminder

Discord bot that sends reminders for F1 race weekend sessions with weather forecasts and live updates.

## Features

- Notifications before Practice, Qualifying, Sprint, and Race sessions
- Weather forecasts with rain probability and radar links
- Weather update alerts when rain chance changes significantly
- Live timing links and circuit info
- Qualifying grid results when available

## Setup

Create a `.env` file:

```
DISCORD_WEBHOOK_URL=your_webhook_url
WEATHER_API_KEY=your_openweathermap_key
NOTIFICATION_LEAD_MINUTES=45
BOT_NAME=F1 Reminder Bot
```

## Run

```
pip install -r requirements.txt
python main.py
```

## Docker

```
docker build -t f1-reminder .
docker run --env-file .env f1-reminder
```

## Deployment

Deployed via Dokku with GitHub Actions CI/CD.
