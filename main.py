import os
import logging

from telegram import Update
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    ConversationHandler,
    filters,
)
from apscheduler.schedulers.asyncio import AsyncIOScheduler

from database import init_db
from handlers import (
    # Commands
    start, get_id, bantuan,
    list_jobs, update_start, selesai_start,
    # Tambah conversation
    tambah_start, tambah_hunter, tambah_grup,
    tambah_desc, tambah_fee, tambah_deadline, tambah_cancel,
    # Callbacks
    cb_select_job, cb_set_status, cb_done,
    # Free text handler
    handle_free_text,
    # States
    HUNTER, GRUP, DESC, FEE, DEADLINE,
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
    """Dipanggil setelah Application siap — inisialisasi DB & scheduler."""
    init_db()
    logger.info("Database initialized")

    scheduler = AsyncIOScheduler(timezone='Asia/Makassar')  # WITA (UTC+8)

    # Reminder setiap jam tepat
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
    logger.info("Scheduler started — reminder tiap jam, deadline check tiap 15 menit")


def main() -> None:
    # ConversationHandler untuk /tambah
    tambah_conv = ConversationHandler(
        entry_points=[CommandHandler('tambah', tambah_start)],
        states={
            HUNTER:   [MessageHandler(filters.TEXT & ~filters.COMMAND, tambah_hunter)],
            GRUP:     [MessageHandler(filters.TEXT & ~filters.COMMAND, tambah_grup)],
            DESC:     [MessageHandler(filters.TEXT & ~filters.COMMAND, tambah_desc)],
            FEE:      [MessageHandler(filters.TEXT & ~filters.COMMAND, tambah_fee)],
            DEADLINE: [MessageHandler(filters.TEXT & ~filters.COMMAND, tambah_deadline)],
        },
        fallbacks=[CommandHandler('cancel', tambah_cancel)],
        allow_reentry=True,
    )

    app = (
        Application.builder()
        .token(BOT_TOKEN)
        .post_init(post_init)
        .build()
    )

    # Command handlers
    app.add_handler(CommandHandler('start',    start))
    app.add_handler(CommandHandler('id',       get_id))
    app.add_handler(CommandHandler('bantuan',  bantuan))
    app.add_handler(CommandHandler('list',     list_jobs))
    app.add_handler(CommandHandler('update',   update_start))
    app.add_handler(CommandHandler('selesai',  selesai_start))

    # Conversation handler
    app.add_handler(tambah_conv)

    # Callback query handlers (urutan penting — lebih spesifik dulu)
    app.add_handler(CallbackQueryHandler(cb_select_job, pattern=r'^job_\d+$'))
    app.add_handler(CallbackQueryHandler(cb_set_status,  pattern=r'^status_'))
    app.add_handler(CallbackQueryHandler(cb_done,        pattern=r'^done_\d+$'))

    # Free text handler (untuk input revision deadline)
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_free_text))

    logger.info("Bot mulai polling...")
    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == '__main__':
    main()
