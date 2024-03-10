import os
import sys
import json

import shutil
import logging
import dotenv

from contextlib import suppress

from bot.loguru_handler import InterceptHandler
from bot.queue import Queue
from bot.database import SQLighter
from bot.other import *
from bot.constants import AudioLibrariesEnum, AudfprintModeEnum
from bot.backup import backup_sender

from aiogram.utils.callback_data import CallbackData
from aiogram import Bot, Dispatcher, executor, types
from aiogram.dispatcher.filters.state import State, StatesGroup
from aiogram.dispatcher import FSMContext
from aiogram.contrib.fsm_storage.files import JSONStorage

os.makedirs("bot/user_data", exist_ok=True)

dotenv.load_dotenv()

TELEGRAM_API_TOKEN = os.getenv("TELEGRAM_API_TOKEN")
AUDIO_LIBRARY = os.getenv("AUDIO_LIBRARY")
AUDFPRINT_MODE = os.getenv("AUDFPRINT_MODE")

def validate_env_vars():
    if TELEGRAM_API_TOKEN is None:
        raise ValueError("Please set TELEGRAM_API_TOKEN in .env file")
    if AUDIO_LIBRARY is None or AUDIO_LIBRARY not in [AudioLibrariesEnum.audfprint.value, AudioLibrariesEnum.SoundFingerprinting.value]:
        raise ValueError("Please set AUDIO_LIBRARY in .env file")
    if AUDIO_LIBRARY == AudioLibrariesEnum.audfprint.value and (AUDFPRINT_MODE is None or AUDFPRINT_MODE not in [AudfprintModeEnum.accurate.value, AudfprintModeEnum.fast.value]):
        raise ValueError("Please set AUDFPRINT_MODE in .env file")

validate_env_vars()

memory_storage = JSONStorage("bot/user_data/fsm_state_storage.json")

logging.basicConfig(handlers=[InterceptHandler()], level=0, force=True)

bot = Bot(token=TELEGRAM_API_TOKEN)
dp = Dispatcher(bot, storage=memory_storage)

db = SQLighter("bot/user_data/database.db")

queue = Queue(maxsize=6)

manage_folder_cb = CallbackData("manage_folder_menu", "folder_id")
remove_folder_cb = CallbackData("remove_folder_message", "folder_id")
remove_folder_process_cb = CallbackData("remove_folder_process", "folder_id")
upload_audio_sample_cb = CallbackData("upload_audio_sample_message", "folder_id")
remove_audio_sample_cb = CallbackData("remove_audio_sample_message", "folder_id")
recognize_query_cb = CallbackData("recognize_query_message", "folder_id")


class CreateFolder(StatesGroup):
    step_1 = State()
    step_2 = State()

class Upload_Sample(StatesGroup):
    step_1 = State()
    step_2 = State()

class RemoveSample(StatesGroup):
    step_1 = State()

class UploadQuery(StatesGroup):
    step_1 = State()

class TaskException(Exception):
    def __init__(self, text: str, ex: Exception):
        self.text = text
        self.ex = ex


async def download_file(message, file_id, destination) -> types.Message:
    message_text = message.text + "\n\nЗагрузка файла..."
    await message.edit_text(message_text + " Выполняем...")
    try:
        await bot.download_file_by_id(file_id, destination)
        assert os.path.exists(destination)
    except Exception as ex:
        managment_msg = await message.edit_text(message_text + " Критическая ошибка, отмена...")
        raise TaskException(managment_msg.text, ex)
    else:
        managment_msg = await message.edit_text(message_text + " Готово ✅")
        return managment_msg

async def audio_processing(message, input_file, output_file) -> types.Message:
    message_text = message.text + "\n\nПроверка на целостность, нормализация и конвертация аудио файла..."
    await message.edit_text(message_text + " Выполняем...")
    try:
        cmd = ['ffmpeg-normalize', '-q', '-vn', input_file, '-c:a', 'libmp3lame', '-o', output_file]
        await execute_command(cmd)
        assert os.path.exists(output_file)
    except Exception as ex:
        managment_msg = await message.edit_text(message_text + " Критическая ошибка, отмена... 📛")
        raise TaskException(managment_msg.text, ex)
    else:
        managment_msg = await message.edit_text(message_text + " Готово ✅")
        return managment_msg

async def register_audio_hashes(message, input_file, fingerprint_db) -> types.Message:
    message_text = message.text + "\n\nЗагружаем викторину в базу..."
    await message.edit_text(message_text + " Выполняем...")
    try:

        if os.path.exists(fingerprint_db) is False:
            db_hashes_add_method = 'new'
        elif os.path.exists(fingerprint_db) is True:
            db_hashes_add_method = 'add'

        if AUDIO_LIBRARY == AudioLibrariesEnum.audfprint.value:
            if AUDFPRINT_MODE == AudfprintModeEnum.accurate.value:
                cmd = [sys.executable, 'bot/library/audfprint-master/audfprint.py', db_hashes_add_method, '-d', fingerprint_db, input_file, '-n', '120', '-X', '-F', '0']
            elif AUDFPRINT_MODE == AudfprintModeEnum.fast.value:
                cmd = [sys.executable, 'bot/library/audfprint-master/audfprint.py', db_hashes_add_method, '-d', fingerprint_db, input_file]
        elif AUDIO_LIBRARY == AudioLibrariesEnum.SoundFingerprinting.value:
            cmd = ['bot/library/SoundFingerprinting/SoundFingerprinting.AddictedCS.Demo', "add", fingerprint_db, input_file]

        await execute_command(cmd)

        assert os.path.exists(fingerprint_db)
    except Exception as ex:
        managment_msg = await message.edit_text(message_text + " Критическая ошибка, отмена...")
        raise TaskException(managment_msg.text, ex)
    else:
        managment_msg = await message.edit_text(message_text + " Готово ✅")
        return managment_msg

async def match_audio_query(message, input_file, fingerprint_db) -> types.Message:
    message_text = message.text + "\n\nИщем викторину в базе..."
    await message.edit_text(message_text + " Выполняем...")
    try:
        if AUDIO_LIBRARY == AudioLibrariesEnum.audfprint.value:
            if AUDFPRINT_MODE == AudfprintModeEnum.accurate.value:
                cmd = [sys.executable, 'bot/library/audfprint/audfprint.py', 'match', '-d', fingerprint_db, input_file, '-n', '120', '-D', '2000', '-X', '-F', '18']
            elif AUDFPRINT_MODE == AudfprintModeEnum.fast.value:
                cmd = [sys.executable, 'bot/library/audfprint/audfprint.py', 'match', '-d', fingerprint_db, input_file]
        elif AUDIO_LIBRARY == AudioLibrariesEnum.SoundFingerprinting.value:
            cmd = ['bot/library/SoundFingerprinting/SoundFingerprinting.AddictedCS.Demo', 'match', fingerprint_db, input_file]

        process = await execute_command(cmd)
        command_result = None

        async with process_output_lines(process) as lines:
            async for line in lines:
                try:
                    command_result = json.loads(line)["RESULT"]
                except Exception as ex:
                    pass
        
        if command_result == "NOMATCH":
            result = "Это божественная музыка! Возможно, именно поэтому я не могу найти её. 😇"
        else:
            result = command_result

        assert os.path.exists(fingerprint_db)
    except Exception as ex:
        managment_msg = await message.edit_text(message_text + " Критическая ошибка, отмена...")
        raise TaskException(managment_msg.text, ex)
    else:
        managment_msg = await message.edit_text(message_text + f" Готово ✅\n\nРезультат:\n{result}\n")
        return managment_msg

async def delete_audio_hashes(message, fingerprint_db, sample_name, state: FSMContext) -> types.Message:
    user_data = await state.get_data()
    message_text = message.text + "\n\nУдаляем викторину из базы..."
    await message.edit_text(message_text + " Выполняем...")
    try:
        folder_samples = db.select_folder_samples(user_data["folder_id"])

        if len(folder_samples) == 1:
            os.remove(fingerprint_db)
            return

        if AUDIO_LIBRARY == AudioLibrariesEnum.audfprint.value:
            cmd = [sys.executable, 'bot/library/audfprint-master/audfprint.py', 'remove', '-d', fingerprint_db, sample_name, '-H', '2']
        elif AUDIO_LIBRARY == AudioLibrariesEnum.SoundFingerprinting.value:
            cmd = ['bot/library/SoundFingerprinting/SoundFingerprinting.AddictedCS.Demo', 'remove', fingerprint_db, sample_name]
        
        await execute_command(cmd)
        
        assert os.path.exists(fingerprint_db)
    except Exception as ex:
       managment_msg = await message.edit_text(message_text + " Критическая ошибка, отмена...")
       raise TaskException(managment_msg.text, ex)
    else:
        managment_msg = await message.edit_text(message_text + " Готово ✅")
        return managment_msg


@dp.message_handler(lambda message: db.select_user(message.chat.id) is None)
async def new_user_message(message: types.Message):
    db.create_user(message.chat.id, message.from_user.first_name)
    await process_help_command_1(message)


@dp.message_handler(commands=['start'], state='*')
async def main_menu_message(message: types.Message, messaging_type='reply'):
    keyboard_markup = types.InlineKeyboardMarkup()
    folder_list_btns = types.InlineKeyboardButton('Папки 📂', callback_data='folders_list')
    about_btns = types.InlineKeyboardButton('О боте / помощь 🤖', callback_data='about_bot_message')
    keyboard_markup.row(folder_list_btns)
    keyboard_markup.row(about_btns)
    if messaging_type == 'edit':
        await message.edit_text("Главное меню : ", reply_markup=keyboard_markup)
    elif messaging_type == 'reply':
        await message.reply("Главное меню : ", reply_markup=keyboard_markup)


@dp.callback_query_handler(text='about_bot_message')
async def about_bot_message(call: types.CallbackQuery):
    await process_help_command_1(call.message, "edit")
    await call.answer()

async def folder_list_menu_message(message: types.Message, messaging_type="edit"):
    user_folders = db.select_user_folders(message.chat.id)

    keyboard_markup = types.InlineKeyboardMarkup()
    create_new_folder_btn = types.InlineKeyboardButton('Создать новую папку 🗂', callback_data='create_new_folder')
    keyboard_markup.row(create_new_folder_btn)

    for folder in user_folders:
        samples_count = len(db.select_folder_samples(folder[0]))
        folder_btn = types.InlineKeyboardButton(f"{folder[1]} ({samples_count})", callback_data=manage_folder_cb.new(folder[0]))
        keyboard_markup.row(folder_btn)

    back_btn = types.InlineKeyboardButton('«      ', callback_data='welcome_message')
    keyboard_markup.row(back_btn)

    if messaging_type == 'start':
        await message.answer(f"Менеджер папок :\n\nОбщее количество папок: {len(user_folders)}", reply_markup=keyboard_markup)
    elif messaging_type == 'edit':
        await message.edit_text(f"Менеджер папок :\n\nОбщее количество папок: {len(user_folders)}", reply_markup=keyboard_markup)


@dp.callback_query_handler(text="create_new_folder")
async def create_folder_step_1_message(call: types.CallbackQuery):
    if len(db.select_user_folders(call.message.chat.id)) >= 10:
        await call.answer('Максимальное количество папок - 10. Удалите не нужные папки и повторите попытку.', True)
        return

    keyboard_markup = types.InlineKeyboardMarkup()
    back_btn = types.InlineKeyboardButton('«      ', callback_data='folders_list')
    keyboard_markup.row(back_btn)
    await call.message.edit_text("Введите название вашей папки : ", reply_markup=keyboard_markup)
    await CreateFolder.step_1.set()
    await call.answer()

@dp.message_handler(state=CreateFolder.step_1, content_types=types.ContentTypes.TEXT)
async def create_folder_step_2_message(message: types.Message, state: FSMContext):
    async with state.proxy() as user_data:
        user_data['folder_name'] = message.text.replace('\n', ' ')

    keyboard_markup = types.InlineKeyboardMarkup()
    back_btn = types.InlineKeyboardButton('«      ', callback_data='folders_list')
    keyboard_markup.row(back_btn)

    # Проверяем количество символов в названии папки
    if len(user_data['folder_name']) >= 20:
        await message.reply('Название папки превышает 20 символов', reply_markup=keyboard_markup)
        return

    # Ищем название данной папки в БД
    if user_data['folder_name'].lower() in [x[1].lower() for x in db.select_user_folders(message.chat.id)]:
        await message.reply('Папка с данным именем уже существует! Введите другое имя', reply_markup=keyboard_markup)
        return

    await state.finish()

    path_list = path(message.chat.id, user_data['folder_name'])
    os.makedirs(path_list.tmp_audio_samples())
    os.makedirs(path_list.processed_audio_samples())
    os.makedirs(path_list.tmp_query_audio())
    os.makedirs(path_list.processed_query_audio())
    os.makedirs(path_list.fingerprint_db_dir_path(), exist_ok=True)

    db.create_folder(message.chat.id, user_data['folder_name'])

    await message.reply(f'✅ Папка "{user_data["folder_name"]}" успешно создана!')
    await folder_list_menu_message(message, 'start')


@dp.callback_query_handler(remove_folder_cb.filter(), state='*')
async def delete_folder_step_1_message(call: types.CallbackQuery, callback_data: dict):
    folder_id = int(callback_data['folder_id'])
    folder_info = db.select_folder(folder_id)

    keyboard_markup = types.InlineKeyboardMarkup()
    delete_btn = types.InlineKeyboardButton('Да!', callback_data=remove_folder_process_cb.new(folder_id))
    back_btn = types.InlineKeyboardButton('«      ', callback_data=manage_folder_cb.new(folder_id))
    keyboard_markup.row(delete_btn)
    keyboard_markup.row(back_btn)
    await call.message.edit_text(
        f'Вы действительно хотите удалить папку "{folder_info[1]}" со всеми викторинами внутри?\n\n'
        "<b>ВНИМАНИЕ! ЭТО ДЕЙСТВИЕ НЕЛЬЗЯ ОТМЕНИТЬ</b>",
        parse_mode="HTML",
        reply_markup=keyboard_markup
    )
    await call.answer()

@dp.callback_query_handler(remove_folder_process_cb.filter(), state='*')
async def delete_folder_step_2_message(call: types.CallbackQuery, callback_data: dict):
    folder_id = int(callback_data['folder_id'])
    folder_info = db.select_folder(folder_id)
    folder_samples = db.select_folder_samples(folder_id)

    path_list = path(call.message.chat.id, folder_info[1])
    # Delete all folders
    shutil.rmtree(path_list.tmp_audio_samples())
    shutil.rmtree(path_list.processed_audio_samples())
    shutil.rmtree(path_list.tmp_query_audio())
    shutil.rmtree(path_list.processed_query_audio())

    # Delete audiofingerprint database
    if os.path.exists(path_list.fingerprint_db()):
        os.remove(path_list.fingerprint_db())

    for sample in folder_samples:
        db.unregister_audio_sample(folder_id, sample[1])

    db.delete_folder(folder_id)

    await call.answer(f'✅ Папка "{folder_info[1]}" успешно удалена!')
    await folder_list_menu_message(call.message, 'edit')


@dp.callback_query_handler(manage_folder_cb.filter(), state='*')
async def manage_folder_menu_message(call: types.CallbackQuery, callback_data: dict, state: FSMContext):
    await state.finish()

    folder_id = int(callback_data['folder_id'])
    folder_info = db.select_folder(folder_id)
    folder_samples = db.select_folder_samples(folder_id)

    keyboard_markup = types.InlineKeyboardMarkup()
    upload_audio_samples_btn = types.InlineKeyboardButton('Загрузить викторины 📤', callback_data=upload_audio_sample_cb.new(folder_id))
    keyboard_markup.row(upload_audio_samples_btn)
    remove_audio_samples_btn = types.InlineKeyboardButton('Удалить викторину 🗑', callback_data=remove_audio_sample_cb.new(folder_id))
    keyboard_markup.row(remove_audio_samples_btn)
    quiz_mode_btn = types.InlineKeyboardButton('Распознать викторину 🔎', callback_data=recognize_query_cb.new(folder_id))
    keyboard_markup.row(quiz_mode_btn)
    delete_btn = types.InlineKeyboardButton('Удалить папкy ❌', callback_data=remove_folder_cb.new(folder_id))
    keyboard_markup.row(delete_btn)
    back_btn = types.InlineKeyboardButton('«      ', callback_data='folders_list')
    keyboard_markup.row(back_btn)

    samples_name = ""
    for num, sample in enumerate(folder_samples, 1):
        samples_name += str(f"{num}) {sample[1]}\n")

    await call.message.edit_text(
        f"Вы работаете с папкой : {folder_info[1]}\n\n"
        f"Количество викторин: {len(folder_samples)}\n"
        f"Список викторин :\n{samples_name}\n"
        "Ваши действия - ", reply_markup=keyboard_markup
    )
    await call.answer()


@dp.callback_query_handler(upload_audio_sample_cb.filter(), state='*')
async def upload_audio_sample_message(call: types.CallbackQuery, callback_data: dict, state: FSMContext):
    folder_id = int(callback_data['folder_id'])
    folder_info = db.select_folder(folder_id)
    folder_samples = db.select_folder_samples(folder_id)

    if len(folder_samples) > 90:
        await call.answer('Максимальное возможное количество викторин в папке - 90', True)
        return

    keyboard_markup = types.InlineKeyboardMarkup()
    back_btn = types.InlineKeyboardButton('«      ', callback_data=manage_folder_cb.new(folder_id))
    keyboard_markup.row(back_btn)
    await call.message.edit_text(
                    f'Вы работаете с папкой "{folder_info[1]}", в режиме загрузки викторин\n\n'
                    'Поддерживаемые форматы - mp3, wav, wma, ogg, flac, aac, opus;\n\n'
                    'Максимальный размер файла - 20 мб, это лимит установленный Телеграмом для ботов;',
                    parse_mode="HTML",
                    reply_markup=keyboard_markup)
    await Upload_Sample.step_1.set()
    await state.update_data({"folder_id": folder_id})
    await call.answer()

@dp.message_handler(state=Upload_Sample.step_1, content_types=types.ContentTypes.DOCUMENT | types.ContentTypes.AUDIO | types.ContentTypes.VIDEO)
async def upload_audio_sample_step_1_message(message: types.Message, state: FSMContext):
    if message.content_type == "document":
        audio_sample_file_info = message.document
        name_file = message.document.file_name
    elif message.content_type == "audio":
        audio_sample_file_info = message.audio
        name_file = message.audio.file_name

    async with state.proxy() as user_data:
        user_data['audio_sample_file_name'] = os.path.splitext(name_file)[0]
        user_data['audio_sample_file_extensions'] = os.path.splitext(name_file)[1]
        user_data['audio_sample_file_id'] = audio_sample_file_info.file_id
        user_data['audio_sample_file_unique_id'] = audio_sample_file_info.file_unique_id

    keyboard_markup = types.InlineKeyboardMarkup()
    back_btn = types.InlineKeyboardButton('«      ', callback_data=manage_folder_cb.new(user_data["folder_id"]))
    keyboard_markup.row(back_btn)

    # Проверяем размер файла
    if int(audio_sample_file_info.file_size) >= 20871520:
        await message.reply('Размер файла превышает 20 mb. Отправьте другой файл', reply_markup=keyboard_markup)
        return

    # Проверка на загруженность файла в текущей папки через db
    file_unique_id = audio_sample_file_info.file_unique_id
    for sample in db.select_folder_samples(user_data["folder_id"]):
        if sample[3] == file_unique_id:
            await message.reply(f'Эта викторина уже существует в папке под названием "{sample[1]}"\nОтправьте другой файл', reply_markup=keyboard_markup)
            return

    await state.update_data({'audio_sample_name': user_data["audio_sample_file_name"]})

    # Проверяем расширение файла
    if user_data["audio_sample_file_extensions"].lower() in ('.aac', '.wav', '.mp3', '.wma', '.ogg', '.flac', '.opus'):
        # await Upload_Sample.step_2.set()

        # await message.reply(
        #                 f'Название вашего аудио файла : <code>{user_data["audio_sample_file_name"]}</code>\n\n'
        #                 'Введите название аудио сэмпла. Это название будет отображатся во время распознавания викторины',
        #                 parse_mode="HTML",
        #                 reply_markup=keyboard_markup)
        await upload_audio_sample_step_2_message(message, state)
    elif not user_data["audio_sample_file_extensions"]:
        await message.reply('Мы не можем определить формат аудио записи. Возможно название файла очень длинное.\nИзмените название файла на более короткую и повторите попытку еще раз', reply_markup=keyboard_markup)
        return
    else:
        await message.reply(f'Увы, но мы формат "{user_data["audio_sample_file_extensions"]}" не принемаем, пришлите в другом формате\n\n', reply_markup=keyboard_markup)
        return


@dp.message_handler(state=Upload_Sample.step_2, content_types=types.ContentTypes.TEXT)
async def upload_audio_sample_step_2_message(message: types.Message, state: FSMContext):
    # async with state.proxy() as user_data:
    #     user_data['audio_sample_name'] = message.text.replace('\n', ' ')

    user_data = await state.get_data()
    folder_info = db.select_folder(user_data["folder_id"])

    file_id = user_data["audio_sample_file_id"]
    audio_sample_name = user_data["audio_sample_name"]
    audio_sample_full_name = f'{audio_sample_name}{user_data["audio_sample_file_extensions"]}'
    path_list = path(message.chat.id, folder_info[1])

    keyboard_markup = types.InlineKeyboardMarkup()
    back_btn = types.InlineKeyboardButton('«      ', callback_data=manage_folder_cb.new(user_data["folder_id"]))
    keyboard_markup.row(back_btn)

    # Проверяем количество символов в названии сэмпла
    if len(audio_sample_name) >= 180:
        await message.reply('Название файла превышает 180 символов, измените название файла', reply_markup=keyboard_markup)
        return

    # Проверяем, существует ли аудио сэмпл с таким же названием
    if user_data["audio_sample_name"].lower() in [x[1].lower() for x in db.select_folder_samples(user_data["folder_id"])]:
        await message.reply("Викторина с таким же названием уже существует", reply_markup=keyboard_markup)
        return

    # await state.finish()

    managment_msg = await message.reply('Задача поставлена в очередь, ожидайте...')

    await queue.put_item(message.chat.id)

    try:
        # Stage 0 : download file
        managment_msg = await download_file(managment_msg, file_id, path_list.tmp_audio_samples(audio_sample_full_name))
        # Stage 1 : check audio files for integrity and mormalize, convert them
        managment_msg = await audio_processing(managment_msg, path_list.tmp_audio_samples(audio_sample_full_name), path_list.processed_audio_samples(audio_sample_name + ".mp3"))
        # Stage 2 : analyze current audio sample hashes
        managment_msg = await register_audio_hashes(managment_msg, path_list.processed_audio_samples(audio_sample_name + ".mp3"), path_list.fingerprint_db())
        # Stage 3 : register current audio sample hashes
        db.register_audio_sample(user_data["folder_id"], user_data["audio_sample_name"], user_data["audio_sample_file_unique_id"])
    except TaskException as task_exception:
        logging.exception(task_exception.ex)
        message_text = task_exception.text + "\n\nЗадача завершилась с ошибкой"
    else:
        message_text = managment_msg.text + "\n\nЗадача успешно завершена"
    finally:
        keyboard_markup = types.InlineKeyboardMarkup()
        manage_folder_menu_message_btn = types.InlineKeyboardButton('« Вернутся к текущей папке', callback_data=manage_folder_cb.new(user_data["folder_id"]))
        upload_sample_btn = types.InlineKeyboardButton('» Загрузить еще одну викторину', callback_data=upload_audio_sample_cb.new(user_data["folder_id"]))
        keyboard_markup.row(manage_folder_menu_message_btn)
        keyboard_markup.row(upload_sample_btn)
        await managment_msg.edit_text(message_text, reply_markup=keyboard_markup)

        with suppress(FileNotFoundError):
            os.remove(path_list.tmp_audio_samples(audio_sample_full_name))
            os.remove(path_list.processed_audio_samples(audio_sample_name + ".mp3"))

        await queue.get_item(message.chat.id)
        queue.task_done()


@dp.callback_query_handler(remove_audio_sample_cb.filter(), state='*')
async def remove_audio_sample_message(call: types.CallbackQuery, callback_data: dict, state: FSMContext):
    folder_id = int(callback_data['folder_id'])
    folder_info = db.select_folder(folder_id)
    folder_samples = db.select_folder_samples(folder_id)

    if len(folder_samples) == 0:
        await call.answer(f'В папке "{folder_info[1]}" отсутствуют викторины.', True)
        return

    keyboard = types.ReplyKeyboardMarkup(resize_keyboard=True, one_time_keyboard=True)
    keyboard.add("<<< Отмена >>>")

    for sample in folder_samples:
        keyboard.add(sample[1])

    await call.message.delete()
    await call.message.answer("Выберите викторину которую хотите удалить:", reply_markup=keyboard)
    await RemoveSample.step_1.set()
    await state.update_data({"folder_id": folder_id})
    await call.answer()

@dp.message_handler(state=RemoveSample.step_1, content_types=types.ContentTypes.TEXT)
async def remove_audio_sample_step_1_message(message: types.Message, state: FSMContext):
    async with state.proxy() as user_data:
        user_data['chosen_sample'] = message.text

    await state.finish()

    folder_info = db.select_folder(user_data["folder_id"])

    path_list = path(message.chat.id, folder_info[1])

    if user_data['chosen_sample'] == "<<< Отмена >>>":
        await message.reply('Вы отменили операцию', reply_markup=keyboard_markup)
        return

    managment_msg = await message.reply('Задача поставлена в очередь, ожидайте...')

    await queue.put_item(message.chat.id)

    try:
        managment_msg = await delete_audio_hashes(managment_msg, path_list.fingerprint_db(), path_list.processed_audio_samples(user_data['chosen_sample'] + ".mp3"))
        db.unregister_audio_sample(user_data["folder_id"], user_data['chosen_sample'])
    except TaskException as task_exception:
        logging.exception(task_exception.ex)
        message_text = task_exception.text + "\n\nЗадача завершилась с ошибкой"
    else:
        message_text = managment_msg.text + "\n\nЗадача успешно завершена"
    finally:
        keyboard_markup = types.InlineKeyboardMarkup()
        manage_folder_menu_message_btn = types.InlineKeyboardButton('« Вернутся к текущей папке', callback_data=manage_folder_cb.new(user_data["folder_id"]))
        upload_sample_btn = types.InlineKeyboardButton('» Удалить еще одну викторину', callback_data=remove_audio_sample_cb.new(user_data["folder_id"]))
        keyboard_markup.row(manage_folder_menu_message_btn)
        keyboard_markup.row(upload_sample_btn)
        await managment_msg.edit_text(message_text, reply_markup=keyboard_markup)

        await queue.get_item(message.chat.id)
        queue.task_done()

@dp.callback_query_handler(recognize_query_cb.filter(), state='*')
async def recognize_query_message(call: types.CallbackQuery, callback_data: dict, state: FSMContext):
    folder_id = int(callback_data['folder_id'])
    folder_info = db.select_folder(folder_id)
    folder_samples = db.select_folder_samples(folder_id)

    if len(folder_samples) == 0:
        await call.answer(f'В папке "{folder_info[1]}" нету ни одной викторины', True)
        return

    keyboard_markup = types.InlineKeyboardMarkup()
    back_btn = types.InlineKeyboardButton('«      ', callback_data=manage_folder_cb.new(folder_id))
    keyboard_markup.row(back_btn)
    await call.message.edit_text(
                    f'Вы работаете с папкой "{folder_info[1]}", в режиме распознавания викторины\n\n'
                    "<i>Жду от тебя голосовое сообщение, с длительностью не менее 5 секунд</i>",
                    parse_mode="HTML",
                    reply_markup=keyboard_markup)
    await UploadQuery.step_1.set()
    await state.update_data({"folder_id": folder_id})
    await call.answer()

@dp.message_handler(state=UploadQuery.step_1, content_types=types.ContentTypes.VOICE | types.ContentTypes.AUDIO)
async def recognize_query_step_1_message(message: types.Message, state: FSMContext):
    user_data = await state.get_data()
    folder_info = db.select_folder(user_data["folder_id"])

    random_str = generate_random_string(32)
    path_list = path(message.chat.id, folder_info[1])

    if message.content_type == "voice":
        file_id = message.voice.file_id
        if message.voice.mime_type == "audio/ogg":
            query_audio_file_extensions = ".ogg"
        else:
            query_audio_file_extensions = ".NULL"
            # await message.answer("Что-то пошло не так...", True)
    elif message.content_type == "audio":
        file_id = message.audio.file_id
        name_file = message.audio.file_name  # New in Bot API 5.0
        query_audio_file_extensions = os.path.splitext(name_file)[1]

    if query_audio_file_extensions.lower() not in ('.aac', '.wav', '.mp3', '.wma', '.ogg', '.flac', '.opus'):
        keyboard_markup = types.InlineKeyboardMarkup()
        back_btn = types.InlineKeyboardButton('«      ', callback_data=manage_folder_cb.new(user_data["folder_id"]))
        keyboard_markup.row(back_btn)
        await message.reply('Мы не можем определить формат аудио записи или не поддерживаемый формат. Возможно название файла очень длинное.\nПовторите попытку еще раз', reply_markup=keyboard_markup)
        return

    query_audio_full_name = f"{random_str}{query_audio_file_extensions}"
    query_audio_name = f"{random_str}"

    await state.finish()
    managment_msg = await message.reply('Задача поставлена в очередь, ожидайте...')

    await queue.put_item(message.chat.id)

    try:
        # Stage 0 : download file
        managment_msg = await download_file(managment_msg, file_id, path_list.tmp_query_audio(query_audio_full_name))
        # Stage 1 : check audio files for integrity and mormalize, convert them
        managment_msg = await audio_processing(managment_msg, path_list.tmp_query_audio(query_audio_full_name), path_list.processed_query_audio(query_audio_name + ".mp3"))
        # Stage 2 : match audio query
        managment_msg = await match_audio_query(managment_msg, path_list.processed_query_audio(query_audio_name + ".mp3"), path_list.fingerprint_db())
    except TaskException as task_exception:
        logging.exception(task_exception.ex)
        message_text = task_exception.text + "\n\nЗадача завершилась с ошибкой"
    else:
        message_text = managment_msg.text + "\n\nЗадача успешно завершена"
    finally:
        keyboard_markup = types.InlineKeyboardMarkup()
        manage_folder_menu_message_btn = types.InlineKeyboardButton('« Вернутся к текущей папке', callback_data=manage_folder_cb.new(user_data["folder_id"]))
        upload_sample_btn = types.InlineKeyboardButton('» Распознать еще одну викторину', callback_data=recognize_query_cb.new(user_data["folder_id"]))
        keyboard_markup.row(manage_folder_menu_message_btn)
        keyboard_markup.row(upload_sample_btn)
        await managment_msg.edit_text(message_text, reply_markup=keyboard_markup)
        
        with suppress(FileNotFoundError):
            os.remove(path_list.tmp_query_audio(query_audio_full_name))
            os.remove(path_list.processed_query_audio(query_audio_name + ".mp3"))

        await queue.get_item(message.chat.id)
        queue.task_done()

@dp.message_handler(commands=['help'], state='*')
async def process_help_command_1(message: types.Message, messaging_type="start"):
    message_text = ("<b>Введение</b>\n\n"
                    "<code>StravinskyBot</code> - бот помощник для распознавания музыкальных викторин.\n\n"
                    "<b>Принцип работ бота:</b>\n"
                    "1&gt; Загружаете аудио файлы викторины в бота\n"
                    "2&gt; Во время самой викторины отправляете голосовые сообщения и я вам выдаю название записи\n\n"
                    "<i>Пройдите все страницы, чтобы узнать как пользоваться ботом.</i>")
    keyboard_markup = types.InlineKeyboardMarkup()
    next_btn = types.InlineKeyboardButton('» Далее', callback_data="process_help_command_2")
    keyboard_markup.row(next_btn)
    if messaging_type == "start":
        await message.reply(message_text, reply_markup=keyboard_markup, parse_mode="HTML")
    elif messaging_type == "edit":
        await message.edit_text(message_text, reply_markup=keyboard_markup, parse_mode="HTML")

async def process_help_command_2(message: types.Message):
    message_text = ("<b>Использование</b>\n\n"
                    "<i>Для того чтобы отобразить главное меню бота, нужно ввести команду </i><i>/start</i>\n\n"
                    "<b># Загрузка аудио записей\n"
                    "</b>0&gt; Откройте главное меню, если это меню не открыта\n"
                    "1&gt; Перейдите в меню 'Папки' и создайте новую папку\n"
                    "2&gt; Придумайте понятное для Вас название папке\n"
                    "3&gt; Откройте только что созданную папку, и нажмите на кнопку 'Загрузить викторину 📤' и отправьте файлом мне аудио запись, которую дал преподаватель для подготовке к викторине\n"
                    "5&gt; Готово!\n\n"
                    "<b># Распознавание викторины</b>\n"
                    "0&gt; Откройте главное меню, если это меню не открыта\n"
                    "1&gt; Перейдите в меню 'Папки'\n"
                    "2&gt; Откройте только что созданную папку, и нажмите на кнопку 'Распознать викторину 🔍' и отправьте файлом или голосовым сообщением отрывок из музыкальной викторины, и ожидайте пока не выйдет название распознанной викторины\n"
                    "3&gt; Готово!")
    keyboard_markup = types.InlineKeyboardMarkup()
    back_btn = types.InlineKeyboardButton('« Назад', callback_data="process_help_command_1")
    next_btn = types.InlineKeyboardButton('» Далее', callback_data="process_help_command_3")
    keyboard_markup.row(back_btn, next_btn)
    await message.edit_text(message_text, reply_markup=keyboard_markup, parse_mode="HTML")

async def process_help_command_3(message: types.Message):
    message_text = ("<b>Поддерживаемые форматы аудио записей:</b>\n"
                    "&gt;*.ogg\n"
                    "&gt;*.mp3\n"
                    "&gt;*.acc\n"
                    "&gt;*.wav\n"
                    "&gt;*.wma\n"
                    "&gt;*.flac\n"
                    "&gt;*.opus\n\n"
                    "<i>Нету формата в котором у тебя аудио запись? Не проблема, просто напиши разработчику об этом: </i><i>@SuenishSalkimbaev</i>")
    keyboard_markup = types.InlineKeyboardMarkup()
    back_btn = types.InlineKeyboardButton('« Назад', callback_data="process_help_command_2")
    next_btn = types.InlineKeyboardButton('» Далее', callback_data="process_help_command_4")
    keyboard_markup.row(back_btn, next_btn)
    await message.edit_text(message_text, reply_markup=keyboard_markup, parse_mode="HTML")

async def process_help_command_4(message: types.Message):
    message_text = ("<b>Дополнительная информация</b>\n\n"
                    "<i>&gt; В случае если у вас возникнут вопросы по боту, или есть пожелание или же хотелки, вы можете написать разработчику: </i><i>@SuenishSalkimbaev</i>")
    keyboard_markup = types.InlineKeyboardMarkup()
    back_btn = types.InlineKeyboardButton('« Назад', callback_data="process_help_command_3")
    next_btn = types.InlineKeyboardButton('Готово!', callback_data="welcome_message")
    keyboard_markup.row(back_btn, next_btn)
    await message.edit_text(message_text, reply_markup=keyboard_markup, parse_mode="HTML")

# TODO: danger
@dp.message_handler(commands=['backup'], state='*')
async def backup_message(msg: types.Message):
    await backup_sender(msg.bot, msg.chat.id)

@dp.message_handler(content_types=types.ContentType.ANY, state='*')
async def unknown_message(msg: types.Message):
    await msg.reply('Я не знаю, что с этим делать\nЯ просто напомню, что есть команда /help')

@dp.callback_query_handler(state='*')
async def callback_handler(query: types.CallbackQuery, state):
    answer_data = query.data
    if answer_data == 'welcome_message':
        await query.answer()
        await main_menu_message(query.message, 'edit')
    if answer_data == 'folders_list':
        await state.finish()
        await query.answer()
        await folder_list_menu_message(query.message, 'edit')
    if answer_data == 'process_help_command_1':
        await query.answer()
        await process_help_command_1(query.message, "edit")
    if answer_data == 'process_help_command_2':
        await query.answer()
        await process_help_command_2(query.message)
    if answer_data == 'process_help_command_3':
        await query.answer()
        await process_help_command_3(query.message)
    if answer_data == 'process_help_command_4':
        await query.answer()
        await process_help_command_4(query.message)

async def on_bot_shutdown(dp: Dispatcher):
    logging.warning("Bot shutdown command recived...")
    logging.warning("Waiting queue...")
    await queue.join()

if __name__ == '__main__':
    executor.start_polling(dp, on_shutdown=on_bot_shutdown)
