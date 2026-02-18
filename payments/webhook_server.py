import os
import logging
import json
from typing import Dict, Any, Optional, Callable

from aiohttp import web
from aiogram import Bot, Dispatcher

from database.database import Database
from payments.payment_handler import YooKassaPayment


class WebhookServer:
    def __init__(self, bot: Bot, db: Database, payment_handler: YooKassaPayment, dp: Dispatcher,
                 host: str = "0.0.0.0", port: int = 8080, 
                 payment_notification_path: str = "/payment-notification",
                 payment_return_path: str = "/payment-return"):
        """
        Инициализация веб-сервера для обработки вебхуков от ЮКассы
        
        :param bot: Экземпляр бота
        :param db: Экземпляр базы данных
        :param payment_handler: Обработчик платежей ЮКассы
        :param dp: Экземпляр диспетчера
        :param host: Хост для запуска сервера
        :param port: Порт для запуска сервера
        :param payment_notification_path: Путь для уведомлений от ЮКассы
        :param payment_return_path: Путь для возврата пользователя после оплаты
        """
        self.bot = bot
        self.db = db
        self.payment_handler = payment_handler
        self.dp = dp
        self.host = host
        self.port = port
        self.payment_notification_path = payment_notification_path
        self.payment_return_path = payment_return_path
        self.app = None
        self.logger = logging.getLogger("WebhookServer")
        
        # Устанавливаем полный URL для возврата пользователя из окружения
        self.return_url = os.environ.get("WEBHOOK_RETURN_URL")
            
        # Настраиваем обработчик платежей с учетом URL возврата
        self.payment_handler.return_url = self.return_url
    
    async def handle_payment_notification(self, request: web.Request) -> web.Response:
        """
        Обработка уведомления от ЮКассы о статусе платежа
        
        :param request: HTTP запрос
        :return: HTTP ответ
        """
        try:
            notification_data = await request.json()
            self.logger.info(f"Received payment notification: {notification_data}")
            
            # Обрабатываем уведомление о платеже
            success, user = await self.payment_handler.process_payment_notification(notification_data)
            
            if success and user:
                user_id = user["user_id"]
                # Обработка подарочной подписки
                payment = notification_data.get("object", {})
                payment_status = payment.get("status", "unknown")
                metadata = payment.get("metadata", {})
                if metadata.get("payment_type") == "gift" and payment_status == "succeeded":
                    gift_code = metadata.get("gift_code")
                    gift_link_template = os.environ.get("GIFT_LINK_TEMPLATE")
                    if gift_link_template:
                        gift_link = gift_link_template.format(gift_code=gift_code)
                        await self.bot.send_message(user_id, f"Ваша ссылка для подарка: {gift_link}")
                    else:
                        await self.bot.send_message(user_id, "Подарочная ссылка временно недоступна.")
                    return web.Response(status=200, text="OK")
                
                # Добавляем проверку - не отправлять сообщение об отмене, если у пользователя активная подписка
                should_send_notification = True
                if payment_status == "canceled":
                    # Проверяем статус подписки пользователя перед отправкой уведомления
                    is_premium = self.db.check_premium_status(user_id)
                    if is_premium:
                        self.logger.info(f"User {user_id} has active premium subscription, skipping canceled payment notification")
                        should_send_notification = False
                
                if should_send_notification:
                    status_message = await self.payment_handler.get_payment_status_message(payment_status)
                    message = await self.bot.send_message(user_id, status_message)
                    
                    # Если платеж успешен, открываем главное меню
                    if payment_status == "succeeded":
                        from handlers.common import show_main_menu
                        from aiogram.fsm.context import FSMContext
                        
                        age_group = self.db.get_user_age(user_id)
                        key = f"chat:{user_id}:user:{user_id}:state"
                        state = FSMContext(self.dp.storage, key)
                        await state.set_state(None)
                        await show_main_menu(user_id, age_group, state)
            
            return web.Response(status=200, text="OK")
        except Exception as e:
            self.logger.error(f"Error handling payment notification: {e}")
            return web.Response(status=500, text="Error processing notification")
    
    async def handle_payment_return(self, request: web.Request) -> web.Response:
        """
        Обработка возврата пользователя после оплаты
        
        :param request: HTTP запрос
        :return: HTTP ответ - страница с информацией о статусе платежа
        """
        try:
            # Получаем параметры запроса
            query_params = request.query
            payment_id = query_params.get("payment_id")
            
            # Редиректим на заданный URL (если указан)
            redirect_url = os.environ.get("PAYMENT_RETURN_REDIRECT_URL")
            if redirect_url:
                return web.HTTPFound(redirect_url)
            return web.Response(status=200, text="OK")
        except Exception as e:
            self.logger.error(f"Error handling payment return: {e}")
            redirect_url = os.environ.get("PAYMENT_RETURN_REDIRECT_URL")
            if redirect_url:
                return web.HTTPFound(redirect_url)
            return web.Response(status=200, text="OK")
    
    async def start(self) -> None:
        """
        Запуск веб-сервера
        """
        self.app = web.Application()
        self.app.router.add_post(r"/payment-notification{slash:/?}", self.handle_payment_notification)
        self.app.router.add_get(r"/payment-return{slash:/?}", self.handle_payment_return)
        
        runner = web.AppRunner(self.app)
        await runner.setup()
        site = web.TCPSite(runner, self.host, self.port)
        await site.start()
        
        self.logger.info(f"Webhook server started on {self.host}:{self.port}")
        self.logger.info(f"Payment notification URL: {self.payment_notification_path}")
        self.logger.info(f"Payment return URL: {self.return_url}")
    
    def get_return_url(self) -> str:
        """
        Получение URL для возврата пользователя после оплаты
        
        :return: URL для возврата
        """
        return self.return_url 
