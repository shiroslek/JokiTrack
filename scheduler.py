import logging
from datetime import datetime
import pytz

from database import get_active_jobs, get_near_deadline_jobs
from utils import format_job_list

logger = logging.getLogger(__name__)
WITA = pytz.timezone('Asia/Makassar')

def now_wita():
    return datetime.now(tz=WITA).replace(tzinfo=None)


async def send_hourly_reminder(bot, chat_id: str):
    """Kirim laporan job lengkap setiap jam tepat."""
    jobs = get_active_jobs()
    now_str = now_wita().strftime('%d/%m/%Y %H:%M')

    if not jobs:
        # Tetap kirim notif kosong agar user tahu bot jalan
        try:
            await bot.send_message(
                chat_id=chat_id,
                text=f"⏰ *Reminder — {now_str}*\n\n📭 Tidak ada job aktif saat ini.",
                parse_mode='Markdown'
            )
        except Exception as e:
            logger.error(f"Gagal kirim reminder kosong: {e}")
        return

    title  = f"⏰ *Reminder — {now_str}*"
    text   = format_job_list(jobs, title=title)

    try:
        await bot.send_message(
            chat_id=chat_id,
            text=text,
            parse_mode='Markdown',
            disable_web_page_preview=True
        )
    except Exception as e:
        logger.error(f"Gagal kirim hourly reminder: {e}")


async def check_deadlines(bot, chat_id: str):
    """Kirim alert khusus jika ada job dengan deadline <= 3 jam."""
    near = get_near_deadline_jobs(hours=3)
    if not near:
        return

    now_str = now_wita().strftime('%H:%M')
    lines   = [f"🚨 *ALERT DEADLINE — {now_str}*\n"]

    for job, diff_secs in sorted(near, key=lambda x: x[1]):
        h = int(diff_secs // 3600)
        m = int((diff_secs % 3600) // 60)
        sisa = f"{h} jam {m} mnt" if h else f"{m} mnt"

        dl_str = (
            job['revision_deadline']
            if job['status'] == 'sedang_direvisi' and job['revision_deadline']
            else job['deadline']
        )
        lines.append(
            f"⚠️ *#{job['id']}* {job['hunter_name']}\n"
            f"   📋 {job['job_desc']}\n"
            f"   ⏰ {dl_str} — sisa *{sisa}*\n"
        )

    try:
        await bot.send_message(
            chat_id=chat_id,
            text="\n".join(lines),
            parse_mode='Markdown',
            disable_web_page_preview=True
        )
    except Exception as e:
        logger.error(f"Gagal kirim deadline alert: {e}")
