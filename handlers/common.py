from aiogram import Router, F
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton, WebAppInfo
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext

from utils.library import bot
from aiogram.exceptions import TelegramBadRequest
import logging

router = Router()


@router.message(Command("start"))
async def command_start(msg: Message, state: FSMContext):
    # Обработка deep-link для подарка
    if msg.text and msg.text.startswith("/start gift_"):
        from database.database import db
        parts = msg.text.split()
        payload = parts[1] if len(parts) > 1 else msg.text[len("/start "):]
        gift_code = payload[len("gift_"):] if payload.startswith("gift_") else None
        if not gift_code:
            await msg.answer("❗️Некорректная ссылка подарка.")
            logging.warning(f"Некорректная ссылка подарка: {msg.text}")
            return
        success = db.redeem_gift_subscription(gift_code, msg.from_user.id)
        logging.info(f"redeem_gift_subscription({gift_code}, {msg.from_user.id}) => {success}")
        if not success:
            await msg.answer("❗️Ссылка недействительна или уже использована.")
            logging.warning(f"Подарок не активирован: {gift_code} для {msg.from_user.id}")
            return
        db.set_premium_status(msg.from_user.id, True, 30)
        logging.info(f"set_premium_status({msg.from_user.id}, True, 30)")
        await msg.answer("🎉 Вам подарили подписку на 30 дней! Пользуйтесь на здоровье! 🥰")
        # Показываем главное меню
        age_group = db.get_user_age(msg.from_user.id) or "0-3"
        try:
            await show_main_menu(msg.from_user.id, age_group, state)
        except Exception as e:
            logging.warning(f"Ошибка при открытии главного меню после подарка: {e}")
        return

    data = await state.get_data()
    message_to_delete = data.get('message_to_delete')

    # Добавляем пользователя в базу данных, если он новый
    from main import db  # Импортируем db из main
    db.add_user(
        user_id=msg.from_user.id,
        username=msg.from_user.username,
        first_name=msg.from_user.first_name,
    )

    # Обновляем время последней активности
    db.update_user_activity(msg.from_user.id)

    # Проверяем, является ли пользователь администратором
    is_admin = db.is_admin(msg.from_user.id)

    # Проверяем, выбирал ли пользователь возраст ранее
    age_group = db.get_user_age(msg.from_user.id)

    if age_group:
        # Если возраст уже выбран, сразу переходим к главному меню
        await show_main_menu(msg.from_user.id, age_group, state, message_to_edit_id=message_to_delete)
        return

    # Приветственное сообщение с анимацией
    welcome_message = (
        f"Привет, {msg.from_user.first_name}! 👋\n\n"
        f"Меня зовут Янтарик, и я твой волшебный помощник! 🧙‍♂️\n\n"
        f"Здесь ты найдешь множество интересного контента:\n"
        f"• Сказки 🧙‍♀\n"
        f"• Мультики 🧜\n"
        f"• Музыка 🎤\n"
        f"• Игры 🎮\n"
        f"• Полезные материалы 🔓\n\n"
        f"AI-Помощник 🧠– Умный помощник, который подскажет:"
        f"   • чем заняться с ребёнком.\n"
        f"   • как развивать малыша.\n"
        f"   • какие игрушки или книги подходят сейчас.\n"
        f"Афиша детских событий 🎟– Будьте в курсе лучших мероприятий: спектакли, мастер-классы, семейные праздники, выставки. Всё — рядом с вами и по возрасту ребёнка."
        f"Чтобы начать, выбери возрастную группу твоего ребенка:"
    )
    # welcome_message = (
    #     f"Привет, {query.from_user.first_name}! 👋\n\n"
    #     f"Меня зовут Янтарик, и я твой волшебный помощник! 🧙‍♂️\n\n"
    #     f"Здесь ты найдешь множество интересного контента:\n"
    #     f"🎮 Развивающие игры – Играем, развиваем логику, учим цвета, формы, счёт и не только!\n"
    #     f"📖 Сказки и мультики – Авторские и классические сказки, добрые мультфильмы.\n"
    #     f"🎵 Музыка и аудиокниги – Успокаивающие мелодии, обучающие песенки, музыка для игр и сна.\n"
    #     f"🔓 Полезные материалы – Рекомендации по уходу за ребенком, питание, развитие и многое другое!\n"
    #     f"🧠 AI-Помощник – Умный помощник, который подскажет:"
    #     f"   • чем заняться с ребёнком.\n"
    #     f"   • как развивать малыша.\n"
    #     f"   • какие игрушки или книги подходят сейчас.\n"
    #     f"Родители всегда знают, что делать — без бесконечных поисков в интернете.\n\n"
    #     f"🎟️ Афиша детских событий – Будьте в курсе лучших мероприятий: спектакли, мастер-классы, семейные праздники, выставки. Всё — рядом с вами и по возрасту ребёнка."
    #     f"Чтобы начать, выбери возрастную группу твоего ребенка:"
    # )
    # Создаем инлайн-кнопки для выбора возраста
    age_buttons = [
        [
            InlineKeyboardButton(text="0-3 года 👶", callback_data="select_age_0-3"),
            InlineKeyboardButton(text="4-6 лет 🧒", callback_data="select_age_4-6")
        ],
        [InlineKeyboardButton(text="7-10 лет 👦", callback_data="select_age_7-10")],
        [
            InlineKeyboardButton(text="Афиша 🎪",
                                 web_app=WebAppInfo(url="")),
            InlineKeyboardButton(text="Поддержка 🛟", callback_data="support")
        ]
    ]

    # Добавляем кнопку администратора, если пользователь - админ
    if is_admin:
        admin_button = [InlineKeyboardButton(text="Администратор 👑", callback_data="admin_panel")]
        age_buttons.append(admin_button)

    age_keyboard = InlineKeyboardMarkup(inline_keyboard=age_buttons)

    if message_to_delete:
        try:
            await bot.delete_message(chat_id=msg.from_user.id, message_id=message_to_delete)
        except Exception as e:
            logging.warning(f"Не удалось удалить старое сообщение: {e}")

    # Всегда отправляем анимацию с приветственным сообщением
    try:
        message_to_edit = await msg.answer_animation(
            animation="",
            caption=welcome_message,
            reply_markup=age_keyboard
        )
    except Exception as e:
        logging.error(f"Ошибка при отправке анимации: {e}")
        # В крайнем случае отправим обычное сообщение
        message_to_edit = await msg.answer(
            text=welcome_message,
            reply_markup=age_keyboard
        )

    # Сохраняем ID отправленного сообщения
    if message_to_edit:
        await state.update_data(message_to_delete=message_to_edit.message_id)
    else:
        await state.update_data(message_to_delete=None)


@router.callback_query(F.data.startswith('select_age_'))
async def handle_age_selection(query: CallbackQuery, state: FSMContext):
    """Обработка выбора возраста через инлайн-кнопки"""
    age_group = query.data.split('_')[2]  # select_age_0-3 -> 0-3
    
    # Сохраняем выбранный возраст в базе данных
    from main import db
    db.set_user_age(query.from_user.id, age_group)
    
    # Обновляем время последней активности
    db.update_user_activity(query.from_user.id)
    db.increment_age_selection(age_group)

    # Отображаем главное меню, редактируя текущее сообщение
    await show_main_menu(query.from_user.id,
                         age_group,
                         state,
                         message_to_edit_id=query.message.message_id)


async def show_main_menu(user_id: int, age_group: str, state: FSMContext, message_to_edit_id: int = None):
    """Показывает главное меню бота в зависимости от выбранного возраста"""
    from main import db
    # Формируем основное меню в зависимости от возраста
    is_premium = db.check_premium_status(user_id)
    if age_group in ["0-3"]:
        menu_buttons = [
            [
                InlineKeyboardButton(text="Мультики 🧜", callback_data="menu_cartoons"),
                InlineKeyboardButton(text="Музыка 🎶", callback_data="menu_music")
            ],
            [
                InlineKeyboardButton(text="Сказки 🧙‍♀", callback_data="menu_fairy_tales"),
                InlineKeyboardButton(text="Полезное 🔓", callback_data="menu_useful")
             ],
            [
                InlineKeyboardButton(text="AI Помощник 🤖",
                                     callback_data="ai_assistant" if is_premium else "require_subscription")
            ],
            [
                InlineKeyboardButton(text="Премиум подписка 🌟", callback_data="menu_subscription")
            ],
            [
                InlineKeyboardButton(text="Поддержка 🛟", callback_data="support"),
                InlineKeyboardButton(text="Сменить возраст 🔄", callback_data="change_age")
            ]
        ]

    elif age_group in ["4-6"]:
        menu_buttons = [
            [
                InlineKeyboardButton(text="Мультики 🧜", callback_data="menu_cartoons"),
                InlineKeyboardButton(text="Музыка 🎶", callback_data="menu_music")
            ],
            [
                InlineKeyboardButton(text="Сказки 🧙‍♀", callback_data="menu_fairy_tales"),
                InlineKeyboardButton(text="Игры 🎮", callback_data="menu_games")
            ],
            [
                InlineKeyboardButton(text="Полезное 🔓", callback_data="menu_useful")
            ],
            [
                InlineKeyboardButton(text="AI Помощник 🤖",
                                     callback_data="ai_assistant" if is_premium else "require_subscription")
            ],
            [
                InlineKeyboardButton(text="Премиум подписка 🌟", callback_data="menu_subscription")
            ],
            [
                InlineKeyboardButton(text="Поддержка 🛟", callback_data="support"),
                InlineKeyboardButton(text="Сменить возраст 🔄", callback_data="change_age")
            ]
        ]
    else:  # 7-10
        menu_buttons = [
            [
                InlineKeyboardButton(text="Мультики 🧜", callback_data="menu_cartoons"),
                InlineKeyboardButton(text="Игры 🎮", callback_data="menu_games")
            ],
            [
                InlineKeyboardButton(text="Английский 🇬🇧", callback_data="menu_english"),
                InlineKeyboardButton(text="Аудиокниги 🎧", callback_data="menu_books")
            ],

            [
                    InlineKeyboardButton(text="Полезное 🔓", callback_data="menu_useful")
            ],
            [
                InlineKeyboardButton(text="AI Помощник 🤖",
                                     callback_data="ai_assistant" if is_premium else "require_subscription")
            ],
            [
                InlineKeyboardButton(text="Премиум подписка 🌟", callback_data="menu_subscription")
            ],
            [
                InlineKeyboardButton(text="Поддержка 🛟", callback_data="support"),
                InlineKeyboardButton(text="Сменить возраст 🔄", callback_data="change_age")
            ]
        ]

    menu_keyboard = InlineKeyboardMarkup(inline_keyboard=menu_buttons)

    # Определяем текст приветствия в зависимости от возраста
    age_display = {
        "0-3": "0-3 года",
        "4-6": "4-6 лет",
        "7-10": "7-10 лет"
    }.get(age_group, age_group)

    message_text = (
        f"Добро пожаловать в главное меню! 🎯\n\n"
        f"Выбранный возраст: {age_display}\n\n"
        f"Выберите категорию, которая вас интересует:"
    )

    edited_message = None
    if message_to_edit_id:
        try:
            # Пытаемся отредактировать переданное сообщение
            edited_message = await bot.edit_message_text(
                chat_id=user_id,
                message_id=message_to_edit_id,
                text=message_text,
                reply_markup=menu_keyboard
            )
        except TelegramBadRequest as e:
            logging.warning(f"Не удалось отредактировать сообщение {message_to_edit_id}: {e}")
            # Если не удалось отредактировать, удаляем старое и отправляем новое
            try:
                await bot.delete_message(chat_id=user_id, message_id=message_to_edit_id)
            except Exception as del_err:
                 logging.warning(f"Не удалось удалить сообщение {message_to_edit_id}: {del_err}")
            edited_message = await bot.send_message(
                chat_id=user_id,
                text=message_text,
                reply_markup=menu_keyboard
            )
        except Exception as e:
            logging.error(f"Непредвиденная ошибка при редактировании сообщения {message_to_edit_id}: {e}")
            # Отправляем новое в случае другой ошибки
            edited_message = await bot.send_message(
                chat_id=user_id,
                text=message_text,
                reply_markup=menu_keyboard
            )
    else:
        # Если ID для редактирования не передан, отправляем новое сообщение
        edited_message = await bot.send_message(
            chat_id=user_id,
            text=message_text,
            reply_markup=menu_keyboard
        )

    # Сохраняем ID актуального сообщения для возможности редактирования в будущем
    if edited_message:
        await state.update_data(message_to_delete=edited_message.message_id)
    else: # На случай если отправка/редактирование не удалось
        await state.update_data(message_to_delete=None)


@router.callback_query(F.data == 'change_age')
async def change_age(query: CallbackQuery, state: FSMContext):
    from main import db
    is_admin = db.is_admin(query.from_user.id)

    age_buttons = [
        [
            InlineKeyboardButton(text="0-3 года 👶", callback_data="select_age_0-3"),
            InlineKeyboardButton(text="4-6 лет 🧒", callback_data="select_age_4-6")
        ],
        [InlineKeyboardButton(text="7-10 лет 👦", callback_data="select_age_7-10")],
        [
            InlineKeyboardButton(text="Афиша 🎪", web_app=WebAppInfo(url="")),
            InlineKeyboardButton(text="Поддержка 🛟", callback_data="support")
        ]
    ]

    if is_admin:
        admin_button = [InlineKeyboardButton(text="Администратор 👑", callback_data="admin_panel")]
        age_buttons.append(admin_button)

    age_keyboard = InlineKeyboardMarkup(inline_keyboard=age_buttons)

    welcome_message = (
        f"Привет, {query.from_user.first_name}! 👋\n\n"
        f"Меня зовут Янтарик, и я твой волшебный помощник! 🧙‍♂️\n\n"
        f"Здесь ты найдешь множество интересного контента:\n"
        f"• Сказки 🧙‍♀\n"
        f"• Мультики 🧜\n"
        f"• Музыка 🎤\n"
        f"• Игры 🎮\n"
        f"• Полезные материалы 🔓\n"
        f"• AI-Помощник 🤖\n\n"
        f"Афиша 🎪– Будьте в курсе лучших мероприятий: спектакли, мастер-классы, семейные праздники, выставки.\n\n"
        f"Чтобы начать, выбери возрастную группу твоего ребенка:"
    )

    try:
        # Удаляем старое сообщение
        await bot.delete_message(chat_id=query.message.chat.id, message_id=query.message.message_id)
    except Exception as e:
        logging.warning(f"Не удалось удалить сообщение: {e}")

    try:
        # Отправляем анимацию с сообщением
        new_message = await bot.send_animation(
            chat_id=query.from_user.id,
            animation="",
            caption=welcome_message,
            reply_markup=age_keyboard
        )
        await state.update_data(message_to_delete=new_message.message_id)
    except Exception as e:
        logging.error(f"Не удалось отправить анимацию при смене возраста: {e}")


@router.callback_query(F.data.startswith('menu_'))
async def handle_menu_selection(query: CallbackQuery, state: FSMContext):
    """Обработка выбора раздела в главном меню"""
    menu_type = query.data.split('_')[1]  # menu_cartoons -> cartoons
    message_id_to_edit = query.message.message_id # Сообщение, которое будем редактировать
    user_id = query.from_user.id
    
    # Получаем возраст пользователя из БД
    from main import db
    age_group = db.get_user_age(query.from_user.id)
    if not age_group:
         # Если возраст не найден в БД, отправляем на старт
         await command_start(query.message, state) # Используем message вместо query, т.к. command_start ожидает Message
         await query.answer() # Отвечаем на callback query
         return
         
    # Обновляем время последней активности
    db.update_user_activity(query.from_user.id)
    
    # Обновляем состояние, сохраняя возраст
    await state.update_data(type_age=age_group)
    
    # Передаем управление соответствующему хендлеру категории
    # Эти хендлеры теперь должны принимать message_id для редактирования
    if menu_type == "cartoons":
        from handlers.categories.cartoons import handle_cartoons
        await handle_cartoons(user_id, state, age_group, message_id_to_edit)
    
    elif menu_type == "music":
        from handlers.categories.music import send_music
        await send_music(user_id, state, age_group, message_id_to_edit)

    elif menu_type == "books":
        from handlers.categories.audio_book import send_book
        await send_book(user_id, state, age_group, message_id_to_edit)
    
    elif menu_type == "fairy":
        from handlers.categories.fairy_tales import send_fairy
        await send_fairy(user_id, state, age_group, message_id_to_edit)
    
    elif menu_type == "useful":
        from handlers.categories.useful import other_category
        await other_category(user_id, state, age_group, message_id_to_edit)
    
    elif menu_type == "games":
        from handlers.categories.games import games
        await games(user_id, state, age_group, message_id_to_edit)

    elif menu_type == "english":
        from handlers.categories.english import english
        await english(user_id, state, age_group, message_id_to_edit)

    elif menu_type == "subscription":
        from handlers.subscription.subscription_menu import subscription_menu
        await subscription_menu(user_id, state, age_group, message_id_to_edit)

    else:
        # На случай неизвестного callback_data
        # Отвечаем на callback query перед тем, как показать сообщение
        await query.answer() 
        await query.message.answer("Неизвестная команда") # Отправляем сообщение вместо alert