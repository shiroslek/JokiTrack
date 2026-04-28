import logging
from datetime import datetime

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes, ConversationHandler

from database import add_job, get_active_jobs, get_job, update_status, archive_job
from utils import STATUS_MAP, format_job_list

logger = logging.getLogger(__name__)

# ─── Conversation states untuk /tambah ────────────────────────────────────────
HUNTER, GRUP, DESC, FEE, DEADLINE = range(5)

# Penyimpanan state sementara untuk input revisi deadline (key: user_id)
# Format: {user_id: {'action': str, 'job_id': int}}
pending: dict = {}


# ─── /start & /id & /bantuan ──────────────────────────────────────────────────

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "👋 *Bot Joki Tracker aktif!*\n\n"
        "📌 Perintah:\n"
        "/tambah — Tambah job baru\n"
        "/list — Lihat semua job aktif\n"
        "/update — Update status job\n"
        "/selesai — Arsipkan job yang sudah dibayar\n"
        "/id — Lihat Chat ID kamu\n"
        "/bantuan — Panduan lengkap",
        parse_mode='Markdown'
    )


async def get_id(update: Update, context: ContextTypes.DEFAULT_TYPE):
    cid = update.effective_chat.id
    await update.message.reply_text(
        f"🆔 Chat ID kamu: `{cid}`\n\nSalin angka ini ke environment variable `CHAT_ID` di Railway.",
        parse_mode='Markdown'
    )


async def bantuan(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "📖 *Panduan Bot Joki Tracker*\n\n"
        "*Alur kerja:*\n"
        "1. Deal dengan hunter → /tambah\n"
        "2. Kirim hasil → /update → Menunggu Approval\n"
        "3. Ada revisi → /update → Sedang Direvisi\n"
        "4. Acc → /update → Menunggu Payment\n"
        "5. Uang masuk → /selesai\n\n"
        "*Status:*\n"
        "🟡 On Proses — Deal, lagi dikerjain\n"
        "🔵 Menunggu Approval — Sudah kirim, nunggu konfirmasi\n"
        "🔴 Sedang Direvisi — Ada revisi dari hunter\n"
        "✅ Menunggu Payment — Clear, tinggal nunggu bayar\n\n"
        "⏰ Reminder otomatis setiap jam tepat (07:00, 08:00, dst)\n"
        "🚨 Alert khusus jika deadline ≤ 3 jam",
        parse_mode='Markdown'
    )


# ─── /tambah — ConversationHandler ───────────────────────────────────────────

async def tambah_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data.clear()
    await update.message.reply_text(
        "📝 *Tambah Job Baru*\n\n"
        "Langkah 1/5 — Masukkan nama atau nomor hunter:",
        parse_mode='Markdown'
    )
    return HUNTER


async def tambah_hunter(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data['hunter_name'] = update.message.text.strip()
    await update.message.reply_text("Langkah 2/5 — Dari grup WA mana?\n_(contoh: Grup Joki UI, Joki Jogja)_",
                                    parse_mode='Markdown')
    return GRUP


async def tambah_grup(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data['group_name'] = update.message.text.strip()
    await update.message.reply_text("Langkah 3/5 — Keterangan job-nya apa?\n_(contoh: Essay 5 halaman, PPT 10 slide)_",
                                    parse_mode='Markdown')
    return DESC


async def tambah_desc(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data['job_desc'] = update.message.text.strip()
    await update.message.reply_text("Langkah 4/5 — Fee bersih kamu berapa?\n_(angka saja, contoh: 75000)_",
                                    parse_mode='Markdown')
    return FEE


async def tambah_fee(update: Update, context: ContextTypes.DEFAULT_TYPE):
    raw = update.message.text.strip().replace('.', '').replace(',', '')
    try:
        context.user_data['fee'] = int(raw)
        await update.message.reply_text(
            "Langkah 5/5 — Deadline-nya kapan?\n"
            "Format: `DD/MM/YYYY HH:MM`\n"
            "Contoh: `30/04/2025 18:00`",
            parse_mode='Markdown'
        )
        return DEADLINE
    except ValueError:
        await update.message.reply_text("❌ Harus berupa angka. Coba lagi:")
        return FEE


async def tambah_deadline(update: Update, context: ContextTypes.DEFAULT_TYPE):
    dl_str = update.message.text.strip()
    try:
        datetime.strptime(dl_str, '%d/%m/%Y %H:%M')
        context.user_data['deadline'] = dl_str

        d = context.user_data
        job_id = add_job(d['hunter_name'], d['group_name'], d['job_desc'], d['fee'], d['deadline'])

        fee_fmt = f"Rp {d['fee']:,}".replace(',', '.')
        await update.message.reply_text(
            f"✅ *Job berhasil ditambahkan!*\n\n"
            f"🆔 ID: #{job_id}\n"
            f"👤 Hunter: {d['hunter_name']}\n"
            f"📱 Grup: {d['group_name']}\n"
            f"📋 Job: {d['job_desc']}\n"
            f"💰 Fee: {fee_fmt}\n"
            f"⏰ Deadline: {d['deadline']}\n"
            f"📌 Status: 🟡 On Proses",
            parse_mode='Markdown'
        )
        return ConversationHandler.END
    except ValueError:
        await update.message.reply_text(
            "❌ Format salah. Gunakan: `DD/MM/YYYY HH:MM`\nContoh: `30/04/2025 18:00`",
            parse_mode='Markdown'
        )
        return DEADLINE


async def tambah_cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data.clear()
    await update.message.reply_text("❌ Penambahan job dibatalkan.")
    return ConversationHandler.END


# ─── /list ────────────────────────────────────────────────────────────────────

async def list_jobs(update: Update, context: ContextTypes.DEFAULT_TYPE):
    jobs = get_active_jobs()
    text = format_job_list(jobs)
    await update.message.reply_text(text, parse_mode='Markdown')


# ─── /update — pilih job lalu pilih status ────────────────────────────────────

async def update_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    jobs = get_active_jobs()
    if not jobs:
        await update.message.reply_text("📭 Tidak ada job aktif.")
        return

    keyboard = []
    for job in jobs:
        emoji = STATUS_MAP.get(job['status'], '❓').split()[0]
        desc_short = job['job_desc'][:22] + ('…' if len(job['job_desc']) > 22 else '')
        label = f"{emoji} #{job['id']} {job['hunter_name']} – {desc_short}"
        keyboard.append([InlineKeyboardButton(label, callback_data=f"job_{job['id']}")])

    await update.message.reply_text(
        "Pilih job yang ingin diupdate statusnya:",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )


async def cb_select_job(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Callback: user memilih job → tampilkan pilihan status"""
    query = update.callback_query
    await query.answer()

    job_id = int(query.data.split('_')[1])
    job = get_job(job_id)
    if not job:
        await query.edit_message_text("❌ Job tidak ditemukan.")
        return

    current = STATUS_MAP.get(job['status'], '-')
    fee_fmt = f"Rp {job['fee']:,}".replace(',', '.')

    keyboard = [
        [InlineKeyboardButton("🟡 On Proses",          callback_data=f"status_{job_id}_on_proses")],
        [InlineKeyboardButton("🔵 Menunggu Approval",  callback_data=f"status_{job_id}_menunggu_approval")],
        [InlineKeyboardButton("🔴 Sedang Direvisi",    callback_data=f"status_{job_id}_sedang_direvisi")],
        [InlineKeyboardButton("✅ Menunggu Payment",   callback_data=f"status_{job_id}_menunggu_payment")],
    ]
    await query.edit_message_text(
        f"*Job #{job_id}*\n"
        f"👤 {job['hunter_name']} | {job['group_name']}\n"
        f"📋 {job['job_desc']}\n"
        f"💰 {fee_fmt} | ⏰ {job['deadline']}\n"
        f"📌 Saat ini: {current}\n\n"
        f"Pilih status baru:",
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode='Markdown'
    )


async def cb_set_status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Callback: user memilih status baru → update DB"""
    query = update.callback_query
    await query.answer()

    # Format callback_data: status_<job_id>_<status_key>
    _, job_id_str, new_status = query.data.split('_', 2)
    job_id = int(job_id_str)

    if new_status == 'sedang_direvisi':
        # Simpan state, minta input deadline revisi via teks biasa
        pending[query.from_user.id] = {'action': 'revision_deadline', 'job_id': job_id}
        await query.edit_message_text(
            f"🔴 Job #{job_id} akan diset *Sedang Direvisi*.\n\n"
            f"Kirim deadline revisinya:\nFormat: `DD/MM/YYYY HH:MM`",
            parse_mode='Markdown'
        )
        return

    if new_status == 'menunggu_payment':
        done_at = datetime.now().strftime('%d/%m/%Y %H:%M')
        update_status(job_id, new_status, done_at=done_at)
        job = get_job(job_id)
        await query.edit_message_text(
            f"✅ Job #{job_id} sekarang *Menunggu Payment*\n"
            f"👤 Hunter: {job['hunter_name']}\n"
            f"📱 Grup: {job['group_name']}\n"
            f"🕐 Done at: {done_at}",
            parse_mode='Markdown'
        )
        return

    update_status(job_id, new_status)
    label = STATUS_MAP.get(new_status, new_status)
    await query.edit_message_text(
        f"✅ Status job #{job_id} diperbarui ke {label}",
        parse_mode='Markdown'
    )


# ─── /selesai — arsipkan job yang sudah lunas ─────────────────────────────────

async def selesai_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    jobs = [j for j in get_active_jobs() if j['status'] == 'menunggu_payment']
    if not jobs:
        await update.message.reply_text(
            "📭 Tidak ada job dengan status *Menunggu Payment*.\n"
            "Update status job dulu lewat /update.",
            parse_mode='Markdown'
        )
        return

    keyboard = []
    for job in jobs:
        fee_fmt = f"Rp {job['fee']:,}".replace(',', '.')
        label = f"✅ #{job['id']} {job['hunter_name']} – {fee_fmt}"
        keyboard.append([InlineKeyboardButton(label, callback_data=f"done_{job['id']}")])

    await update.message.reply_text(
        "Pilih job yang sudah *lunas* (akan diarsipkan):",
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode='Markdown'
    )


async def cb_done(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    job_id = int(query.data.split('_')[1])
    job = get_job(job_id)
    archive_job(job_id)

    fee_fmt = f"Rp {job['fee']:,}".replace(',', '.')
    await query.edit_message_text(
        f"🎉 *Job #{job_id} sudah lunas & diarsipkan!*\n\n"
        f"👤 Hunter: {job['hunter_name']}\n"
        f"📱 Grup: {job['group_name']}\n"
        f"📋 Job: {job['job_desc']}\n"
        f"💰 Fee: {fee_fmt}\n"
        f"✔️ Done: {job['done_at']}",
        parse_mode='Markdown'
    )


# ─── Message handler untuk input pending (revision deadline) ──────────────────

async def handle_free_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if user_id not in pending:
        return

    state = pending[user_id]

    if state['action'] == 'revision_deadline':
        dl_str = update.message.text.strip()
        try:
            datetime.strptime(dl_str, '%d/%m/%Y %H:%M')
            job_id = state['job_id']
            update_status(job_id, 'sedang_direvisi', revision_deadline=dl_str)
            del pending[user_id]
            await update.message.reply_text(
                f"🔴 Job #{job_id} diset *Sedang Direvisi*\n⏰ Deadline revisi: {dl_str}",
                parse_mode='Markdown'
            )
        except ValueError:
            await update.message.reply_text(
                "❌ Format salah. Gunakan: `DD/MM/YYYY HH:MM`\nContoh: `30/04/2025 20:00`",
                parse_mode='Markdown'
            )
