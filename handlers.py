import logging
from datetime import datetime

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes, ConversationHandler

from database import add_job, get_active_jobs, get_job, update_status, archive_job
from utils import STATUS_MAP, format_job_list, hunter_link

logger = logging.getLogger(__name__)

# ─── Conversation states ───────────────────────────────────────────────────────
HUNTER, GRUP, DESC, FEE, DEADLINE = range(5)

# State sementara untuk input revision deadline
pending: dict = {}


# ─── Keyboard helper ──────────────────────────────────────────────────────────

def kb_home():
    return InlineKeyboardMarkup([[
        InlineKeyboardButton("🏠 Menu Utama", callback_data="menu_home")
    ]])


def kb_home_list():
    return InlineKeyboardMarkup([[
        InlineKeyboardButton("📋 Lihat Semua", callback_data="menu_list"),
        InlineKeyboardButton("🏠 Menu Utama",  callback_data="menu_home"),
    ]])


def kb_main_menu():
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("➕ Tambah Job",    callback_data="menu_tambah"),
            InlineKeyboardButton("📋 List Job",      callback_data="menu_list"),
        ],
        [
            InlineKeyboardButton("🔄 Update Status", callback_data="menu_update"),
            InlineKeyboardButton("✅ Selesai/Lunas", callback_data="menu_selesai"),
        ],
        [
            InlineKeyboardButton("📖 Bantuan",       callback_data="menu_bantuan"),
        ],
    ])


# ─── Tampilkan menu utama (dipakai di banyak tempat) ─────────────────────────

async def show_main_menu(target, edit=False):
    text = (
        "👋 *Joki Tracker Bot*\n\n"
        "Pilih menu di bawah:"
    )
    if edit:
        await target.edit_message_text(text, parse_mode='Markdown',
                                       reply_markup=kb_main_menu())
    else:
        await target.reply_text(text, parse_mode='Markdown',
                                reply_markup=kb_main_menu())


# ─── Entry point — semua pesan teks saat tidak dalam conversation ─────────────

async def any_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Tangkap pesan teks apapun → routing ke form/pending/menu."""
    user_id = update.effective_user.id
    # Sedang isi form tambah job atau input revision deadline → teruskan ke handler
    if user_id in pending or context.user_data.get('conv_state') is not None:
        await handle_free_text(update, context)
        return
    await show_main_menu(update.message)


# ─── /start & /id ─────────────────────────────────────────────────────────────

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await show_main_menu(update.message)


async def get_id(update: Update, context: ContextTypes.DEFAULT_TYPE):
    cid = update.effective_chat.id
    await update.message.reply_text(
        f"🆔 Chat ID kamu: `{cid}`\n\nSalin angka ini ke variable `CHAT_ID` di Railway.",
        parse_mode='Markdown',
        reply_markup=kb_home()
    )


# ─── Callback utama — semua tombol menu ───────────────────────────────────────

async def cb_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    action = query.data

    # ── Menu Utama ──
    if action == 'menu_home':
        await show_main_menu(query, edit=True)

    # ── List Job ──
    elif action == 'menu_list':
        jobs = get_active_jobs()
        text = format_job_list(jobs)
        keyboard = InlineKeyboardMarkup([
            [
                InlineKeyboardButton("🔄 Update Status", callback_data="menu_update"),
                InlineKeyboardButton("✅ Selesai/Lunas", callback_data="menu_selesai"),
            ],
            [InlineKeyboardButton("🏠 Menu Utama", callback_data="menu_home")],
        ])
        await query.edit_message_text(text, parse_mode='Markdown',
                                      reply_markup=keyboard,
                                      disable_web_page_preview=True)

    # ── Bantuan ──
    elif action == 'menu_bantuan':
        text = (
            "📖 *Panduan Bot Joki Tracker*\n\n"
            "*Alur kerja:*\n"
            "1⃣ Deal dengan hunter → Tambah Job\n"
            "2⃣ Kirim hasil → Update → Menunggu Approval\n"
            "3⃣ Ada revisi → Update → Sedang Direvisi\n"
            "4⃣ Acc → Update → Menunggu Payment\n"
            "5⃣ Uang masuk → Selesai/Lunas\n\n"
            "*Status:*\n"
            "🟡 On Proses — Deal, lagi dikerjain\n"
            "🔵 Menunggu Approval — Sudah kirim\n"
            "🔴 Sedang Direvisi — Ada revisi\n"
            "✅ Menunggu Payment — Tinggal nunggu bayar\n\n"
            "⏰ Reminder otomatis setiap jam tepat\n"
            "🚨 Alert khusus jika deadline ≤ 3 jam"
        )
        await query.edit_message_text(text, parse_mode='Markdown',
                                      reply_markup=kb_home())

    # ── Tambah Job (entry point conversation via tombol) ──
    elif action == 'menu_tambah':
        context.user_data.clear()
        await query.edit_message_text(
            "📝 *Tambah Job Baru* — (1/5)\n\n"
            "Ketik *nomor WA* atau *nama* hunter:\n"
            "_Contoh nomor: +62 831-6896-8059_\n"
            "_Contoh nama: Budi_",
            parse_mode='Markdown',
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("❌ Batal", callback_data="tambah_cancel")
            ]])
        )
        context.user_data['conv_state'] = HUNTER

    # ── Batal tambah ──
    elif action == 'tambah_cancel':
        context.user_data.clear()
        await show_main_menu(query, edit=True)

    # ── Update status ──
    elif action == 'menu_update':
        await _show_job_picker(query, action_type='update')

    # ── Selesai/Lunas ──
    elif action == 'menu_selesai':
        await _show_job_picker(query, action_type='selesai')


async def _show_job_picker(query, action_type: str):
    if action_type == 'selesai':
        jobs = [j for j in get_active_jobs() if j['status'] == 'menunggu_payment']
        title = "💰 *Pilih job yang sudah lunas:*"
        empty_msg = "📭 Tidak ada job *Menunggu Payment* saat ini."
        prefix = 'done'
    else:
        jobs = get_active_jobs()
        title = "🔄 *Pilih job yang ingin diupdate:*"
        empty_msg = "📭 Tidak ada job aktif saat ini."
        prefix = 'job'

    if not jobs:
        await query.edit_message_text(empty_msg, parse_mode='Markdown',
                                      reply_markup=kb_home())
        return

    keyboard = []
    for job in jobs:
        emoji = STATUS_MAP.get(job['status'], '❓').split()[0]
        desc_short = job['job_desc'][:22] + ('…' if len(job['job_desc']) > 22 else '')
        label = f"{emoji} #{job['id']} {job['hunter_name']} — {desc_short}"
        keyboard.append([InlineKeyboardButton(label, callback_data=f"{prefix}_{job['id']}")])

    keyboard.append([InlineKeyboardButton("🏠 Menu Utama", callback_data="menu_home")])
    await query.edit_message_text(title, parse_mode='Markdown',
                                  reply_markup=InlineKeyboardMarkup(keyboard))


# ─── Callback: pilih job untuk update ─────────────────────────────────────────

async def cb_select_job(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    job_id = int(query.data.split('_')[1])
    job = get_job(job_id)
    if not job:
        await query.edit_message_text("❌ Job tidak ditemukan.", reply_markup=kb_home())
        return

    current = STATUS_MAP.get(job['status'], '-')
    fee_fmt = f"Rp {job['fee']:,}".replace(',', '.')
    link = hunter_link(job['hunter_name'])

    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("🟡 On Proses",          callback_data=f"status_{job_id}_on_proses")],
        [InlineKeyboardButton("🔵 Menunggu Approval",  callback_data=f"status_{job_id}_menunggu_approval")],
        [InlineKeyboardButton("🔴 Sedang Direvisi",    callback_data=f"status_{job_id}_sedang_direvisi")],
        [InlineKeyboardButton("✅ Menunggu Payment",   callback_data=f"status_{job_id}_menunggu_payment")],
        [InlineKeyboardButton("🔙 Kembali",            callback_data="menu_update")],
    ])
    await query.edit_message_text(
        f"*Job #{job_id}*\n"
        f"👤 Hunter: {link}\n"
        f"📱 Grup: {job['group_name']}\n"
        f"📋 {job['job_desc']}\n"
        f"💰 {fee_fmt} | ⏰ {job['deadline']}\n"
        f"📌 Status: {current}\n\n"
        f"Pilih status baru:",
        reply_markup=keyboard,
        parse_mode='Markdown',
        disable_web_page_preview=True
    )


# ─── Callback: set status baru ────────────────────────────────────────────────

async def cb_set_status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    _, job_id_str, new_status = query.data.split('_', 2)
    job_id = int(job_id_str)

    if new_status == 'sedang_direvisi':
        pending[query.from_user.id] = {'action': 'revision_deadline', 'job_id': job_id}
        await query.edit_message_text(
            f"🔴 Job #{job_id} → *Sedang Direvisi*\n\n"
            f"Ketik deadline revisinya:\n`DD/MM/YYYY HH:MM`\n"
            f"_Contoh: 30/04/2025 20:00_",
            parse_mode='Markdown'
        )
        return

    if new_status == 'menunggu_payment':
        done_at = datetime.now().strftime('%d/%m/%Y %H:%M')
        update_status(job_id, new_status, done_at=done_at)
        job = get_job(job_id)
        link = hunter_link(job['hunter_name'])
        await query.edit_message_text(
            f"✅ *Job #{job_id} — Menunggu Payment*\n\n"
            f"👤 Hunter: {link}\n"
            f"📱 Grup: {job['group_name']}\n"
            f"🕐 Done at: {done_at}",
            parse_mode='Markdown',
            reply_markup=kb_home_list(),
            disable_web_page_preview=True
        )
        return

    update_status(job_id, new_status)
    label = STATUS_MAP.get(new_status, new_status)
    await query.edit_message_text(
        f"✅ Status job #{job_id} diperbarui ke {label}",
        parse_mode='Markdown',
        reply_markup=kb_home_list()
    )


# ─── Callback: arsipkan job lunas ─────────────────────────────────────────────

async def cb_done(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    job_id = int(query.data.split('_')[1])
    job = get_job(job_id)
    archive_job(job_id)

    fee_fmt = f"Rp {job['fee']:,}".replace(',', '.')
    link = hunter_link(job['hunter_name'])
    await query.edit_message_text(
        f"🎉 *Job #{job_id} lunas & diarsipkan!*\n\n"
        f"👤 Hunter: {link}\n"
        f"📱 Grup: {job['group_name']}\n"
        f"📋 Job: {job['job_desc']}\n"
        f"💰 Fee: {fee_fmt}\n"
        f"✔️ Done: {job['done_at']}",
        parse_mode='Markdown',
        reply_markup=kb_home_list(),
        disable_web_page_preview=True
    )


# ─── Text handler — untuk input form tambah & revision deadline ───────────────

async def handle_free_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id

    # ── Revision deadline ──
    if user_id in pending:
        state = pending[user_id]
        if state['action'] == 'revision_deadline':
            dl_str = update.message.text.strip()
            try:
                datetime.strptime(dl_str, '%d/%m/%Y %H:%M')
                job_id = state['job_id']
                update_status(job_id, 'sedang_direvisi', revision_deadline=dl_str)
                del pending[user_id]
                await update.message.reply_text(
                    f"🔴 Job #{job_id} → *Sedang Direvisi*\n⏰ Deadline revisi: {dl_str}",
                    parse_mode='Markdown',
                    reply_markup=kb_home_list()
                )
            except ValueError:
                await update.message.reply_text(
                    "❌ Format salah. Ketik lagi:\n`DD/MM/YYYY HH:MM`",
                    parse_mode='Markdown'
                )
        return

    # ── Form tambah job (state machine manual via user_data) ──
    state = context.user_data.get('conv_state')
    if state is None:
        await show_main_menu(update.message)
        return

    text = update.message.text.strip()

    cancel_kb = InlineKeyboardMarkup([[
        InlineKeyboardButton("❌ Batal", callback_data="tambah_cancel")
    ]])

    if state == HUNTER:
        context.user_data['hunter_name'] = text
        context.user_data['conv_state'] = GRUP
        await update.message.reply_text(
            "📝 *Tambah Job Baru* — (2/5)\n\nDari grup WA mana?\n_Contoh: Grup Joki UI_",
            parse_mode='Markdown', reply_markup=cancel_kb
        )

    elif state == GRUP:
        context.user_data['group_name'] = text
        context.user_data['conv_state'] = DESC
        await update.message.reply_text(
            "📝 *Tambah Job Baru* — (3/5)\n\nKeterangan job?\n_Contoh: Essay 5 hal, PPT 10 slide_",
            parse_mode='Markdown', reply_markup=cancel_kb
        )

    elif state == DESC:
        context.user_data['job_desc'] = text
        context.user_data['conv_state'] = FEE
        await update.message.reply_text(
            "📝 *Tambah Job Baru* — (4/5)\n\nFee bersih kamu?\n_Angka saja, contoh: 75000_",
            parse_mode='Markdown', reply_markup=cancel_kb
        )

    elif state == FEE:
        raw = text.replace('.', '').replace(',', '')
        try:
            context.user_data['fee'] = int(raw)
            context.user_data['conv_state'] = DEADLINE
            await update.message.reply_text(
                "📝 *Tambah Job Baru* — (5/5)\n\nDeadline-nya kapan?\n"
                "Format: `DD/MM/YYYY HH:MM`\n_Contoh: 30/04/2025 18:00_",
                parse_mode='Markdown', reply_markup=cancel_kb
            )
        except ValueError:
            await update.message.reply_text("❌ Harus berupa angka. Coba lagi:",
                                            reply_markup=cancel_kb)

    elif state == DEADLINE:
        try:
            datetime.strptime(text, '%d/%m/%Y %H:%M')
            context.user_data['deadline'] = text

            d = context.user_data
            job_id = add_job(d['hunter_name'], d['group_name'],
                             d['job_desc'], d['fee'], d['deadline'])
            context.user_data.clear()

            fee_fmt = f"Rp {d['fee']:,}".replace(',', '.')
            link = hunter_link(d['hunter_name'])

            keyboard = InlineKeyboardMarkup([
                [
                    InlineKeyboardButton("🔄 Update Status", callback_data=f"job_{job_id}"),
                    InlineKeyboardButton("📋 Lihat Semua",   callback_data="menu_list"),
                ],
                [InlineKeyboardButton("🏠 Menu Utama", callback_data="menu_home")],
            ])
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
                reply_markup=keyboard,
                disable_web_page_preview=True
            )
        except ValueError:
            await update.message.reply_text(
                "❌ Format salah. Ketik lagi:\n`DD/MM/YYYY HH:MM`",
                parse_mode='Markdown', reply_markup=cancel_kb
            )
