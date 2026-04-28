import logging
from datetime import datetime

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes, ConversationHandler

from database import add_job, get_active_jobs, get_job, update_status, archive_job
from utils import STATUS_MAP, format_job_list, hunter_link

logger = logging.getLogger(__name__)

# ─── Conversation states untuk /tambah ────────────────────────────────────────
HUNTER, GRUP, DESC, FEE, DEADLINE = range(5)

# Penyimpanan state sementara untuk input revisi deadline (key: user_id)
pending: dict = {}


# ─── /start & /id & /bantuan ──────────────────────────────────────────────────

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [
        [
            InlineKeyboardButton("➕ Tambah Job",   callback_data="menu_tambah"),
            InlineKeyboardButton("📋 List Job",     callback_data="menu_list"),
        ],
        [
            InlineKeyboardButton("🔄 Update Status", callback_data="menu_update"),
            InlineKeyboardButton("✅ Selesai/Lunas", callback_data="menu_selesai"),
        ],
        [
            InlineKeyboardButton("📖 Bantuan",       callback_data="menu_bantuan"),
        ],
    ]
    await update.message.reply_text(
        "👋 *Joki Tracker Bot*\n\nPilih menu:",
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode='Markdown'
    )


async def get_id(update: Update, context: ContextTypes.DEFAULT_TYPE):
    cid = update.effective_chat.id
    await update.message.reply_text(
        f"🆔 Chat ID kamu: `{cid}`\n\nSalin angka ini ke environment variable `CHAT_ID` di Railway.",
        parse_mode='Markdown'
    )


async def bantuan(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = (
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
        "⏰ Reminder otomatis setiap jam tepat\n"
        "🚨 Alert khusus jika deadline ≤ 3 jam"
    )
    keyboard = [[InlineKeyboardButton("🏠 Kembali ke Menu", callback_data="menu_home")]]
    if update.message:
        await update.message.reply_text(text, parse_mode='Markdown',
                                        reply_markup=InlineKeyboardMarkup(keyboard))
    else:
        await update.callback_query.edit_message_text(text, parse_mode='Markdown',
                                                       reply_markup=InlineKeyboardMarkup(keyboard))


# ─── Callback untuk tombol menu utama ─────────────────────────────────────────

async def cb_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    action = query.data  # menu_tambah, menu_list, dst

    if action == 'menu_home':
        keyboard = [
            [
                InlineKeyboardButton("➕ Tambah Job",    callback_data="menu_tambah"),
                InlineKeyboardButton("📋 List Job",      callback_data="menu_list"),
            ],
            [
                InlineKeyboardButton("🔄 Update Status", callback_data="menu_update"),
                InlineKeyboardButton("✅ Selesai/Lunas", callback_data="menu_selesai"),
            ],
            [
                InlineKeyboardButton("📖 Bantuan",        callback_data="menu_bantuan"),
            ],
        ]
        await query.edit_message_text(
            "👋 *Joki Tracker Bot*\n\nPilih menu:",
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode='Markdown'
        )

    elif action == 'menu_list':
        jobs = get_active_jobs()
        text = format_job_list(jobs)
        keyboard = [[InlineKeyboardButton("🏠 Kembali ke Menu", callback_data="menu_home")]]
        await query.edit_message_text(text, parse_mode='Markdown',
                                      reply_markup=InlineKeyboardMarkup(keyboard),
                                      disable_web_page_preview=True)

    elif action == 'menu_bantuan':
        await bantuan(update, context)

    elif action == 'menu_update':
        await _show_job_picker(query, action_type='update')

    elif action == 'menu_selesai':
        await _show_job_picker(query, action_type='selesai')

    elif action == 'menu_tambah':
        await query.edit_message_text(
            "📝 *Tambah Job Baru*\n\n"
            "Ketik /tambah untuk mulai mengisi data job.",
            parse_mode='Markdown',
            reply_markup=InlineKeyboardMarkup(
                [[InlineKeyboardButton("🏠 Kembali ke Menu", callback_data="menu_home")]]
            )
        )


async def _show_job_picker(query, action_type: str):
    """Tampilkan daftar job aktif sebagai tombol untuk dipilih."""
    if action_type == 'selesai':
        jobs = [j for j in get_active_jobs() if j['status'] == 'menunggu_payment']
        title = "💰 Pilih job yang sudah *lunas*:"
        empty_msg = "📭 Tidak ada job *Menunggu Payment* saat ini."
        prefix = 'done'
    else:
        jobs = get_active_jobs()
        title = "🔄 Pilih job yang ingin diupdate:"
        empty_msg = "📭 Tidak ada job aktif saat ini."
        prefix = 'job'

    if not jobs:
        await query.edit_message_text(
            empty_msg,
            parse_mode='Markdown',
            reply_markup=InlineKeyboardMarkup(
                [[InlineKeyboardButton("🏠 Kembali ke Menu", callback_data="menu_home")]]
            )
        )
        return

    keyboard = []
    for job in jobs:
        emoji = STATUS_MAP.get(job['status'], '❓').split()[0]
        desc_short = job['job_desc'][:20] + ('…' if len(job['job_desc']) > 20 else '')
        label = f"{emoji} #{job['id']} {job['hunter_name']} — {desc_short}"
        keyboard.append([InlineKeyboardButton(label, callback_data=f"{prefix}_{job['id']}")])

    keyboard.append([InlineKeyboardButton("🏠 Kembali ke Menu", callback_data="menu_home")])
    await query.edit_message_text(
        title,
        parse_mode='Markdown',
        reply_markup=InlineKeyboardMarkup(keyboard)
    )


# ─── /tambah — ConversationHandler ───────────────────────────────────────────

async def tambah_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data.clear()
    await update.message.reply_text(
        "📝 *Tambah Job Baru* (1/5)\n\n"
        "Masukkan *nomor WA hunter* (dengan kode negara, tanpa +):\n"
        "_Contoh: 6281234567890_\n\n"
        "Atau ketik /cancel untuk batal.",
        parse_mode='Markdown'
    )
    return HUNTER


async def tambah_hunter(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data['hunter_name'] = update.message.text.strip()
    await update.message.reply_text(
        "📝 *Tambah Job Baru* (2/5)\n\nDari grup WA mana?\n_Contoh: Grup Joki UI, Joki Jogja_",
        parse_mode='Markdown'
    )
    return GRUP


async def tambah_grup(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data['group_name'] = update.message.text.strip()
    await update.message.reply_text(
        "📝 *Tambah Job Baru* (3/5)\n\nKeterangan job-nya apa?\n_Contoh: Essay 5 halaman, PPT 10 slide_",
        parse_mode='Markdown'
    )
    return DESC


async def tambah_desc(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data['job_desc'] = update.message.text.strip()
    await update.message.reply_text(
        "📝 *Tambah Job Baru* (4/5)\n\nFee bersih kamu berapa?\n_Angka saja, contoh: 75000_",
        parse_mode='Markdown'
    )
    return FEE


async def tambah_fee(update: Update, context: ContextTypes.DEFAULT_TYPE):
    raw = update.message.text.strip().replace('.', '').replace(',', '')
    try:
        context.user_data['fee'] = int(raw)
        await update.message.reply_text(
            "📝 *Tambah Job Baru* (5/5)\n\nDeadline-nya kapan?\n"
            "Format: `DD/MM/YYYY HH:MM`\n"
            "_Contoh: 30/04/2025 18:00_",
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
        link = hunter_link(d['hunter_name'])

        keyboard = [
            [
                InlineKeyboardButton("🔄 Update Status", callback_data=f"job_{job_id}"),
                InlineKeyboardButton("📋 Lihat Semua",   callback_data="menu_list"),
            ],
            [InlineKeyboardButton("🏠 Menu Utama", callback_data="menu_home")],
        ]
        await update.message.reply_text(
            f"✅ *Job berhasil ditambahkan!*\n\n"
            f"🆔 ID: #{job_id}\n"
            f"👤 Hunter: {link}\n"
            f"📱 Grup: {d['group_name']}\n"
            f"📋 Job: {d['job_desc']}\n"
            f"💰 Fee: {fee_fmt}\n"
            f"⏰ Deadline: {d['deadline']}\n"
            f"📌 Status: 🟡 On Proses",
            parse_mode='Markdown',
            reply_markup=InlineKeyboardMarkup(keyboard),
            disable_web_page_preview=True
        )
        return ConversationHandler.END
    except ValueError:
        await update.message.reply_text(
            "❌ Format salah. Gunakan: `DD/MM/YYYY HH:MM`\n_Contoh: 30/04/2025 18:00_",
            parse_mode='Markdown'
        )
        return DEADLINE


async def tambah_cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data.clear()
    keyboard = [[InlineKeyboardButton("🏠 Menu Utama", callback_data="menu_home")]]
    await update.message.reply_text(
        "❌ Penambahan job dibatalkan.",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )
    return ConversationHandler.END


# ─── /list ────────────────────────────────────────────────────────────────────

async def list_jobs(update: Update, context: ContextTypes.DEFAULT_TYPE):
    jobs = get_active_jobs()
    text = format_job_list(jobs)
    keyboard = [
        [
            InlineKeyboardButton("🔄 Update Status", callback_data="menu_update"),
            InlineKeyboardButton("✅ Selesai/Lunas", callback_data="menu_selesai"),
        ],
        [InlineKeyboardButton("🏠 Menu Utama", callback_data="menu_home")],
    ]
    await update.message.reply_text(
        text,
        parse_mode='Markdown',
        reply_markup=InlineKeyboardMarkup(keyboard),
        disable_web_page_preview=True
    )


# ─── /update — pilih job lalu pilih status ────────────────────────────────────

async def update_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    jobs = get_active_jobs()
    if not jobs:
        await update.message.reply_text("📭 Tidak ada job aktif.")
        return

    keyboard = []
    for job in jobs:
        emoji = STATUS_MAP.get(job['status'], '❓').split()[0]
        desc_short = job['job_desc'][:20] + ('…' if len(job['job_desc']) > 20 else '')
        label = f"{emoji} #{job['id']} {job['hunter_name']} — {desc_short}"
        keyboard.append([InlineKeyboardButton(label, callback_data=f"job_{job['id']}")])

    keyboard.append([InlineKeyboardButton("🏠 Menu Utama", callback_data="menu_home")])
    await update.message.reply_text(
        "🔄 Pilih job yang ingin diupdate:",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )


async def cb_select_job(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    job_id = int(query.data.split('_')[1])
    job = get_job(job_id)
    if not job:
        await query.edit_message_text("❌ Job tidak ditemukan.")
        return

    current = STATUS_MAP.get(job['status'], '-')
    fee_fmt = f"Rp {job['fee']:,}".replace(',', '.')
    link = hunter_link(job['hunter_name'])

    keyboard = [
        [InlineKeyboardButton("🟡 On Proses",          callback_data=f"status_{job_id}_on_proses")],
        [InlineKeyboardButton("🔵 Menunggu Approval",  callback_data=f"status_{job_id}_menunggu_approval")],
        [InlineKeyboardButton("🔴 Sedang Direvisi",    callback_data=f"status_{job_id}_sedang_direvisi")],
        [InlineKeyboardButton("✅ Menunggu Payment",   callback_data=f"status_{job_id}_menunggu_payment")],
        [InlineKeyboardButton("🔙 Kembali",            callback_data="menu_update")],
    ]
    await query.edit_message_text(
        f"*Job #{job_id}*\n"
        f"👤 Hunter: {link}\n"
        f"📱 Grup: {job['group_name']}\n"
        f"📋 {job['job_desc']}\n"
        f"💰 {fee_fmt} | ⏰ {job['deadline']}\n"
        f"📌 Saat ini: {current}\n\n"
        f"Pilih status baru:",
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode='Markdown',
        disable_web_page_preview=True
    )


async def cb_set_status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    _, job_id_str, new_status = query.data.split('_', 2)
    job_id = int(job_id_str)

    if new_status == 'sedang_direvisi':
        pending[query.from_user.id] = {'action': 'revision_deadline', 'job_id': job_id}
        await query.edit_message_text(
            f"🔴 Job #{job_id} → *Sedang Direvisi*\n\n"
            f"Kirim deadline revisinya:\n`DD/MM/YYYY HH:MM`",
            parse_mode='Markdown'
        )
        return

    if new_status == 'menunggu_payment':
        done_at = datetime.now().strftime('%d/%m/%Y %H:%M')
        update_status(job_id, new_status, done_at=done_at)
        job = get_job(job_id)
        link = hunter_link(job['hunter_name'])
        keyboard = [
            [
                InlineKeyboardButton("📋 Lihat Semua", callback_data="menu_list"),
                InlineKeyboardButton("🏠 Menu Utama",  callback_data="menu_home"),
            ]
        ]
        await query.edit_message_text(
            f"✅ *Job #{job_id} — Menunggu Payment*\n\n"
            f"👤 Hunter: {link}\n"
            f"📱 Grup: {job['group_name']}\n"
            f"🕐 Done at: {done_at}",
            parse_mode='Markdown',
            reply_markup=InlineKeyboardMarkup(keyboard),
            disable_web_page_preview=True
        )
        return

    update_status(job_id, new_status)
    label = STATUS_MAP.get(new_status, new_status)
    keyboard = [
        [
            InlineKeyboardButton("📋 Lihat Semua", callback_data="menu_list"),
            InlineKeyboardButton("🏠 Menu Utama",  callback_data="menu_home"),
        ]
    ]
    await query.edit_message_text(
        f"✅ Status job #{job_id} diperbarui ke {label}",
        parse_mode='Markdown',
        reply_markup=InlineKeyboardMarkup(keyboard)
    )


# ─── /selesai — arsipkan job yang sudah lunas ─────────────────────────────────

async def selesai_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    jobs = [j for j in get_active_jobs() if j['status'] == 'menunggu_payment']
    if not jobs:
        await update.message.reply_text(
            "📭 Tidak ada job *Menunggu Payment*.\nUpdate status dulu lewat /update.",
            parse_mode='Markdown'
        )
        return

    keyboard = []
    for job in jobs:
        fee_fmt = f"Rp {job['fee']:,}".replace(',', '.')
        label = f"✅ #{job['id']} {job['hunter_name']} — {fee_fmt}"
        keyboard.append([InlineKeyboardButton(label, callback_data=f"done_{job['id']}")])

    keyboard.append([InlineKeyboardButton("🏠 Menu Utama", callback_data="menu_home")])
    await update.message.reply_text(
        "💰 Pilih job yang sudah *lunas* (akan diarsipkan):",
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
    link = hunter_link(job['hunter_name'])
    keyboard = [
        [
            InlineKeyboardButton("📋 Lihat Semua", callback_data="menu_list"),
            InlineKeyboardButton("🏠 Menu Utama",  callback_data="menu_home"),
        ]
    ]
    await query.edit_message_text(
        f"🎉 *Job #{job_id} lunas & diarsipkan!*\n\n"
        f"👤 Hunter: {link}\n"
        f"📱 Grup: {job['group_name']}\n"
        f"📋 Job: {job['job_desc']}\n"
        f"💰 Fee: {fee_fmt}\n"
        f"✔️ Done: {job['done_at']}",
        parse_mode='Markdown',
        reply_markup=InlineKeyboardMarkup(keyboard),
        disable_web_page_preview=True
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
            keyboard = [
                [
                    InlineKeyboardButton("📋 Lihat Semua", callback_data="menu_list"),
                    InlineKeyboardButton("🏠 Menu Utama",  callback_data="menu_home"),
                ]
            ]
            await update.message.reply_text(
                f"🔴 Job #{job_id} → *Sedang Direvisi*\n⏰ Deadline revisi: {dl_str}",
                parse_mode='Markdown',
                reply_markup=InlineKeyboardMarkup(keyboard)
            )
        except ValueError:
            await update.message.reply_text(
                "❌ Format salah. Gunakan: `DD/MM/YYYY HH:MM`\n_Contoh: 30/04/2025 20:00_",
                parse_mode='Markdown'
            )
