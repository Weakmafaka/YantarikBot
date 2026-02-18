from aiogram import Router
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.fsm.context import FSMContext
from utils.library import bot
from utils.logger import get_logger

logger = get_logger(__name__)
router = Router()


async def subscription_menu(user_id: int, state: FSMContext, age_group: str, message_id_to_edit: int):
    text = "Здесь ты можешь легко проверить свою подписку или порадовать близкого — подарить ему доступ к 'Янтарику'."
    button_sub = [
        [InlineKeyboardButton(text="Подарить подписку 🎁", callback_data="gift_subscription")],
        [InlineKeyboardButton(text="Моя подписка 💳", callback_data="subscription")],
        [InlineKeyboardButton(text="Назад в меню ⬅️", callback_data="back_to_main")]
    ]
    send_button = InlineKeyboardMarkup(inline_keyboard=button_sub)

    await bot.edit_message_text(chat_id=user_id,
                                message_id=message_id_to_edit,
                                text=text,
                                reply_markup=send_button,)

