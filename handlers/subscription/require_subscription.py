from aiogram import Router, F
from aiogram.types import CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.fsm.context import FSMContext
from utils.library import bot
from aiogram.exceptions import TelegramBadRequest

router = Router()


@router.callback_query(F.data == "require_subscription")
async def require_subscription_handler(query: CallbackQuery, state: FSMContext):
    await query.answer() # Отвечаем на callback query
    # Текст и кнопка для предложения подписки
    subscription_text = (
        "Эта категория доступна только по премиум подписке 🔐\n\n"
        "Оформите подписку, чтобы получить доступ ко всем полезным материалам и заданиям для вашего ребенка."
    )
    subscription_keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Оформить подписку ✨", callback_data="subscription")],
        [InlineKeyboardButton(text="Назад ⬅️", callback_data="menu_useful")] # Кнопка назад к "Полезное"
    ])
    try:
        # Пытаемся отредактировать существующее сообщение
        await query.message.edit_text(
            text=subscription_text,
            reply_markup=subscription_keyboard
        )
    except TelegramBadRequest:
        # Если не удалось (например, текст тот же), отправляем новое
        await bot.send_message(
            chat_id=query.from_user.id,
            text=subscription_text,
            reply_markup=subscription_keyboard
        )
    # Сохраняем ID сообщения для возможного удаления, если нужно
    await state.update_data(message_to_delete=query.message.message_id if query.message else None)