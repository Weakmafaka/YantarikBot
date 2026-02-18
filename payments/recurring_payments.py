import asyncio
import logging
import datetime
from typing import List, Dict, Any

from aiogram import Bot
from database.database import Database
from payments.payment_handler import YooKassaPayment


class RecurringPaymentScheduler:
    def __init__(self, bot: Bot, db: Database, payment_handler: YooKassaPayment, check_interval: int = 3600):
        """
        Инициализация планировщика для рекуррентных платежей
        
        :param bot: Экземпляр бота
        :param db: Экземпляр базы данных
        :param payment_handler: Обработчик платежей ЮКассы
        :param check_interval: Интервал проверки в секундах (по умолчанию 1 час)
        """
        self.bot = bot
        self.db = db
        self.payment_handler = payment_handler
        self.check_interval = check_interval
        self.logger = logging.getLogger("RecurringPaymentScheduler")
        self.is_running = False
        self.task = None
    
    async def start(self) -> None:
        """
        Запуск планировщика
        """
        if self.is_running:
            return
        
        self.is_running = True
        self.task = asyncio.create_task(self._run_scheduler())
        self.logger.info("Recurring payment scheduler started")
    
    async def stop(self) -> None:
        """
        Остановка планировщика
        """
        if not self.is_running or not self.task:
            return
        
        self.is_running = False
        self.task.cancel()
        try:
            await self.task
        except asyncio.CancelledError:
            pass
        self.logger.info("Recurring payment scheduler stopped")
    
    async def _run_scheduler(self) -> None:
        """
        Основной цикл планировщика
        """
        while self.is_running:
            try:
                await self._process_recurring_payments()
            except Exception as e:
                self.logger.error(f"Error processing recurring payments: {e}")
            
            # Ждем до следующей проверки
            await asyncio.sleep(self.check_interval)
    
    async def _process_recurring_payments(self) -> None:
        """
        Обработка рекуррентных платежей
        """
        self.logger.info("Checking for users with expired premium subscriptions")
        
        # Получаем список пользователей для рекуррентного платежа
        users = self.db.get_users_for_recurring_payment()
        
        if not users:
            self.logger.info("No users found for recurring payments")
            return
        
        self.logger.info(f"Found {len(users)} users for recurring payments")
        
        # Обрабатываем каждого пользователя
        for user in users:
            user_id = user["user_id"]
            payment_method_id = user["payment_method_id"]
            
            self.logger.info(f"Processing recurring payment for user {user_id}")
            
            try:
                # Создаем рекуррентный платеж
                payment_info = await self.payment_handler.create_recurring_payment(user_id, payment_method_id)
                
                if not payment_info:
                    self.logger.error(f"Failed to create recurring payment for user {user_id}")
                    await self._notify_user_about_payment_failure(user_id)
                    continue
                
                # Проверяем статус платежа
                payment_status = payment_info.get("status")
                
                if payment_status == "succeeded":
                    # Платеж успешен - обновляем статус премиум подписки и уведомляем пользователя
                    self.db.set_premium_status(user_id, True, 30)
                    await self._notify_user_about_successful_payment(user_id)
                elif payment_status == "pending" or payment_status == "waiting_for_capture":
                    # Платеж в обработке - отмечаем это в логах
                    self.logger.info(f"Recurring payment for user {user_id} is in progress")
                else:
                    # Платеж не удался - уведомляем пользователя
                    self.logger.error(f"Recurring payment for user {user_id} failed with status {payment_status}")
                    await self._notify_user_about_payment_failure(user_id)
            except Exception as e:
                self.logger.error(f"Error processing recurring payment for user {user_id}: {e}")
                await self._notify_user_about_payment_failure(user_id)
    
    async def _notify_user_about_successful_payment(self, user_id: int) -> None:
        """
        Уведомление пользователя об успешном автоматическом продлении подписки
        
        :param user_id: ID пользователя
        """
        try:
            message = (
                "Ваша премиум-подписка успешно продлена на 30 дней! 📅\n\n"
                "С вашей карты списано 250 рублей. Вы можете продолжать пользоваться "
                "всеми премиум-функциями бота, включая раздел 'Полезное 🔓'.\n\n"
                "Следующее автоматическое продление произойдет через 30 дней."
            )
            await self.bot.send_message(user_id, message)
            self.logger.info(f"Sent successful payment notification to user {user_id}")
            
            # Открываем главное меню
            from handlers.common import show_main_menu
            from aiogram.fsm.storage.memory import MemoryStorage
            from aiogram.fsm.context import FSMContext
            
            # Получаем возрастную группу пользователя
            age_group = self.db.get_user_age(user_id)
            
            # Создаем объект состояния
            storage = MemoryStorage()
            state = FSMContext(storage=storage, key=storage.build_key(bot=self.bot, user_id=user_id, chat_id=user_id))
            
            # Открываем главное меню (не редактируя текущее сообщение)
            await show_main_menu(user_id, age_group, state)
        except Exception as e:
            self.logger.error(f"Failed to send successful payment notification to user {user_id}: {e}")
    
    async def _notify_user_about_payment_failure(self, user_id: int) -> None:
        """
        Уведомление пользователя о неудачном автоматическом продлении подписки
        
        :param user_id: ID пользователя
        """
        try:
            # Проверяем, есть ли у пользователя активная подписка
            is_premium = self.db.check_premium_status(user_id)
            if is_premium:
                self.logger.info(f"User {user_id} has active premium subscription, skipping payment failure notification")
                return
                
            message = (
                "Не удалось автоматически продлить вашу премиум-подписку ❌\n\n"
                "Причина может быть в недостатке средств на карте или в технических проблемах. "
                "Вы можете обновить способ оплаты или оплатить подписку вручную, "
                "нажав на кнопку 'Премиум подписка 💳' в главном меню бота.\n\n"
                "Доступ к разделу 'Полезное 🔓' временно приостановлен."
            )
            await self.bot.send_message(user_id, message)
            self.logger.info(f"Sent payment failure notification to user {user_id}")
        except Exception as e:
            self.logger.error(f"Failed to send payment failure notification to user {user_id}: {e}")
    
    async def check_now(self) -> None:
        """
        Немедленная проверка и обработка рекуррентных платежей
        """
        self.logger.info("Manual check for recurring payments triggered")
        await self._process_recurring_payments()
        self.logger.info("Manual check for recurring payments completed") 