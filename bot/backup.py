from bot.zip import aio_make_zip_file

from aiogram import types

from datetime import datetime
import os


async def backup_sender(bot, user_id):
    time_now = datetime.now()
    date_time_str = time_now.strftime("%Y-%m-%d %H:%M:%S")
    created_backup_file = await aio_make_zip_file(f"StravinskyBot_backup_{date_time_str}", "bot/user_data/")
    await bot.send_document(user_id, types.InputFile(created_backup_file))
    os.remove(created_backup_file)
