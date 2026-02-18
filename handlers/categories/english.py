import os
from aiogram import Router, F
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, WebAppInfo, CallbackQuery, InputMediaPhoto
from aiogram.fsm.context import FSMContext

from utils.library import bot
import logging

router = Router()

GAME_URLS = {
    "0": os.getenv("EN_GAME_0_URL"),
    "1": os.getenv("EN_GAME_1_URL"),
    "2": os.getenv("EN_GAME_2_URL"),
    "3": os.getenv("EN_GAME_3_URL"),
    "4": os.getenv("EN_GAME_4_URL"),
    "5": os.getenv("EN_GAME_5_URL"),
    "6": os.getenv("EN_GAME_6_URL"),
}

VIDEO_URLS = {
    "0": os.getenv("EN_VIDEO_0_URL"),
    "1": os.getenv("EN_VIDEO_1_URL"),
    "2": os.getenv("EN_VIDEO_2_URL"),
    "3": os.getenv("EN_VIDEO_3_URL"),
    "4": os.getenv("EN_VIDEO_4_URL"),
    "5": os.getenv("EN_VIDEO_5_URL"),
    "6": os.getenv("EN_VIDEO_6_URL"),
}

PHOTO_URLS = {
    "0": os.getenv("EN_PHOTO_0_URL"),
    "1": os.getenv("EN_PHOTO_1_URL"),
    "2": os.getenv("EN_PHOTO_2_URL"),
    "3": os.getenv("EN_PHOTO_3_URL"),
    "4": os.getenv("EN_PHOTO_4_URL"),
    "5": os.getenv("EN_PHOTO_5_URL"),
    "6": os.getenv("EN_PHOTO_6_URL"),
}


async def english(user_id: int, state: FSMContext, age_group: str, message_id_to_edit: int):
    """Отображает меню с кнопками для запуска игр Mini Apps english."""

    text = "Выберите игру, в которую хотите сыграть:"

    # Создаем кнопки с Mini Apps
    games_keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [
             InlineKeyboardButton(text="🔤Алфавит",
                                  callback_data="game_english_0"),
            InlineKeyboardButton(text="🔢Цифры",
                                 callback_data="game_english_1")
        ],
        [
            InlineKeyboardButton(text="👋 Приветствие",
                                 callback_data="game_english_2"),
            InlineKeyboardButton(text="🧍Части тела",
                                 callback_data="game_english_3")
        ],
        [
            InlineKeyboardButton(text="🎨Цвета",
                                 callback_data="game_english_4"),
            InlineKeyboardButton(text="🌞Времена года",
                                 callback_data="game_english_5")],
            # [InlineKeyboardButton(text="📚Грамматика",
            #                       callback_data="game_english_6"),
        [
                InlineKeyboardButton(text="Назад в меню ⬅️", callback_data="back_to_main")
        ]
    ])

    try:
        await bot.edit_message_text(
            chat_id=user_id,
            message_id=message_id_to_edit,
            text=text,
            reply_markup=games_keyboard
        )
        # Сохраняем ID сообщения, чтобы его можно было удалить/изменить при возврате в главное меню
        await state.update_data(message_to_delete=message_id_to_edit)
    except Exception as e:
        logging.error(f"Ошибка при редактировании сообщения в games: {e}")
        # В случае ошибки отправляем новое сообщение
        try:
            await bot.delete_message(chat_id=user_id, message_id=message_id_to_edit)
        except Exception as del_e:
            logging.warning(f"Не удалось удалить старое сообщение в games: {del_e}")
        new_msg = await bot.send_message(user_id, text, reply_markup=games_keyboard)
        await state.update_data(message_to_delete=new_msg.message_id)


@router.callback_query(lambda c: c.data.startswith('game_english'))
async def test_english(query: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    message_edit = data.get('message_to_delete')

    _, index_str, type_game = query.data.split("_")

    game_url = None
    text = None
    photo = None
    video_url = None

    if type_game == "0":
        game_url = GAME_URLS.get(type_game)
        video_url = VIDEO_URLS.get(type_game)
        text = "В данном уроке ваш ребенок выучит английский алфавит 🎉"
        photo = PHOTO_URLS.get(type_game)
    elif type_game == "1":
        game_url = GAME_URLS.get(type_game)
        video_url = VIDEO_URLS.get(type_game)
        text = "В данном уроке ваш ребенок выучит произношение цифр на английском языке 🎉"
        photo = PHOTO_URLS.get(type_game)
    elif type_game == "2":
        game_url = GAME_URLS.get(type_game)
        video_url = VIDEO_URLS.get(type_game)
        text = "В данном уроке ваш ребенок научится различным приветствиям на английском языке 🎉"
        photo = PHOTO_URLS.get(type_game)
    elif type_game == "3":
        game_url = GAME_URLS.get(type_game)
        video_url = VIDEO_URLS.get(type_game)
        text = "В данном уроке ваш ребенок научится называть разные части тела на английском языке 🎉"
        photo = PHOTO_URLS.get(type_game)
    elif type_game == "4":
        game_url = GAME_URLS.get(type_game)
        video_url = VIDEO_URLS.get(type_game)
        text = "В данном уроке ваш ребенок выучит различные цвета на английском языке 🎉"
        photo = PHOTO_URLS.get(type_game)
    elif type_game == "5":
        game_url = GAME_URLS.get(type_game)
        video_url = VIDEO_URLS.get(type_game)
        text = "В данном уроке ваш ребенок научится произносить времена года на английском языке 🎉"
        photo = PHOTO_URLS.get(type_game)

    elif type_game == "6":
        game_url = GAME_URLS.get(type_game)
        video_url = VIDEO_URLS.get(type_game)
        text = "В данном уроке ваш ребенок научится произносить времена года на английском языке 🎉"
        photo = PHOTO_URLS.get(type_game)

    if not game_url or not video_url or not photo:
        await bot.send_message(query.from_user.id, "Контент временно недоступен. Попробуйте позже.")
        return

    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="Обучение 📚",
                                 web_app=WebAppInfo(url=video_url))
        ],
        [
            InlineKeyboardButton(text="Практическая 🏁",
                                 web_app=WebAppInfo(url=game_url))
        ],
        [
            InlineKeyboardButton(text="Назад в меню ⬅️", callback_data="back_to_eng")
        ]
    ])

    try:
        # Пытаемся редактировать существующее сообщение
        await bot.edit_message_media(
            chat_id=query.from_user.id,
            message_id=message_edit,
            media=InputMediaPhoto(
                media=photo,
                caption=text
            ),
            reply_markup=keyboard
        )
    except Exception as e:
        # Если не получилось редактировать (например, сообщение не содержит медиа)
        try:
            await bot.edit_message_caption(
                chat_id=query.from_user.id,
                message_id=message_edit,
                caption=text,
                reply_markup=keyboard
            )
        except Exception as e:
            # Если совсем не получается редактировать, отправляем новое сообщение
            print(f"Ошибка при редактировании: {e}")
            msg = await bot.send_photo(
                chat_id=query.from_user.id,
                photo=photo,
                caption=text,
                reply_markup=keyboard
            )
            await state.update_data(message_to_delete=msg.message_id)


@router.callback_query(F.data == "back_to_eng")
async def back_to_eng(query : CallbackQuery, state : FSMContext):
    age = "None"
    message_id_to_edit = query.message.message_id
    await english(query.from_user.id, state, age, message_id_to_edit)
