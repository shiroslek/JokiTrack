import os
import logging

from telegram import Update
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    filters,
)
from apscheduler.schedulers.asyncio import AsyncIOScheduler

from database import init_db
from handlers import start, get_id, any_message, cb_handler
from scheduler import send_hourly_reminder, check_deadlines

logging.basicConfig(
    format='%(asctime)s | %(levelname)s | %(name)s | %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

BOT_TOKEN = os.environ['BOT_TOKEN']
CHAT_ID   = os.environ['CHAT_ID']


async def post_init(application: Application) -> None:
    init_db()
    logger.info("Database initialized")

    scheduler = AsyncIOScheduler(timezone='Asia/Makassar')

    scheduler.add_job(
        send_hourly_reminder,
        trigger='cron',
        minute=0,
        args=[application.bot, CHAT_ID],
        id='hourly_reminder',
    )
    scheduler.add_job(
        check_deadlines,
        trigger='interval',
        minutes=15,
        args=[application.bot, CHAT_ID],
        id='deadline_check',
    )

    scheduler.start()
    logger.info("Scheduler started — reminder tiap jam tepat, cek deadline tiap 15 menit")


def main() -> None:
    app = (
        Application.builder()
        .token(BOT_TOKEN)
        .post_init(post_init)
        .build()
    )

    app.add_handler(CommandHandler('start', start))
    app.add_handler(CommandHandler('id',    get_id))

    # Satu callback handler untuk semua tombol
    app.add_handler(CallbackQueryHandler(cb_handler))

    # Semua teks masuk ke any_message
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, any_message))

    logger.info("Bot polling...")
    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == '__main__':
    main()
