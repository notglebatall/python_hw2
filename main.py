import asyncio
import logging
import os 

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.filters import CommandStart
from aiogram.types import Message

from routers.profile import profile_router
from routers.progress import progress_router

from database.engine import init_db, session_maker
from middlewares.db import DataBaseSession

from dotenv import load_dotenv

load_dotenv()

TOKEN = os.getenv('TOKEN')

bot = Bot(token=TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
dp = Dispatcher()


@dp.message(CommandStart())
async def command_start_handler(message: Message):
    await message.answer(f"Привет, {message.from_user.full_name}!")


async def main():
    await init_db()
    
    dp.include_router(profile_router)
    dp.include_router(progress_router)
    
    dp.update.middleware(DataBaseSession(session_pool=session_maker))
    
    await bot.delete_webhook(drop_pending_updates=True)
    await dp.start_polling(bot)


if __name__ == "__main__":
    try:
        logging.basicConfig(level=logging.INFO)
        asyncio.run(main())
    except KeyboardInterrupt:
        logging.error("Bot stopped!")