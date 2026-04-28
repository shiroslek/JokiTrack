import logging
from datetime import datetime

from database import get_active_jobs, get_near_deadline_jobs
from utils import format_job_list

logger = logging.getLogger(__name__)


async def send_hourly_reminder(bot, chat_id: str):
    """Kirim ringkasan semua job aktif setiap jam tepat."""
    jobs = get_active_jobs()
    if not jobs:
        return  # Tidak kirim apa-apa jika tidak ada job

    now_str = datetime.now().strftime('%d/%m/%Y %H:%M')
    header = f"⏰ *REMINDER — {now_str}*"
    text = format_job_list(jobs, title=header)

    try:
        await bot.send_message(chat_id=chat_id, text=text, parse_mode='Markdown')
    except Exception as e:
        logger.error(f"Gagal kirim hourly reminder: {e}")


async def check_deadlines(bot, chat_id: str):
    """Kirim alert khusus jika ada job dengan deadline ≤ 3 jam."""
    near = get_near_deadline_jobs(hours=3)
    if not near:
        return

    lines = ["🚨 *PERINGATAN DEADLINE!*\n"]
    for job, diff_secs in near:
        hours = int(diff_secs // 3600)
        mins = int((diff_secs % 3600) // 60)
        if hours > 0:
            time_str = f"{hours} jam {mins} menit"
        else:
            time_str = f"{mins} menit"

        dl_str = (
            job['revision_deadline']
            if job['status'] == 'sedang_direvisi' and job['revision_deadline']
            else job['deadline']
        )
        lines.append(
            f"⚠️ Job #{job['id']} sisa *{time_str}*\n"
            f"👤 {job['hunter_name']} | {job['job_desc']}\n"
            f"⏰ Deadline: {dl_str}\n"
        )

    try:
        await bot.send_message(chat_id=chat_id, text="\n".join(lines), parse_mode='Markdown')
    except Exception as e:
        logger.error(f"Gagal kirim deadline alert: {e}")
