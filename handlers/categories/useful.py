import os
from aiogram import Router
from aiogram.types import CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton, InputMediaPhoto, \
    WebAppInfo, InputMediaDocument
from aiogram.fsm.context import FSMContext
from aiogram.utils.keyboard import InlineKeyboardBuilder
from utils.library import bot
from utils.s3_service import get_url, get_files_useful, generate_download_url as get_s3_download_url
from handlers.admin_panel.error_notify import notify_admins
from handlers.subscription.require_subscription import require_subscription_handler
import logging
from database.database import db
from typing import Dict
import time
from aiogram.exceptions import TelegramBadRequest

router = Router()

VIDEO_MESSAGE_CACHE: Dict[str, Dict[str, int]] = {}  # {file_url: {'message_id': int, 'timestamp': float}}

# Время жизни кэша (1 час)
CACHE_EXPIRATION = 3600

async def show_useful_content(user_id, message_id_to_edit, state: FSMContext, path):
    """Показывает контент с пагинацией"""
    data = await state.get_data()

    content_files = data.get('content_files', [])
    idx = data.get('content_index', 0)
    name = data.get('content_name')
    poster_url = data.get('content_poster_url')

    if not all([content_files, name]):
        logging.error(f"Отсутствуют данные для пагинации: {data}")
        await bot.edit_message_text(chat_id=user_id, message_id=message_id_to_edit, text="Ошибка отображения контента.")
        return

    if idx >= len(content_files):
        logging.warning(f"Индекс пагинации {idx} вне диапазона {len(content_files)}")
        idx = 0
        await state.update_data(content_index=idx)

    file_info = content_files[idx]
    file_name = getattr(file_info, 'name', 'Неизвестный файл')
    file_url = getattr(file_info, 'file', None)

    caption = f"{name} ({idx + 1} из {len(content_files)})"

    # Формируем клавиатуру
    kb = InlineKeyboardBuilder()

    # Кнопки пагинации
    pagination_buttons = []
    if idx > 0:
        pagination_buttons.append(InlineKeyboardButton(text="⬅️ Пред.", callback_data="content_prev"))
    pagination_buttons.append(InlineKeyboardButton(text=f"{idx + 1}/{len(content_files)}", callback_data="no_action"))
    if idx < len(content_files) - 1:
        pagination_buttons.append(InlineKeyboardButton(text="След. ➡️", callback_data="content_next"))
    if pagination_buttons:
        kb.row(*pagination_buttons)

    # Кнопки действий
    if file_url:
        action_buttons = []
        # URL для просмотра
        action_buttons.append(InlineKeyboardButton(text="Смотреть 🌌", web_app=WebAppInfo(url=file_url)))
        # URL для скачивания
        path_download = path+"/"+file_name
        download_url = await get_s3_download_url(path_download)
        action_buttons.append(InlineKeyboardButton(text="Скачать ⤴️", url=download_url))
        kb.row(*action_buttons)

    # Кнопка "Назад"
    kb.row(InlineKeyboardButton(text="Назад к списку ⬅️", callback_data="menu_useful"))

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

@router.callback_query(lambda c: c.data in ['content_prev', 'content_next'])
async def handle_content_pagination(query: CallbackQuery, state: FSMContext):
    """Обработка пагинации контента"""
    data = await state.get_data()
    idx = data.get('content_index', 0)
    files = data.get('content_files', [])
    path = data.get('content_path')

    if not files or not path:
        await query.answer("Ошибка пагинации: нет данных.", show_alert=True)
        return

    new_idx = idx
    if query.data == 'content_prev' and idx > 0:
        new_idx = idx - 1
    elif query.data == 'content_next' and idx < len(files) - 1:
        new_idx = idx + 1
    else:
        return await query.answer()

    await state.update_data(content_index=new_idx)
    await show_useful_content(query.from_user.id, query.message.message_id, state, path)

async def send_video_with_cache(user_id: int, video_file, caption: str) -> bool:
    """
    Отправляет видео с использованием кэшированного message_id, если он доступен
    """
    global VIDEO_MESSAGE_CACHE

    current_time = time.time()
    cache_key = video_file.name
    cached_data = VIDEO_MESSAGE_CACHE.get(cache_key)

    # Проверяем, есть ли актуальные данные в кэше
    if cached_data and current_time - cached_data['timestamp'] < CACHE_EXPIRATION:
        try:
            # Пытаемся переслать сообщение
            await bot.copy_message(
                chat_id=user_id,
                from_chat_id=cached_data['from_chat_id'],
                message_id=cached_data['message_id']
            )
            logging.info(f"Видео отправлено из кэша: {cache_key}")
            return True
        except Exception as e:
            logging.warning(f"Ошибка пересылки видео из кэша (удаляем из кэша): {e}")
            del VIDEO_MESSAGE_CACHE[cache_key]

    # Отправляем видео заново
    try:
        from aiogram.types import URLInputFile
        document_file = URLInputFile(video_file.file, filename=video_file.name)

        # Отправка видео в "тихий" сервис-чат (или самому себе), чтобы сохранить message_id
        temp_message = await bot.send_video(
            chat_id=user_id,
            video=document_file,
            caption=caption,
        )

        # Сохраняем данные в кэш
        VIDEO_MESSAGE_CACHE[cache_key] = {
            'message_id': temp_message.message_id,
            'from_chat_id': user_id,
            'timestamp': current_time
        }
        logging.info(f"Сохранено в кэш: {cache_key} -> {temp_message.message_id}")

        return True
    except Exception as e:
        logging.error(f"Ошибка при отправке видео: {e}")
        return False


def is_video_in_cache(video_url: str) -> bool:
    """Проверяет, есть ли видео в кэше"""
    cached_data = VIDEO_MESSAGE_CACHE.get(video_url)
    if not cached_data:
        return False

    current_time = time.time()
    return current_time - cached_data['timestamp'] < CACHE_EXPIRATION


# Хендлер вызывается из common.py при нажатии кнопки "Полезное 🔓"
async def other_category(user_id: int, state: FSMContext, age_group: str, message_id_to_edit: int):
    is_premium = db.check_premium_status(user_id)
    file_path = f"Контент/{age_group}/Полезное"

    # Получаем все кнопки и названия элементов
    raw_buttons, raw_item_names = await get_files_useful(file_path, age_group, "checkuseful_")

    processed_buttons = []
    processed_item_names = []
    locked_categories = db.get_all_locked_categories() if not is_premium else []

    for i, item_name in enumerate(raw_item_names):
        button = raw_buttons[i]

        if is_premium:
            # Для премиум пользователей все кнопки остаются как есть
            processed_buttons.append(button)
            processed_item_names.append(item_name)
            continue

        # Для не-премиум пользователей проверяем статус категории и подкатегорий
        item_path = f"{file_path}/{item_name}"
        items = await get_url(item_path)
        subfolders = [item for item in items if item.type == 'dir'] if items else []

        if not subfolders:
            # Если это конечная категория без подпапок
            if item_name in locked_categories:
                processed_buttons.append(InlineKeyboardButton(
                    text=f"{item_name} 🔒",
                    callback_data="require_subscription"
                ))
            else:
                processed_buttons.append(button)
            processed_item_names.append(item_name)
        else:
            # Если есть подпапки, проверяем их статус
            all_subfolders_locked = True
            for folder in subfolders:
                if folder.name not in locked_categories:
                    all_subfolders_locked = False
                    break

            if all_subfolders_locked:
                # Все подкатегории заблокированы - родительская с замком
                processed_buttons.append(InlineKeyboardButton(
                    text=f"{item_name} 🔒",
                    callback_data="require_subscription"
                ))
            else:
                # Хотя бы одна подкатегория разблокирована - родительская без замка
                processed_buttons.append(button)
            processed_item_names.append(item_name)

    await state.update_data(useful_item_names=processed_item_names)


    back_button = InlineKeyboardButton(text="Назад в меню ⬅️", callback_data="back_to_main")

    # Добавляем кнопки в список
    final_buttons_list = processed_buttons + [back_button]

    # Формируем клавиатуру
    send_buttons = InlineKeyboardMarkup(inline_keyboard=[[button] for button in final_buttons_list])

    text = "Выберите тему в разделе 'Полезное':"
    try:
        await bot.edit_message_text(
            chat_id=user_id,
            message_id=message_id_to_edit,
            text=text,
            reply_markup=send_buttons
        )
        await state.update_data(message_to_delete=message_id_to_edit)
    except Exception as e:
        logging.error(f"Ошибка при редактировании в other_category (premium): {e}")
        new_msg = await bot.send_message(user_id, text, reply_markup=send_buttons)
        await state.update_data(message_to_delete=new_msg.message_id)

# УДАЛЕНО: @router.message(F.text.in_(["Полезное 🔓"])) - теперь вызывается из common.py

# УДАЛЕНО: @router.callback_query(lambda c: c.data.startswith('cards_')) - функционал карточек пока не интегрирован в новую структуру
# УДАЛЕНО: @router.callback_query(lambda c: c.data.startswith('menu_')) - функционал меню пока не интегрирован



# Обработка выбора конкретной подкатегории в "Полезном"
@router.callback_query(lambda c: c.data.startswith('checkuseful_'))
async def check_useful_category(query: CallbackQuery, state: FSMContext):
    try:
        # Пытаемся ответить на callback query в начале
        await query.answer()
        
        parts = query.data.split('_')
        type_age = parts[-1]  # Возрастная группа

        if len(parts) == 3 and parts[1].isdigit():  # Формат checkuseful_index_age
            item_index = int(parts[1])
            data = await state.get_data()
            item_names = data.get('useful_item_names', [])

            if not item_names or item_index >= len(item_names):
                await query.answer("Ошибка получения данных. Попробуйте снова.")
                await other_category(query.from_user.id, state, type_age, query.message.message_id)
                return

            name = item_names[item_index]
            current_path = f"Контент/{type_age}/Полезное/{name}"
        else:  # Формат checkuseful_folder_name_age
            folder_name = '_'.join(parts[1:-1]).replace('_', ' ')
            data = await state.get_data()
            current_path = data.get('current_useful_path', f"Контент/{type_age}/Полезное")
            current_path = f"{current_path}/{folder_name}"
            name = folder_name

        await state.update_data(current_useful_path=current_path)

        # Проверяем подписку и блокировку категории
        is_premium = db.check_premium_status(query.from_user.id)
        if not is_premium:
            # Проверяем все родительские папки на блокировку
            path_parts = current_path.split('/')
            for i in range(3, len(path_parts)):  # Начинаем с "Полезное"
                parent_name = path_parts[i]
                if db.is_category_locked(parent_name):
                    await require_subscription_handler(query, state)
                    return

        try:
            items = await get_url(current_path)
        except Exception as e:
            logging.error(f"Ошибка при получении элементов из {current_path}: {e}")
            await query.answer("Ошибка при загрузке данных. Попробуйте позже.")
            return

        if not items:
            await query.answer(f"Категория '{name}' пуста.", show_alert=True)
            await notify_admins(f"Ошибка\nКатегория {name} в возрасте {type_age} пустая")
            await other_category(query.from_user.id, state, type_age, query.message.message_id)
            return

        # Разделяем папки и файлы
        subfolders = [item for item in items if item.type == 'dir']
        files = [item for item in items if item.type == 'file']

        # Если есть подпапки - показываем их как кнопки
        if subfolders:
            buttons = []
            for folder in subfolders:
                folder_name_encoded = folder.name.replace(' ', '_')
                button_text = folder.name

                if not is_premium and folder.name in db.get_all_locked_categories():
                    button_text += " 🔒"

                buttons.append(InlineKeyboardButton(
                    text=button_text,
                    callback_data=f"checkuseful_{folder_name_encoded}_{type_age}"
                ))

            buttons.append(InlineKeyboardButton(text="Назад к списку тем ⬅️", callback_data="menu_useful"))
            keyboard = InlineKeyboardMarkup(inline_keyboard=[[b] for b in buttons])

            text = f"Выберите подкатегорию в '{name}':"
            try:
                await query.message.edit_text(text=text, reply_markup=keyboard)
            except Exception as e:
                if "message is not modified" not in str(e):
                    logging.error(f"Ошибка при показе подпапок: {e}")
                    await notify_admins(f"Критическая ошибка\nПри показе папок {e} возраст {type_age}")
                    await bot.send_message(query.from_user.id, text, reply_markup=keyboard)

        # Если есть файлы - обрабатываем их
        elif files:
            image_extensions = ['jpg', 'jpeg', 'png']
            video_extensions = ['mp4', 'mov']
            pdf_files = [f for f in files if f.name.split('.')[-1].lower() == 'pdf']
            image_files = [f for f in files if f.name.split('.')[-1].lower() in image_extensions]
            video_files = [f for f in files if f.name.split('.')[-1].lower() in video_extensions]
            other_files = [f for f in files if
                          f.name.split('.')[-1].lower() not in image_extensions + video_extensions + ['pdf']]

            # Если есть видео, показываем с пагинацией
            if video_files:
                # Находим постер (первое изображение или None)
                poster_url = image_files[0].file if image_files else None
                content_files = video_files

                await state.update_data(
                    content_files=content_files,
                    content_index=0,
                    content_name=name,
                    content_path=current_path,
                    content_poster_url=poster_url
                )
                await show_useful_content(query.from_user.id, query.message.message_id, state, current_path)

                # Отправляем PDF файлы группой после показа контента
                if pdf_files:
                    media_group = []
                    for file in pdf_files:
                        try:
                            media = InputMediaDocument(
                                media=file.file,
                                caption=f"{file.name}" if len(media_group) == 0 else None
                            )
                            media_group.append(media)
                        except Exception as e:
                            logging.error(f"Ошибка при подготовке PDF файла {file.name}: {e}")

                    # Отправляем PDF файлы группами по 10
                    if media_group:
                        for i in range(0, len(media_group), 10):
                            try:
                                await bot.send_media_group(
                                    chat_id=query.from_user.id,
                                    media=media_group[i:i + 10]
                                )
                            except Exception as e:
                                logging.error(f"Ошибка при отправке группы PDF: {e}")
                                # Если не удалось отправить группой, пробуем по одному
                                for media_item in media_group[i:i + 10]:
                                    try:
                                        await bot.send_document(
                                            chat_id=query.from_user.id,
                                            document=media_item.media,
                                            caption=media_item.caption
                                        )
                                    except Exception as e:
                                        logging.error(f"Ошибка при отправке PDF файла: {e}")

                # Отправляем остальные файлы по одному
                for file in other_files:
                    try:
                        await bot.send_document(
                            chat_id=query.from_user.id,
                            document=file.file,
                            caption=f"{file.name}"
                        )
                    except Exception as e:
                        logging.error(f"Ошибка при отправке файла {file.name}: {e}")

                return

            # Если видео нет, отправляем все файлы обычным способом
            try:
                await query.message.edit_text(
                    f"Отправляем {name}...",
                    reply_markup=None
                )
            except Exception as e:
                if "message is not modified" not in str(e):
                    logging.warning(f"Не удалось отредактировать сообщение: {e}")

            sent_messages_count = 0

            # Отправляем изображения группой
            if image_files:
                media = [InputMediaPhoto(media=file.file) for file in image_files]
                for i in range(0, len(media), 10):
                    try:
                        await bot.send_media_group(chat_id=query.from_user.id, media=media[i:i + 10])
                        sent_messages_count += 1
                    except Exception as e:
                        logging.error(f"Ошибка при отправке медиагруппы: {e}")
                        # Если не удалось отправить группой, пробуем по одному
                        for media_item in media[i:i + 10]:
                            try:
                                await bot.send_photo(chat_id=query.from_user.id, photo=media_item.media)
                                sent_messages_count += 1
                            except Exception as e:
                                logging.error(f"Ошибка при отправке фото: {e}")

            # Отправляем PDF файлы группой
            if pdf_files:
                media_group = []
                for file in pdf_files:
                    try:
                        media = InputMediaDocument(
                            media=file.file,
                            caption=f"{file.name}" if len(media_group) == 0 else None
                        )
                        media_group.append(media)
                    except Exception as e:
                        logging.error(f"Ошибка при подготовке PDF файла {file.name}: {e}")

                # Отправляем PDF файлы группами по 10
                if media_group:
                    for i in range(0, len(media_group), 10):
                        try:
                            await bot.send_media_group(
                                chat_id=query.from_user.id,
                                media=media_group[i:i + 10]
                            )
                            sent_messages_count += 1
                        except Exception as e:
                            logging.error(f"Ошибка при отправке группы PDF: {e}")
                            # Если не удалось отправить группой, пробуем по одному
                            for media_item in media_group[i:i + 10]:
                                try:
                                    await bot.send_document(
                                        chat_id=query.from_user.id,
                                        document=media_item.media,
                                        caption=media_item.caption
                                    )
                                    sent_messages_count += 1
                                except Exception as e:
                                    logging.error(f"Ошибка при отправке PDF файла: {e}")

            # Отправляем остальные файлы по одному
            for file in other_files:
                try:
                    await bot.send_document(
                        chat_id=query.from_user.id,
                        document=file.file,
                        caption=f"{file.name}"
                    )
                    sent_messages_count += 1
                except Exception as e:
                    logging.error(f"Ошибка при отправке файла {file.name}: {e}")

            if sent_messages_count == 0:
                raise Exception("Не удалось отправить ни один файл")

            # После отправки всех файлов отправляем новое сообщение с кнопками
            final_text = f"{name} – успешно отправлено ✅"
            back_button = InlineKeyboardButton(text="Назад к списку ⬅️", callback_data="menu_useful")

            # Если были отправлены фотографии, добавляем кнопку "Как рисовать?"
            if image_files:
                how_draw_button = InlineKeyboardButton(
                    text="Как рисовать?",
                    web_app=WebAppInfo(
                        url=os.getenv("USEFUL_INSTRUCTION_URL")))
                final_keyboard = InlineKeyboardMarkup(inline_keyboard=[
                    [how_draw_button],
                    [back_button]
                ])
            else:
                final_keyboard = InlineKeyboardMarkup(inline_keyboard=[[back_button]])

            # Удаляем сообщение "Отправляем файлы..."
            try:
                await bot.delete_message(chat_id=query.from_user.id, message_id=query.message.message_id)
            except Exception as e:
                logging.warning(f"Не удалось удалить сообщение: {e}")

            # Отправляем новое сообщение с кнопками
            await bot.send_message(
                chat_id=query.from_user.id,
                text=final_text,
                reply_markup=final_keyboard
            )

    except Exception as e:
        logging.error(f"Ошибка при обработке кнопки: {e}")
        await notify_admins(f"Критическая ошибка\nПри обработке кнопки в разделе Полезное: {e}")
        # Показываем пользователю дружелюбное сообщение
        try:
            back_button = InlineKeyboardButton(text="◀️ Назад", callback_data=f"useful_{type_age}")
            keyboard = InlineKeyboardMarkup(inline_keyboard=[[back_button]])
            await bot.send_message(
                chat_id=query.from_user.id,
                text="Извините, произошла ошибка. Пожалуйста, попробуйте еще раз.",
                reply_markup=keyboard
            )
        except Exception as send_error:
            logging.error(f"Не удалось отправить сообщение об ошибке: {send_error}")
