import uuid
import os
import datetime
import secrets
import logging
from typing import Dict, Any, Optional, Tuple

import aiohttp
import json
from aiogram import Bot
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton

from database.database import Database


class YooKassaPayment:
    def __init__(self, shop_id: str, api_key: str, db: Database, return_url: str):
        """
        Инициализация класса для работы с ЮКассой
        
        :param shop_id: Идентификатор магазина в ЮКассе
        :param api_key: Секретный ключ для API ЮКассы
        :param db: Экземпляр базы данных
        :param return_url: URL для возврата после оплаты
        """
        self.shop_id = shop_id
        self.api_key = api_key
        self.db = db
        self.return_url = return_url
        self.base_url = os.getenv("YOOKASSA_BASE_URL")
        self.logger = logging.getLogger("YooKassaPayment")
    
    async def create_trial_payment(self, user_id: int, username: str, first_name: str) -> Optional[Dict[str, Any]]:
        """
        Создание пробного платежа на 1 рубль для подключения премиум на 3 дня
        
        :param user_id: ID пользователя в Telegram
        :param username: Username пользователя
        :param first_name: Имя пользователя
        :return: Данные о созданном платеже или None в случае ошибки
        """
        # Добавляем пользователя в БД, если его там еще нет
        self.db.add_user(user_id, username, first_name)
        
        # Проверяем, не использовал ли пользователь уже триальный период
        user = self.db.get_user(user_id)
        if user["trial_used"]:
            return await self.create_regular_payment(user_id)
        
        # Идентификатор платежа
        payment_id = f"trial_{user_id}_{uuid.uuid4()}"
        
        # Логирование для теста
        self.logger.info(f"[TRIAL] user_id={user_id}, username={username}, first_name={first_name}, trial_used={user['trial_used']}")
        
        # Данные для запроса на создание платежа
        payment_data = {
            "amount": {
                "value": "1.00",
                "currency": "RUB"
            },
            "capture": True,
            "confirmation": {
                "type": "redirect",
                "return_url": self.return_url
            },
            "description": f"Пробная подписка на 3 дня для пользователя {username or first_name or user_id}",
            "metadata": {
                "user_id": user_id,
                "payment_type": "trial"
            },
            "save_payment_method": True,
            "merchant_customer_id": str(user_id),
            "receipt": {
                "customer": {
                    "email": "user@example.com"
                },
                "items": [
                    {
                        "description": "Пробная подписка на 3 дня",
                        "quantity": 1.0,
                        "amount": {
                            "value": "1.00",
                            "currency": "RUB"
                        },
                        "vat_code": 1,
                        "payment_mode": "full_prepayment",
                        "payment_subject": "service"
                    }
                ]
            }
        }
        
        # Выполняем запрос к API ЮКассы
        headers = {
            "Content-Type": "application/json",
            "Idempotence-Key": secrets.token_hex(16)
        }
        auth = aiohttp.BasicAuth(self.shop_id, self.api_key)
        
        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    f"{self.base_url}/payments",
                    json=payment_data,
                    headers=headers,
                    auth=auth
                ) as response:
                    self.logger.info(f"[TRIAL] YooKassa response status: {response.status}")
                    if response.status == 200:
                        payment_info = await response.json()
                        self.logger.info(f"[TRIAL] YooKassa response: {payment_info}")
                        
                        # Сохраняем информацию о платеже в БД
                        self.db.add_payment(
                            payment_info["id"],
                            user_id,
                            1.0,
                            "RUB",
                            payment_info["status"],
                            False,
                            "Пробная подписка на 3 дня"
                        )
                        
                        return payment_info
                    else:
                        error_data = await response.json()
                        self.logger.error(f"Error creating trial payment: {error_data}")
                        return None
        except Exception as e:
            self.logger.error(f"Exception in create_trial_payment: {e}")
            return None
    
    async def create_regular_payment(self, user_id: int) -> Optional[Dict[str, Any]]:
        """
        Создание регулярного платежа на 250 рублей для подключения премиум на 30 дней
        
        :param user_id: ID пользователя в Telegram
        :return: Данные о созданном платеже или None в случае ошибки
        """
        # Получаем данные о пользователе
        user = self.db.get_user(user_id)
        if not user:
            self.logger.error(f"User {user_id} not found in database")
            return None
        
        # Идентификатор платежа
        payment_id = f"regular_{user_id}_{uuid.uuid4()}"
        
        # Данные для запроса на создание платежа
        payment_data = {
            "amount": {
                "value": "250.00",
                "currency": "RUB"
            },
            "capture": True,
            "confirmation": {
                "type": "redirect",
                "return_url": self.return_url
            },
            "description": f"Премиум подписка на 30 дней для пользователя {user['username'] or user['first_name'] or user_id}",
            "metadata": {
                "user_id": user_id,
                "payment_type": "regular"
            },
            "save_payment_method": True,
            "merchant_customer_id": str(user_id),
            "receipt": {
                "customer": {
                    "email": "user@example.com"
                },
                "items": [
                    {
                        "description": "Премиум подписка на 30 дней",
                        "quantity": 1.0,
                        "amount": {
                            "value": "250.00",
                            "currency": "RUB"
                        },
                        "vat_code": 1,
                        "payment_mode": "full_prepayment",
                        "payment_subject": "service"
                    }
                ]
            }
        }
        
        # Выполняем запрос к API ЮКассы
        headers = {
            "Content-Type": "application/json",
            "Idempotence-Key": secrets.token_hex(16)
        }
        auth = aiohttp.BasicAuth(self.shop_id, self.api_key)
        
        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    f"{self.base_url}/payments",
                    json=payment_data,
                    headers=headers,
                    auth=auth
                ) as response:
                    if response.status == 200:
                        payment_info = await response.json()
                        
                        # Сохраняем информацию о платеже в БД
                        self.db.add_payment(
                            payment_info["id"],
                            user_id,
                            250.0,
                            "RUB",
                            payment_info["status"],
                            False,
                            "Премиум подписка на 30 дней"
                        )
                        
                        return payment_info
                    else:
                        error_data = await response.json()
                        self.logger.error(f"Error creating regular payment: {error_data}")
                        return None
        except Exception as e:
            self.logger.error(f"Exception in create_regular_payment: {e}")
            return None
    
    async def create_recurring_payment(self, user_id: int, payment_method_id: str) -> Optional[Dict[str, Any]]:
        """
        Создание рекуррентного платежа для продления премиум подписки
        
        :param user_id: ID пользователя в Telegram
        :param payment_method_id: ID сохраненного метода оплаты
        :return: Данные о созданном платеже или None в случае ошибки
        """
        # Получаем данные о пользователе
        user = self.db.get_user(user_id)
        if not user:
            self.logger.error(f"User {user_id} not found in database")
            return None
        
        # Идентификатор платежа
        payment_id = f"recurring_{user_id}_{uuid.uuid4()}"
        
        # Данные для запроса на создание платежа
        payment_data = {
            "amount": {
                "value": "250.00",
                "currency": "RUB"
            },
            "capture": True,
            "description": f"Автоматическое продление премиум подписки на 30 дней для пользователя {user['username'] or user['first_name'] or user_id}",
            "metadata": {
                "user_id": user_id,
                "payment_type": "recurring"
            },
            "payment_method_id": payment_method_id,
            "receipt": {
                "customer": {
                    "email": "user@example.com"
                },
                "items": [
                    {
                        "description": "Премиум подписка на 30 дней",
                        "quantity": 1.0,
                        "amount": {
                            "value": "250.00",
                            "currency": "RUB"
                        },
                        "vat_code": 1,
                        "payment_mode": "full_prepayment",
                        "payment_subject": "service"
                    }
                ]
            }
        }
        
        # Выполняем запрос к API ЮКассы
        headers = {
            "Content-Type": "application/json",
            "Idempotence-Key": secrets.token_hex(16)
        }
        auth = aiohttp.BasicAuth(self.shop_id, self.api_key)
        
        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    f"{self.base_url}/payments",
                    json=payment_data,
                    headers=headers,
                    auth=auth
                ) as response:
                    if response.status == 200:
                        payment_info = await response.json()
                        
                        # Сохраняем информацию о платеже в БД
                        self.db.add_payment(
                            payment_info["id"],
                            user_id,
                            250.0,
                            "RUB",
                            payment_info["status"],
                            True,
                            "Автоматическое продление премиум подписки на 30 дней",
                            payment_method_id
                        )
                        
                        # Если платеж успешен, обновляем статус премиум подписки
                        if payment_info["status"] == "succeeded":
                            self.db.set_premium_status(user_id, True, 30)
                        
                        return payment_info
                    else:
                        error_data = await response.json()
                        self.logger.error(f"Error creating recurring payment: {error_data}")
                        return None
        except Exception as e:
            self.logger.error(f"Exception in create_recurring_payment: {e}")
            return None
    
    async def check_payment_status(self, payment_id: str) -> Optional[Dict[str, Any]]:
        """
        Проверка статуса платежа в ЮКассе
        
        :param payment_id: ID платежа
        :return: Данные о платеже или None в случае ошибки
        """
        auth = aiohttp.BasicAuth(self.shop_id, self.api_key)
        
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    f"{self.base_url}/payments/{payment_id}",
                    auth=auth
                ) as response:
                    if response.status == 200:
                        payment_info = await response.json()
                        return payment_info
                    else:
                        error_data = await response.json()
                        self.logger.error(f"Error checking payment status: {error_data}")
                        return None
        except Exception as e:
            self.logger.error(f"Exception in check_payment_status: {e}")
            return None
    
    async def cancel_subscription(self, user_id: int) -> Tuple[bool, str]:
        """
        Отмена подписки пользователя путем удаления его сохраненного метода оплаты
        
        :param user_id: ID пользователя в Telegram
        :return: Кортеж из флага успеха и сообщения
        """
        # Получаем данные о пользователе
        user = self.db.get_user(user_id)
        if not user:
            return False, "Пользователь не найден в базе данных"
        
        # Проверяем, есть ли у пользователя сохраненный метод оплаты
        payment_method_id = user.get("payment_method_id")
        
        if not payment_method_id:
            return False, "У вас нет активной подписки для отмены"
        
        try:
            # Удаляем метод оплаты из БД
            self.db.save_payment_method(user_id, None)
            
            # Обновляем статус премиум подписки (сохраняем текущую подписку до её окончания)
            # Для полной отмены можно использовать: self.db.set_premium_status(user_id, False, 0)
            
            return True, "Ваша подписка успешно отменена. Текущий премиум-период будет действовать до окончания срока, автоматическое продление отключено."
            
        except Exception as e:
            self.logger.error(f"Exception in cancel_subscription: {e}")
            return False, "Произошла ошибка при отмене подписки. Пожалуйста, попробуйте позже."
    
    async def process_payment_notification(self, notification_data: Dict[str, Any]) -> Tuple[bool, Optional[Dict[str, Any]]]:
        """
        Обработка уведомления о платеже от ЮКассы
        
        :param notification_data: Данные уведомления
        :return: Кортеж из флага успеха и данных о пользователе
        """
        try:
            event = notification_data.get("event")
            payment = notification_data.get("object")
            
            if not event or not payment or event not in ["payment.waiting_for_capture", "payment.succeeded", "payment.canceled"]:
                self.logger.error(f"Invalid notification data: {notification_data}")
                return False, None
            
            payment_id = payment.get("id")
            if not payment_id:
                self.logger.error("Payment ID not found in notification")
                return False, None
            
            # Получаем данные о платеже из БД
            payment_info = self.db.get_payment(payment_id)
            
            # Если платеж не найден в БД, проверяем метаданные
            if not payment_info:
                metadata = payment.get("metadata", {})
                user_id = metadata.get("user_id")
                
                if not user_id:
                    self.logger.error(f"User ID not found in payment metadata: {payment}")
                    return False, None
                
                # Сохраняем информацию о платеже в БД
                payment_type = metadata.get("payment_type", "unknown")
                if payment_type == "trial":
                    amount = 1.0
                    description = "Пробная подписка на 3 дня"
                else:
                    amount = 250.0
                    description = "Премиум подписка на 30 дней"
                
                self.db.add_payment(
                    payment_id,
                    int(user_id),
                    amount,
                    payment.get("amount", {}).get("currency", "RUB"),
                    payment.get("status", "unknown"),
                    payment_type == "recurring",
                    description,
                    payment.get("payment_method", {}).get("id")
                )
                
                payment_info = {
                    "payment_id": payment_id,
                    "user_id": int(user_id),
                    "amount": amount,
                    "status": payment.get("status", "unknown"),
                    "is_recurring": payment_type == "recurring"
                }
            
            # Обновляем статус платежа в БД
            self.db.update_payment_status(payment_id, payment.get("status", "unknown"))
            
            user_id = payment_info["user_id"]
            user = self.db.get_user(user_id)
            
            if not user:
                self.logger.error(f"User {user_id} not found in database")
                return False, None
            
            # Если платеж успешен, обновляем статус премиум подписки
            if event == "payment.succeeded":
                payment_method = payment.get("payment_method", {})
                payment_method_id = payment_method.get("id")
                
                if payment_method.get("saved"):
                    # Сохраняем метод оплаты пользователя
                    self.db.save_payment_method(user_id, payment_method_id)
                
                # Определяем тип платежа и устанавливаем соответствующий статус
                metadata = payment.get("metadata", {})
                payment_type = metadata.get("payment_type", "unknown")
                
                if payment_type == "trial":
                    # Триальный платеж - 3 дня премиума и отметка об использовании триала
                    self.db.set_premium_status(user_id, True, 3)
                    self.db.set_trial_used(user_id, True)
                else:
                    # Обычный платеж - 30 дней премиума
                    self.db.set_premium_status(user_id, True, 30)
            
            return True, user
        except Exception as e:
            self.logger.error(f"Exception in process_payment_notification: {e}")
            return False, None
    
    async def create_payment_keyboard(self, payment_url: str) -> InlineKeyboardMarkup:
        """
        Создание клавиатуры с кнопкой оплаты
        
        :param payment_url: URL для перехода к оплате
        :return: Клавиатура с кнопкой оплаты и кнопкой отмены
        """
        keyboard = InlineKeyboardMarkup(
            inline_keyboard=[
                [InlineKeyboardButton(text="Оплатить", url=payment_url)],
                [InlineKeyboardButton(text="Отмена", callback_data="cancel_payment")],
            ]
        )
        return keyboard
    
    async def get_payment_status_message(self, payment_status: str) -> str:
        """
        Получение сообщения о статусе платежа
        
        :param payment_status: Статус платежа
        :return: Текст сообщения
        """
        status_messages = {
            "pending": "Платеж в обработке. Ожидаем подтверждение...",
            "waiting_for_capture": "Платеж авторизован. Ожидаем подтверждение...",
            "succeeded": "Платеж успешно выполнен! Премиум доступ активирован.",
            "canceled": "Платеж отменен."
        }
        
        return status_messages.get(payment_status, f"Статус платежа: {payment_status}")

    async def create_gift_payment(self, user_id: int, username: str, first_name: str, gift_code: str) -> Optional[Dict[str, Any]]:
        """
        Создание платежа на подарочную подписку (30 дней) с генерацией кода подарка
        """
        import uuid, secrets, aiohttp
        from datetime import datetime
        # Идентификатор платежа
        payment_id = f"gift_{user_id}_{uuid.uuid4()}"
        # Данные для запроса
        payment_data = {
            "amount": {"value": "250.00", "currency": "RUB"},
            "capture": True,
            "confirmation": {"type": "redirect", "return_url": self.return_url},
            "description": f"Подарочная подписка на 30 дней от пользователя {username or first_name or user_id}",
            "metadata": {"user_id": user_id, "payment_type": "gift", "gift_code": gift_code},
            "save_payment_method": False,
            "merchant_customer_id": str(user_id),
            "receipt": {
                "customer": {"email": "user@example.com"},
                "items": [
                    {
                        "description": "Подарочная подписка на 30 дней",
                        "quantity": 1.0,
                        "amount": {"value": "250.00", "currency": "RUB"},
                        "vat_code": 1,
                        "payment_mode": "full_prepayment",
                        "payment_subject": "service"
                    }
                ]
            }
        }
        headers = {"Content-Type": "application/json", "Idempotence-Key": secrets.token_hex(16)}
        auth = aiohttp.BasicAuth(self.shop_id, self.api_key)
        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    f"{self.base_url}/payments",
                    json=payment_data,
                    headers=headers,
                    auth=auth
                ) as response:
                    if response.status == 200:
                        payment_info = await response.json()
                        # Сохраняем код подарка в БД
                        self.db.add_gift_subscription(gift_code, user_id)
                        return payment_info
                    else:
                        error_data = await response.json()
                        self.logger.error(f"Error creating gift payment: {error_data}")
                        return None
        except Exception as e:
            self.logger.error(f"Exception in create_gift_payment: {e}")
            return None 
