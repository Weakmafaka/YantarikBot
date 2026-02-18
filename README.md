# YantarickBot

Telegram-бот с подписками, контентом и AI-помощником.

**Что важно для публикации на GitHub**
- Секреты и ссылки не хранятся в коде — все вынесено в переменные окружения.
- Шаблон переменных: `/Users/weakmafaka/Desktop/PROJECTS/TelegramBot/YantarickBot/utils/.env.example`.

**Требования**
- Python 3.10+

**Установка**
```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

**Конфигурация**
Создайте `.env` в корне проекта на основе шаблона:
```bash
cp utils/.env.example .env
```

Ниже перечислены основные переменные окружения (заполняйте только то, что используете):

- `TOKEN` — токен Telegram-бота.
- `YOOKASSA_SHOP_ID` — ID магазина YooKassa.
- `YOOKASSA_API_KEY` — API-ключ YooKassa.
- `YOOKASSA_BASE_URL` — базовый URL API YooKassa (если используете нестандартный).
- `WEBHOOK_PORT` — порт вебхуков (по умолчанию `8080`).
- `WEBHOOK_RETURN_URL` — URL возврата пользователя после оплаты.
- `PAYMENT_RETURN_REDIRECT_URL` — куда редиректить при `payment-return`.
- `GIFT_LINK_TEMPLATE` — шаблон ссылки на подарок, например `https://t.me/your_bot?start=gift_{gift_code}`.
- `OPENAI_API_KEY` — ключ OpenAI (для AI-помощника).
- `HTTP_PROXY`, `HTTPS_PROXY` — прокси (если нужно).

Контентные ссылки и внешние ресурсы:
- `ABOUT_URL` — ссылка на страницу «О нас».
- `SUPPORT_EMAIL`, `SUPPORT_TELEGRAM` — контакты поддержки.
- `USEFUL_INSTRUCTION_URL` — ссылка на инструкцию в разделе «Полезное».
- `GAME_*_URL` — ссылки на мини-игры.
- `EN_*_URL` — ссылки на контент английского (игры/видео/картинки).

S3:
- `S3_ENDPOINT`
- `S3_ACCESS_KEY`
- `S3_SECRET_KEY`
- `S3_REGION`
- `S3_BUCKET`
- `S3_PUBLIC_URL`

**Запуск**
```bash
python main.py
```

**Примечания**
- Для продакшн-настроек вебхуков используйте шаблоны в `/Users/weakmafaka/Desktop/PROJECTS/TelegramBot/YantarickBot/utils/nginx_config.conf` и `/Users/weakmafaka/Desktop/PROJECTS/TelegramBot/YantarickBot/utils/server_setup_instructions.txt`.
