from utils.library import *
import logging
import asyncio
import os
from database.database import db
from payments.payment_handler import YooKassaPayment
from payments.webhook_server import WebhookServer
from payments.recurring_payments import RecurringPaymentScheduler
from dotenv import load_dotenv
from handlers.routers import setup_routers
from handlers.admin_panel.inactive_notifications import InactiveUserNotifier
import sys
from aiogram.types import BotCommand

load_dotenv()

# Устанавливаем SelectorEventLoop для Windows
if os.name == 'nt':
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

# Настройка логирования
log_formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')

file_handler = logging.FileHandler('bot.log', encoding='utf-8')
file_handler.setLevel(logging.DEBUG)
file_handler.setFormatter(log_formatter)

console_handler = logging.StreamHandler(sys.stdout)
console_handler.setLevel(logging.INFO)
console_handler.setFormatter(log_formatter)

logging.basicConfig(level=logging.DEBUG, handlers=[file_handler, console_handler])

# total_users = db.get_all_users()
# logging.info(f"Общее количество пользователей: {total_users}")

# db.delete_user(768903494)
# print(f"админы: {db.get_all_admins()}")
# db.set_premium_status(989687907, True, 10)

# Настройка обработчика платежей ЮКассы
SHOP_ID = os.getenv("YOOKASSA_SHOP_ID")
API_KEY = os.getenv("YOOKASSA_API_KEY")
WEBHOOK_PORT = int(os.getenv("WEBHOOK_PORT", 8080))
WEBHOOK_RETURN_URL = os.getenv("WEBHOOK_RETURN_URL")

payment_handler = YooKassaPayment(
    shop_id=SHOP_ID,
    api_key=API_KEY,
    db=db,
    return_url=WEBHOOK_RETURN_URL
)

# Планировщик рекуррентных платежей
recurring_scheduler = None

# Планировщик уведомлений для неактивных пользователей
inactive_notifier = None


async def main():
    global recurring_scheduler, inactive_notifier

    # Установка команды /start
    await bot.set_my_commands([
        BotCommand(command="start", description="Запуск бота"),
    ])

    # Настройка роутеров
    setup_routers(dp)

    # Инициализация вебхук-сервера
    webhook_server = WebhookServer(
        bot=bot,
        db=db,
        payment_handler=payment_handler,
        dp=dp,
        host="0.0.0.0",
        port=WEBHOOK_PORT
    )

    # Инициализация планировщика рекуррентных платежей
    recurring_scheduler = RecurringPaymentScheduler(
        bot=bot,
        db=db,
        payment_handler=payment_handler
    )

    # Инициализация планировщика уведомлений для неактивных пользователе
    inactive_notifier = InactiveUserNotifier(
        bot=bot,
        db=db
    )

    # Запуск вебхук-сервера
    await webhook_server.start()

    # Запуск планировщика рекуррентных платежей
    await recurring_scheduler.start()

    # Запуск планировщика уведомлений
    await inactive_notifier.start()

    logging.info("Бот Янтарик запущен. Используется новая логика с сохранением возраста в БД.")

    # Запуск бота
    await dp.start_polling(bot)


if __name__ == '__main__':
    logging.basicConfig(level=logging.INFO)
    asyncio.run(main())
