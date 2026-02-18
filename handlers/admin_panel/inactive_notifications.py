import logging
import asyncio
import pytz
from datetime import datetime
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from aiogram import Bot
from database.database import Database

class InactiveUserNotifier:
    def __init__(self, bot: Bot, db: Database):
        self.bot = bot
        self.db = db
        self.scheduler = AsyncIOScheduler()
        self.moscow_tz = pytz.timezone('Europe/Moscow')
        
        # Тексты уведомлений
        self.notifications = {
            "tuesday": {
                "text": "🎯 Привет! Мы скучаем по тебе в боте Янтарик! Загляни к нам, у нас много интересного для твоего малыша: сказки, мультики, игры и многое другое! 🧙‍♂️✨",
                "hour": 14,
                "minute": 0
            },
            "friday": {
                "text": "✨ Мамочка, не забывай про Янтарика! В нашем боте появился новый контент для твоего ребенка. Заходи, будем рады тебя видеть! 🎁🧸",
                "hour": 14,
                "minute": 0
            }
        }
    
    async def start(self):
        """Запускает планировщик с настроенными задачами."""
        logging.info("Запуск планировщика уведомлений неактивным пользователям...")
        
        # Уведомление во вторник
        self.scheduler.add_job(
            self.send_notification,
            CronTrigger(
                day_of_week="tue", 
                hour=self.notifications["tuesday"]["hour"], 
                minute=self.notifications["tuesday"]["minute"], 
                timezone=self.moscow_tz
            ),
            kwargs={"notification_type": "tuesday"},
            id="tuesday_notification"
        )
        
        # Уведомление в пятницу
        self.scheduler.add_job(
            self.send_notification,
            CronTrigger(
                day_of_week="fri", 
                hour=self.notifications["friday"]["hour"], 
                minute=self.notifications["friday"]["minute"], 
                timezone=self.moscow_tz
            ),
            kwargs={"notification_type": "friday"},
            id="friday_notification"
        )
        
        # Запуск планировщика
        self.scheduler.start()
        logging.info(f"Планировщик уведомлений запущен. Следующие уведомления:")
        for job in self.scheduler.get_jobs():
            next_run = job.next_run_time.astimezone(self.moscow_tz).strftime("%d.%m.%Y %H:%M:%S")
            logging.info(f"- {job.id}: {next_run} (МСК)")
    
    async def send_notification(self, notification_type: str):
        """Отправляет уведомления неактивным пользователям.
        
        Args:
            notification_type (str): Тип уведомления ('tuesday' или 'friday')
        """
        if notification_type not in self.notifications:
            logging.error(f"Неизвестный тип уведомления: {notification_type}")
            return
        
        notification_text = self.notifications[notification_type]["text"]
        logging.info(f"Отправка уведомлений ({notification_type})...")
        
        # Получаем неактивных более 2 дней пользователей
        inactive_users = self.db.get_inactive_users(days=2)
        
        if not inactive_users:
            logging.info("Нет неактивных пользователей для отправки уведомлений")
            return
        
        success_count = 0
        error_count = 0
        
        for user in inactive_users:
            user_id = user["user_id"]
            try:
                # Отправка уведомления пользователю
                await self.bot.send_message(
                    chat_id=user_id,
                    text=notification_text
                )
                success_count += 1
                
                # Небольшая задержка между отправками, чтобы не получить блокировку от Telegram
                # Для больших баз данных рекомендуется увеличить задержку
                await asyncio.sleep(0.05)
                
            except Exception as e:
                logging.error(f"Ошибка при отправке уведомления пользователю {user_id}: {e}")
                error_count += 1
        
        logging.info(f"Отправка уведомлений завершена. Успешно: {success_count}, ошибок: {error_count}")
    
    async def stop(self):
        """Останавливает планировщик."""
        self.scheduler.shutdown()
        logging.info("Планировщик уведомлений остановлен") 