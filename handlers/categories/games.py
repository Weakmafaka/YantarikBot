import os
from aiogram import Router
from aiogram.types import CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton, WebAppInfo
from aiogram.fsm.context import FSMContext
from utils.library import bot
import logging

router = Router()

GAME_URLS = [
    ("🍉 Fruit Ninja", os.getenv("GAME_FRUIT_NINJA_URL")),
    ("🏃 Subway Surfers", os.getenv("GAME_SUBWAY_SURFERS_URL")),
    ("🐼 Panda Bubbles", os.getenv("GAME_PANDA_BUBBLES_URL")),
    ("🏎️ Polytrack", os.getenv("GAME_POLYTRACK_URL")),
    ("🎨 Emoji Coloring", os.getenv("GAME_EMOJI_COLORING_URL")),
    ("🚗 Mr Racer", os.getenv("GAME_MR_RACER_URL")),
]

async def games(user_id: int, state: FSMContext, age_group: str, message_id_to_edit: int):
    """Отображает меню с кнопками для запуска игр Mini Apps."""
    
    text = "Выберите игру, в которую хотите сыграть:"
    
    # Создаем кнопки с Mini Apps из переменных окружения
    rows = []
    row = []
    for title, url in GAME_URLS:
        if not url:
            continue
        row.append(InlineKeyboardButton(text=title, web_app=WebAppInfo(url=url)))
        if len(row) == 2:
            rows.append(row)
            row = []
    if row:
        rows.append(row)

    rows.append([InlineKeyboardButton(text="Назад в меню ⬅️", callback_data="back_to_main")])
    games_keyboard = InlineKeyboardMarkup(inline_keyboard=rows)
    
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
