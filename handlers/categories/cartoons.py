from aiogram import Router
from aiogram.types import CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton, InputMediaPhoto, WebAppInfo
from aiogram.fsm.context import FSMContext
from aiogram.utils.keyboard import InlineKeyboardBuilder
from utils.library import bot
from utils.s3_service import get_files_useful, get_url as get_s3_url, generate_download_url as get_s3_download_url
from aiogram.exceptions import TelegramBadRequest
import logging
from handlers.admin_panel.error_notify import notify_admins

router = Router()

async def handle_cartoons(user_id: int, state: FSMContext, age_group: str, message_id_to_edit: int):
    """Показывает список доступных мультиков для выбранного возраста"""
    file_path = f"Контент/{age_group}/Мультики"
    buttons, item_names = await get_files_useful(file_path, age_group, "checkmult_")

    await state.update_data(cartoon_item_names=item_names)

    back_button = InlineKeyboardButton(text="Назад в меню ⬅️", callback_data="back_to_main")

    if not buttons:
        text = "К сожалению, мультики для этого возраста пока не добавлены. 😔"
        error = f"Ошибка\nНе загружены мультики в категории возраста: {age_group}"
        await notify_admins(error)
        keyboard = InlineKeyboardMarkup(inline_keyboard=[[back_button]])
    else:
        text = "Выберите мультик для просмотра:"
        buttons.append(back_button)
        keyboard = InlineKeyboardMarkup(
            inline_keyboard=[buttons[i:i + 2] for i in range(0, len(buttons), 2)]
        )

    try:
        await bot.edit_message_text(
            chat_id=user_id,
            message_id=message_id_to_edit,
            text=text,
            reply_markup=keyboard
        )
        await state.update_data(message_to_delete=message_id_to_edit)
    except Exception as e:
        logging.error(f"Ошибка при редактировании в handle_cartoons: {e}")
        new_msg = await bot.send_message(user_id, text, reply_markup=keyboard)
        await state.update_data(message_to_delete=new_msg.message_id)


@router.callback_query(lambda c: c.data.startswith('checkmult_'))
async def check_mult(query: CallbackQuery, state: FSMContext):
    try:
        # Пытаемся ответить на callback query в начале
        await query.answer()
        
        _, index_str, type_age = query.data.split("_")
        item_index = int(index_str)
    except ValueError:
        error = f"Ошибка разбора callback_data в check_mult: {query.data}"
        logging.error(error)
        await notify_admins(f"Критическая ошибка\n{error}")
        await query.answer("Ошибка данных. Попробуйте еще раз.")
        return

    data = await state.get_data()
    item_names = data.get('cartoon_item_names')

    if not item_names or item_index >= len(item_names):
        error = f"Не найден список имен или индекс вне диапазона в check_mult: index={item_index}, names={item_names}"
        logging.error(error)
        await notify_admins(f"Критическая ошибка\n{error}")
        await query.answer("Ошибка получения данных. Пожалуйста, вернитесь в меню и попробуйте снова.")
        await handle_cartoons(query.from_user.id, state, type_age, query.message.message_id)
        return

    name = item_names[item_index]

    try:
        if name == 'Советские мультики':
            try:
                await query.message.edit_text(f"Загружаем '{name}'... ⏳", reply_markup=None)
            except Exception as e:
                logging.warning(f"Не удалось отредактировать на 'Загружаем': {e}")

            file_path = f"Контент/{type_age}/Мультики/{name}"
            soviet_buttons, soviet_item_names = await get_files_useful(file_path, type_age, "checksovmult_")

            await state.update_data(soviet_cartoon_item_names=soviet_item_names)

            back_button = InlineKeyboardButton(text="Назад к мультикам ⬅️", callback_data="menu_cartoons")

            if not soviet_buttons:
                text = f"В разделе '{name}' пока пусто. 😔"
                error = f"Ошибка\nВ разделе {name} нету мультиков"
                keyboard = InlineKeyboardMarkup(inline_keyboard=[[back_button]])
            else:
                text = "Выберите советский мультик для просмотра:"
                soviet_buttons.append(back_button)
                keyboard = InlineKeyboardMarkup(
                    inline_keyboard=[soviet_buttons[i:i + 2] for i in range(0, len(soviet_buttons), 2)]
                )

            try:
                await query.message.edit_text(text=text, reply_markup=keyboard)
                await state.update_data(message_to_delete=query.message.message_id)
            except Exception as e:
                logging.error(f"Ошибка при редактировании в check_mult (советские): {e}")
                new_msg = await bot.send_message(query.from_user.id, text, reply_markup=keyboard)
                await state.update_data(message_to_delete=new_msg.message_id)
            return

        try:
            await query.message.edit_text(f"Загружаем мультик '{name}'... ⏳", reply_markup=None)
        except Exception as e:
            logging.warning(f"Не удалось отредактировать на 'Загружаем мультик': {e}")

        path = f"Контент/{type_age}/Мультики/{name}"
        files = await get_s3_url(path)

        if not files:
            await query.answer(f"'{name}' – ещё не загружен или категория пуста.", show_alert=True)
            error = f"Ошибка\nПустая категория мультиков {name} в возрасте {type_age}"
            await notify_admins(error)
            await handle_cartoons(query.from_user.id, state, type_age, query.message.message_id)
            return

        # Находим и сохраняем постер один раз
        poster_url = None
        filtered_files = []
        image_exts = ('.jpg', '.jpeg', '.png', '.gif', '.bmp')

        for f in files:
            fname = f.name.lower()
            if fname.endswith(image_exts) and not poster_url:
                poster_url = f.file
            else:
                filtered_files.append(f)

        await state.update_data(
            mult_files=filtered_files,
            mult_index=0,
            mult_name=name,
            mult_type=type_age,
            mult_path=path,
            mult_poster_url=poster_url  # Сохраняем URL постера
        )

        await show_mult(query.from_user.id, query.message.message_id, state, path)

    except Exception as e:
        logging.error(f"Ошибка при обработке кнопки мультфильмов: {e}")
        await notify_admins(f"Критическая ошибка\nПри обработке кнопки в разделе Мультфильмы: {e}")
        # Показываем пользователю дружелюбное сообщение
        try:
            back_button = InlineKeyboardButton(text="◀️ Назад", callback_data=f"mult_{type_age}")
            keyboard = InlineKeyboardMarkup(inline_keyboard=[[back_button]])
            await bot.send_message(
                chat_id=query.from_user.id,
                text="Извините, произошла ошибка при загрузке мультфильма. Пожалуйста, попробуйте еще раз.",
                reply_markup=keyboard
            )
        except Exception as send_error:
            logging.error(f"Не удалось отправить сообщение об ошибке: {send_error}")


@router.callback_query(lambda c: c.data.startswith('checksovmult_'))
async def check_soviet_mult(query: CallbackQuery, state: FSMContext):
    try:
        _, index_str, type_age = query.data.split("_")
        item_index = int(index_str)
    except ValueError:
        error = f"Ошибка разбора callback_data в check_soviet_mult: {query.data}"
        logging.error(error)
        await notify_admins(f"Критическая ошибка\n{error}")
        await query.answer("Ошибка данных. Попробуйте еще раз.")
        return

    data = await state.get_data()
    soviet_item_names = data.get('soviet_cartoon_item_names')

    if not soviet_item_names or item_index >= len(soviet_item_names):
        error = f"Не найден список имен или индекс вне диапазона в check_soviet_mult: index={item_index}, names={soviet_item_names}"
        logging.error(error)
        await notify_admins(f"Критическая ошибка\n{error}")
        await query.answer("Ошибка получения данных. Пожалуйста, вернитесь в меню и попробуйте снова.")
        await handle_cartoons(query.from_user.id, state, type_age, query.message.message_id)
        return

    name = soviet_item_names[item_index]

    try:
        await query.message.edit_text(f"Загружаем советский мультик '{name}'... ⏳", reply_markup=None)
    except Exception as e:
        logging.warning(f"Не удалось отредактировать на 'Загружаем советский мультик': {e}")

    path = f"Контент/{type_age}/Мультики/Советские мультики/{name}"
    files = await get_s3_url(path)

    if not files:
        await query.answer(f"'{name}' – ещё не загружен или папка пуста.", show_alert=True)
        await notify_admins(f"Ошибка\n В советских мультиках {type_age}, не подгружен мультик {name}")
        await handle_cartoons(query.from_user.id, state, type_age, query.message.message_id)
        return

    # Находим и сохраняем постер один раз
    poster_url = None
    filtered_files = []
    image_exts = ('.jpg', '.jpeg', '.png', '.gif', '.bmp')

    for f in files:
        fname = f.name.lower()
        if fname.endswith(image_exts) and not poster_url:
            poster_url = f.file
        else:
            filtered_files.append(f)

    await state.update_data(
        mult_files=filtered_files,
        mult_index=0,
        mult_name=name,
        mult_type=type_age,
        mult_path=path,
        mult_poster_url=poster_url  # Сохраняем URL постера
    )
    await show_mult(query.from_user.id, query.message.message_id, state, path)


async def show_mult(user_id, message_id_to_edit, state: FSMContext, path):
    data = await state.get_data()

    mult_files = data.get('mult_files', [])
    idx = data.get('mult_index', 0)
    name = data.get('mult_name')
    poster_url = data.get('mult_poster_url')

    if not all([mult_files, name]):
        logging.error(f"Отсутствуют данные для пагинации: {data}")
        await bot.edit_message_text(chat_id=user_id, message_id=message_id_to_edit, text="Ошибка отображения мультика.")
        return

    if idx >= len(mult_files):
        logging.warning(f"Индекс пагинации {idx} вне диапазона {len(mult_files)}")
        idx = 0
        await state.update_data(mult_index=idx)

    file_info = mult_files[idx]
    file_name = getattr(file_info, 'name', 'Неизвестный файл')
    file_url = getattr(file_info, 'file', None)

    caption = f"{name} (серия {idx + 1} из {len(mult_files)})"

    # Формируем клавиатуру
    kb = InlineKeyboardBuilder()

    # Кнопки пагинации
    pagination_buttons = []
    if idx > 0:
        pagination_buttons.append(InlineKeyboardButton(text="⬅️ Пред.", callback_data="mult_prev"))
    pagination_buttons.append(InlineKeyboardButton(text=f"{idx + 1}/{len(mult_files)}", callback_data="no_action"))
    if idx < len(mult_files) - 1:
        pagination_buttons.append(InlineKeyboardButton(text="След. ➡️", callback_data="mult_next"))
    if pagination_buttons:
        kb.row(*pagination_buttons)

    # Кнопки просмотра и скачивания
    action_buttons = []
    if file_url:
        # URL для просмотра (обычный)
        action_buttons.append(InlineKeyboardButton(text="Смотреть 🌌", web_app=WebAppInfo(url=file_url)))
        path_download = path+"/"+file_name
        print(path_download)
        download_url = await get_s3_download_url(path_download)
        action_buttons.append(InlineKeyboardButton(text="Скачать ⤴️", url=download_url))

    if action_buttons:
        kb.row(*action_buttons)

    # Кнопка "Назад"
    kb.row(InlineKeyboardButton(text="Назад к списку ⬅️", callback_data="menu_cartoons"))

    try:
        if poster_url:
            media = InputMediaPhoto(media=poster_url, caption=caption)
            try:
                await bot.edit_message_media(
                    chat_id=user_id,
                    message_id=message_id_to_edit,
                    media=media,
                    reply_markup=kb.as_markup()
                )
                return
            except TelegramBadRequest:
                msg = await bot.send_photo(
                    chat_id=user_id,
                    photo=poster_url,
                    caption=caption,
                    reply_markup=kb.as_markup()
                )
                await state.update_data(message_to_delete=msg.message_id)
                try:
                    await bot.delete_message(chat_id=user_id, message_id=message_id_to_edit)
                except Exception:
                    pass
                return

        await bot.edit_message_text(
            chat_id=user_id,
            message_id=message_id_to_edit,
            text=caption,
            reply_markup=kb.as_markup()
        )
    except Exception as e:
        logging.error(f"Ошибка при отправке сообщения: {e}")
        msg = await bot.send_message(
            chat_id=user_id,
            text=caption,
            reply_markup=kb.as_markup()
        )
        await state.update_data(message_to_delete=msg.message_id)


@router.callback_query(lambda c: c.data in ['mult_prev', 'mult_next'])
async def handle_pagination(query: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    idx = data.get('mult_index', 0)
    files = data.get('mult_files', [])
    path = data.get('mult_path')

    if not files or not path:
        await query.answer("Ошибка пагинации: нет данных.", show_alert=True)
        return

    new_idx = idx
    if query.data == 'mult_prev' and idx > 0:
        new_idx = idx - 1
    elif query.data == 'mult_next' and idx < len(files) - 1:
        new_idx = idx + 1
    else:
        return await query.answer()

    await state.update_data(mult_index=new_idx)
    await show_mult(query.from_user.id, query.message.message_id, state, path)