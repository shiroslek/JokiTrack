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
from handlers import (
    start, get_id,
    any_message, handle_free_text,
    cb_menu, cb_select_job, cb_set_status, cb_done,
)
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

    # Reminder setiap jam tepat (menit=0)
    scheduler.add_job(
        send_hourly_reminder,
        trigger='cron',
        minute=0,
        args=[application.bot, CHAT_ID],
        id='hourly_reminder',
    )

    # Cek deadline setiap 15 menit
    scheduler.add_job(
        check_deadlines,
        trigger='interval',
        minutes=15,
        args=[application.bot, CHAT_ID],
        id='deadline_check',
    )

    scheduler.start()
    logger.info("Scheduler started — reminder tiap jam tepat, deadline check tiap 15 menit")


def main() -> None:
    app = (
        Application.builder()
        .token(BOT_TOKEN)
        .post_init(post_init)
        .build()
    )

    # /start dan /id tetap ada sebagai fallback
    app.add_handler(CommandHandler('start', start))
    app.add_handler(CommandHandler('id',    get_id))

    # Callback handlers — urutan: spesifik dulu
    app.add_handler(CallbackQueryHandler(cb_select_job, pattern=r'^job_\d+$'))
    app.add_handler(CallbackQueryHandler(cb_set_status, pattern=r'^status_'))
    app.add_handler(CallbackQueryHandler(cb_done,       pattern=r'^done_\d+$'))
    app.add_handler(CallbackQueryHandler(cb_menu,       pattern=r'^menu_|^tambah_cancel$'))

    # Semua teks → handle_free_text (form input) atau tampilkan menu utama
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, any_message))

    logger.info("Bot mulai polling...")
    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == '__main__':
    main()
