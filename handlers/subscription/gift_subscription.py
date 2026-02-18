from aiogram import Router, F
from aiogram.types import CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton, Message
from aiogram.fsm.context import FSMContext
from utils.library import bot
from database.database import db
import uuid
import logging

router = Router()

@router.callback_query(F.data == "gift_subscription")
async def gift_subscription_intro(query: CallbackQuery, state: FSMContext):
    text = (
        "🎁 Хотите сделать подарок?\n\n"
        "Нажмите на кнопку <b>«Оплатить подарок»</b> 👇, оплатите, получите ссылку, "
        "отправьте её другу — и он получит подписку на месяц! 🥳"
    )
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Оплатить подарок 🎁", callback_data="create_gift_payment")],
        [InlineKeyboardButton(text="Назад ⬅️", callback_data="back_to_main")]
    ])
    await query.message.edit_text(text=text, reply_markup=kb, parse_mode="HTML")

@router.callback_query(F.data == "create_gift_payment")
async def create_gift_payment_handler(query: CallbackQuery, state: FSMContext):
    from main import payment_handler
    user_id = query.from_user.id
    username = query.from_user.username
    first_name = query.from_user.first_name

    # Генерируем код подарка и сохраняем запись
    gift_code = uuid.uuid4().hex

    # Переходим к оплате
    try:
        loading = await query.message.edit_text(
            text="Подготавливаем подарочную подписку... ⏳🎁",
            reply_markup=None
        )
    except:
        loading = await query.message.answer("Подготавливаем подарочную подписку... ⏳🎁")

    payment_info = await payment_handler.create_gift_payment(user_id, username, first_name, gift_code)
    if not payment_info:
        await query.message.edit_text(
            "❌ Не удалось создать платеж. Попробуйте позже.",
            reply_markup=InlineKeyboardMarkup(
                inline_keyboard=[[InlineKeyboardButton(text="Назад ⬅️", callback_data="back_to_main")]]
            )
        )
        return

    payment_url = payment_info.get("confirmation", {}).get("confirmation_url")
    if not payment_url:
        await query.message.edit_text(
            "❌ Не удалось получить ссылку для оплаты.",
            reply_markup=InlineKeyboardMarkup(
                inline_keyboard=[[InlineKeyboardButton(text="Назад ⬅️", callback_data="back_to_main")]]
            )
        )
        return

    payment_keyboard = await payment_handler.create_payment_keyboard(payment_url)
    # Сохраняем в состоянии, если понадобится
    await state.update_data(gift_code=gift_code, payment_id=payment_info.get("id"))

    await query.message.edit_text(
        text="💸 Для оплаты подарка нажмите кнопку ниже:",
        reply_markup=payment_keyboard
    )

@router.message(lambda msg: msg.text and msg.text.startswith("/start gift_"))
async def start_gift(msg: Message, state: FSMContext):
    # Извлекаем код подарка
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
    from handlers.common import show_main_menu
    age_group = db.get_user_age(msg.from_user.id) or "0-3"
    try:
        await show_main_menu(msg.from_user.id, age_group, state)
    except Exception as e:
        logging.warning(f"Ошибка при открытии главного меню после подарка: {e}") 