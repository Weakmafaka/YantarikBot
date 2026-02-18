from aiogram import Router, F
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.fsm.context import FSMContext
from datetime import datetime
from utils.library import bot
from aiogram.exceptions import TelegramBadRequest
from utils.logger import get_logger

logger = get_logger(__name__)

router = Router()

@router.callback_query(F.data == 'subscription')
async def subscription_handler(query: CallbackQuery, state: FSMContext):
    """Обработчик кнопки 'Моя подписка'"""
    try:
        # Импортируем db из main для проверки подписки
        from main import db
        
        # Проверяем, есть ли у пользователя премиум доступ
        user_id = query.from_user.id
        user = db.get_user(user_id)
        
        logger.info("subscription_check", 
            user_id=user_id,
            username=query.from_user.username,
            user_data=user
        )
        
        if not user:
            logger.warning("user_not_found", user_id=user_id)
            await query.answer("Не удалось найти информацию о пользователе.", show_alert=True)
            return
        
        is_premium = user.get("is_premium", False)
        trial_used = user.get("trial_used", False)
        payment_method_id = user.get("payment_method_id")
        premium_until = user.get("premium_until")
        
        if is_premium:
            # У пользователя уже есть премиум доступ - показываем информацию о подписке
            if premium_until:
                premium_until_date = datetime.strptime(premium_until, "%Y-%m-%d %H:%M:%S")
                premium_until_str = premium_until_date.strftime("%d.%m.%Y")
                days_left = max(0, (premium_until_date - datetime.now()).days)
                
                subscription_text = (
                    f"У вас активирована премиум подписка ✅\n\n"
                    f"Доступ к премиум разделу будет действовать до {premium_until_str}\n"
                    f"Осталось дней: {days_left}\n\n"
                )
                if payment_method_id:
                    subscription_text += (
                        f"По истечении срока действия подписки с вашей карты будет списано 250 рублей, "
                        f"и доступ автоматически продлится на 30 дней."
                    )
                else:
                    subscription_text += "Автопродление отключено."
            else:
                subscription_text = (
                    "У вас активирована постоянная премиум подписка ✅\n\n"
                    "Доступ к премиум разделу открыт навсегда."
                )
            
            buttons = []
            if payment_method_id and premium_until:
                buttons.append([InlineKeyboardButton(text="Отменить автопродление 🚫", callback_data="cancel_auto_renewal")])
            buttons.append([InlineKeyboardButton(text="Назад ⬅️", callback_data="back_to_main")])
            send_buttons = InlineKeyboardMarkup(inline_keyboard=buttons)
        else:
            # У пользователя нет премиум доступа - предлагаем подписку
            if trial_used:
                subscription_text = (
                    "Премиум подписка открывает доступ к разделу 'Полезное' 🔓\n\n"
                    "Стоимость подписки: 250 рублей за 30 дней\n"
                    "После оплаты с вашей карты ежемесячно будет списываться 250 рублей "
                    "для автоматического продления подписки."
                )
            else:
                subscription_text = (
                    "Премиум подписка открывает доступ к разделу 'Полезное' 🔓\n\n"
                    "Попробуйте 3 дня за 1 рубль!\n"
                    "После окончания пробного периода с вашей карты будет списано 250 рублей, "
                    "и подписка продлится на 30 дней. Далее - автоматическое продление каждые 30 дней."
                )
            
            buttons = [
                [InlineKeyboardButton(text="Оформить подписку ✨", callback_data="create_payment")],
                [InlineKeyboardButton(text="Назад ⬅️", callback_data="back_to_main")]
            ]
            send_buttons = InlineKeyboardMarkup(inline_keyboard=buttons)
        
        # Редактируем сообщение
        try:
            await query.message.edit_text(
                text=subscription_text,
                reply_markup=send_buttons
            )
            await state.update_data(message_to_delete=query.message.message_id)
            logger.info("subscription_message_updated",
                user_id=user_id,
                message_id=query.message.message_id
            )
        except TelegramBadRequest as e:
            logger.warning("edit_message_failed",
                user_id=user_id,
                error=str(e),
                message_id=query.message.message_id
            )
            # Если не вышло отредактировать, удаляем старое и отправляем новое
            try:
                await bot.delete_message(chat_id=query.message.chat.id, message_id=query.message.message_id)
            except Exception as del_err:
                logger.warning("delete_message_failed",
                    user_id=user_id,
                    message_id=query.message.message_id,
                    error=str(del_err)
                )
            new_message = await bot.send_message(
                chat_id=query.from_user.id,
                text=subscription_text,
                reply_markup=send_buttons
            )
            await state.update_data(message_to_delete=new_message.message_id)
            logger.info("new_subscription_message_sent",
                user_id=user_id,
                new_message_id=new_message.message_id
            )
    except Exception as e:
        logger.error("subscription_handler_error",
            user_id=query.from_user.id,
            error=str(e),
            error_type=type(e).__name__
        )
        await query.answer("Произошла ошибка. Попробуйте позже.", show_alert=True)


@router.callback_query(F.data == "create_payment")
async def create_payment_handler(query: CallbackQuery, state: FSMContext):
    user_id = query.from_user.id
    username = query.from_user.username
    first_name = query.from_user.first_name
    
    # Импортируем payment_handler и db из main
    from main import payment_handler, db
    
    # Редактируем сообщение, показывая статус подготовки
    try:
        loading_message = await query.message.edit_text(
            text="Подготавливаем платеж... ⏳",
            reply_markup=None # Убираем кнопки на время загрузки
        )
    except TelegramBadRequest as e:
        logging.warning(f"Не удалось отредактировать на 'Подготавливаем платеж': {e}")
        await bot.delete_message(chat_id=query.message.chat.id, message_id=query.message.message_id)
        loading_message = await bot.send_message(
            chat_id=user_id,
            text="Подготавливаем платеж... ⏳"
        )
    
    loading_message_id = loading_message.message_id
    
    # Определяем тип платежа (пробный или обычный) в зависимости от того,
    # использовал ли пользователь уже пробный период
    user = db.get_user(user_id)
    is_trial = not (user and user["trial_used"])
    
    if is_trial:
        payment_info = await payment_handler.create_trial_payment(user_id, username, first_name)
    else:
        payment_info = await payment_handler.create_regular_payment(user_id)
    
    if not payment_info:
        # Ошибка при создании платежа
        error_message = (
            "К сожалению, не удалось создать платеж. Пожалуйста, попробуйте позже или "
            "обратитесь в техническую поддержку."
        )
        buttons = [[InlineKeyboardButton(text="Назад ⬅️", callback_data="back_to_main")]]
        error_keyboard = InlineKeyboardMarkup(inline_keyboard=buttons)
        
        try:
            await bot.edit_message_text(
                chat_id=user_id,
                message_id=loading_message_id,
                text=error_message,
                reply_markup=error_keyboard
            )
            await state.update_data(message_to_delete=loading_message_id)
        except Exception as edit_err:
            logging.error(f"Ошибка при редактировании на сообщение об ошибке платежа: {edit_err}")
            await bot.send_message(chat_id=user_id, text=error_message, reply_markup=error_keyboard)
            await state.update_data(message_to_delete=None) # Не знаем ID нового сообщения
        return
    
    # Получаем URL для оплаты
    confirmation = payment_info.get("confirmation", {})
    payment_url = confirmation.get("confirmation_url")
    
    if not payment_url:
        # Ошибка при получении ссылки для оплаты
        error_message = (
            "К сожалению, не удалось получить ссылку для оплаты. Пожалуйста, попробуйте позже или "
            "обратитесь в техническую поддержку."
        )
        
        buttons = [[InlineKeyboardButton(text="Назад ⬅️", callback_data="back_to_main")]]
        error_keyboard = InlineKeyboardMarkup(inline_keyboard=buttons)
        
        try:
            await bot.edit_message_text(
                chat_id=user_id,
                message_id=loading_message_id,
                text=error_message,
                reply_markup=error_keyboard
            )
            await state.update_data(message_to_delete=loading_message_id)
        except Exception as edit_err:
            logging.error(f"Ошибка при редактировании на сообщение об ошибке URL: {edit_err}")
            await bot.send_message(chat_id=user_id, text=error_message, reply_markup=error_keyboard)
            await state.update_data(message_to_delete=None)
        return
    
    # Создаем клавиатуру с кнопкой оплаты
    payment_keyboard = await payment_handler.create_payment_keyboard(payment_url)
    
    # Определяем текст сообщения в зависимости от типа платежа
    if is_trial:
        payment_message = (
            "Для оформления пробной подписки нажмите кнопку 'Оплатить' ниже.\n\n"
            "Стоимость: 1 рубль за 3 дня пробного периода.\n"
            "После оплаты вам будет доступен раздел 'Полезное'.\n\n"
            "По истечении 3 дней с вашей карты будет списано 250 рублей "
            "для продления подписки на 30 дней.\n\n"
            "Нажимая кнопку, вы соглашаетесь с автоматическим списанием средств."
        )
    else:
        payment_message = (
            "Для оформления подписки нажмите кнопку 'Оплатить' ниже.\n\n"
            "Стоимость: 250 рублей за 30 дней.\n"
            "После оплаты вам будет доступен раздел 'Полезное'.\n\n"
            "Нажимая кнопку, вы соглашаетесь с автоматическим списанием средств "
            "каждые 30 дней для продления подписки."
        )
    
    # Редактируем сообщение с кнопкой оплаты
    try:
        await bot.edit_message_text(
            chat_id=user_id,
            message_id=loading_message_id,
            text=payment_message,
            reply_markup=payment_keyboard
        )
        await state.update_data(message_to_delete=loading_message_id)
    except Exception as edit_err:
        logging.error(f"Ошибка при редактировании на сообщение об оплате: {edit_err}")
        # Если редактирование не удалось, просто отправим новое
        try:
            await bot.delete_message(chat_id=user_id, message_id=loading_message_id)
        except Exception:
            pass
        new_msg = await bot.send_message(
            chat_id=user_id,
            text=payment_message,
            reply_markup=payment_keyboard
        )
        await state.update_data(message_to_delete=new_msg.message_id)
    
    # Сохраняем ID платежа в состоянии пользователя для дальнейшего отслеживания
    await state.update_data(payment_id=payment_info["id"])


@router.callback_query(F.data == "cancel_payment")
async def cancel_payment_handler(query: CallbackQuery, state: FSMContext):
    # Редактируем сообщение с кнопкой оплаты
    try:
        await query.message.edit_text(
            text="Платеж отменен. Вы можете оформить подписку позже.",
            reply_markup=None # Убираем кнопки
        )
        # Добавляем кнопку назад через отдельное сообщение или редактируем еще раз?
        # Лучше сразу вернуть в главное меню
    except TelegramBadRequest as e:
        logging.warning(f"Не удалось отредактировать сообщение cancel_payment: {e}")
        await bot.delete_message(chat_id=query.message.chat.id, message_id=query.message.message_id)
        await bot.send_message(
            chat_id=query.from_user.id,
            text="Платеж отменен. Вы можете оформить подписку позже."
        )
    except Exception as e:
        logging.error(f"Ошибка в cancel_payment_handler: {e}")
        # Все равно пытаемся вернуть в главное меню
        
    # Возвращаемся в главное меню
    from main import db
    age_group = db.get_user_age(query.from_user.id)
    from handlers.common import show_main_menu
    # Отправляем новое сообщение с главным меню, так как текущее изменено
    await show_main_menu(query.from_user.id, age_group, state, message_to_edit_id=None)


@router.callback_query(F.data == "cancel_auto_renewal")
async def cancel_auto_renewal_handler(query: CallbackQuery, state: FSMContext):
    user_id = query.from_user.id
    
    # Импортируем payment_handler из main
    from main import payment_handler
    
    # Используем метод отмены подписки
    success, message = await payment_handler.cancel_subscription(user_id)
    
    # Редактируем текущее сообщение, показывая результат
    try:
        await query.message.edit_text(
            text=message,
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="В главное меню ⬅️", callback_data="back_to_main")]
            ])
        )
        await state.update_data(message_to_delete=query.message.message_id)
    except TelegramBadRequest as e:
        logging.warning(f"Не удалось отредактировать сообщение cancel_auto_renewal: {e}")
        await bot.delete_message(chat_id=query.message.chat.id, message_id=query.message.message_id)
        new_msg = await bot.send_message(
            chat_id=user_id,
            text=message,
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="В главное меню ⬅️", callback_data="back_to_main")]
            ])
        )
        await state.update_data(message_to_delete=new_msg.message_id)
    except Exception as e:
        logging.error(f"Ошибка в cancel_auto_renewal_handler: {e}")
    # Возвращаемся в главное меню по кнопке
    # from handlers.common import command_start
    # await command_start(query.message, state)


@router.message(F.text == "Моя подписка")
async def my_subscription_handler_text(msg: Message, state: FSMContext):
    """Обработчик текстовой команды 'Моя подписка' (если осталась в клавиатуре)"""
    # Просто перенаправляем на callback-обработчик 'subscription'
    # Создаем фейковый CallbackQuery
    from aiogram.types.user import User
    from aiogram.types.chat import Chat
    
    fake_user = User(id=msg.from_user.id, is_bot=False, first_name=msg.from_user.first_name)
    fake_chat = Chat(id=msg.chat.id, type='private') # или msg.chat.type
    
    # Отправляем временное сообщение, чтобы было что редактировать
    temp_msg = await msg.answer("Загрузка информации о подписке...")
    await bot.delete_message(chat_id=msg.chat.id, message_id=msg.message_id) # Удаляем исходное сообщение
    
    fake_query = CallbackQuery(
        id=str(msg.message_id), # Используем ID сообщения как ID запроса
        from_user=fake_user,
        chat_instance="fake_instance",
        message=temp_msg, # Передаем временное сообщение
        data='subscription'
    )
    await subscription_handler(fake_query, state)


# Остальные хендлеры (ask_cancel_subscription, confirm_cancel_subscription) уже используют edit_text
@router.callback_query(F.data == "cancel_subscription")
async def ask_cancel_subscription(query: CallbackQuery, state: FSMContext):
    buttons = [
        [InlineKeyboardButton(text="Да, отменить 🚫", callback_data="confirm_cancel_subscription")],
        [InlineKeyboardButton(text="Нет, оставить ✅", callback_data="subscription")] # Возвращаем на просмотр подписки
    ]
    kb = InlineKeyboardMarkup(inline_keyboard=buttons)
    try:
        await query.message.edit_text(
            "Вы уверены, что хотите отменить автопродление подписки?",
            reply_markup=kb
        )
    except Exception as e:
        logging.error(f"Ошибка в ask_cancel_subscription: {e}")


@router.callback_query(F.data == "confirm_cancel_subscription")
async def confirm_cancel_subscription(query: CallbackQuery, state: FSMContext):
    user_id = query.from_user.id
    
    # Импортируем payment_handler из main
    from main import payment_handler, db
    
    success, message = await payment_handler.cancel_subscription(user_id)
    
    # Обновляем сообщение с результатом
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Понятно", callback_data="subscription")] # Возврат к информации о подписке
    ])
    
    try:
        await query.message.edit_text(message, reply_markup=kb)
        await state.update_data(message_to_delete=query.message.message_id)
    except Exception as e:
        logging.error(f"Ошибка в confirm_cancel_subscription: {e}")
        # Если не вышло, просто отправляем результат
        await bot.send_message(user_id, message, reply_markup=kb) 