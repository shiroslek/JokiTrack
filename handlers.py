import logging
from datetime import datetime
import pytz

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes

from database import add_job, get_active_jobs, get_job, update_status, archive_job, delete_job
from utils import STATUS_MAP, format_job_list, hunter_link, parse_deadline, normalize_wa_number

logger = logging.getLogger(__name__)

WITA = pytz.timezone('Asia/Makassar')
def now_wita():
    return datetime.now(tz=WITA).replace(tzinfo=None)

# State keys di context.user_data
FORM_STATE  = 'form_state'
FORM_DATA   = 'form_data'

# State values
S_HUNTER   = 'hunter'
S_GRUP     = 'grup'
S_DESC     = 'desc'
S_FEE      = 'fee'
S_DEADLINE = 'deadline'

# State untuk input teks non-form
PENDING_STATE = 'pending_state'   # {'action': str, 'job_id': int}

# ─── Keyboard helpers ─────────────────────────────────────────────────────────

def kb(*rows):
    return InlineKeyboardMarkup(list(rows))

def row(*btns):
    return list(btns)

def btn(text, data):
    return InlineKeyboardButton(text, callback_data=data)

KB_HOME  = kb(row(btn("🏠 Menu Utama", "menu_home")))
KB_BACK_HOME = kb(
    row(btn("📋 Lihat List", "menu_list"), btn("🏠 Menu Utama", "menu_home"))
)

def kb_main():
    return kb(
        row(btn("➕ Tambah Job",    "menu_tambah"),
            btn("📋 List Job",      "menu_list")),
        row(btn("🔄 Update Status", "menu_update"),
            btn("🗑️ Hapus Job",     "menu_hapus")),
        row(btn("✅ Selesai/Lunas", "menu_selesai"),
            btn("📖 Bantuan",       "menu_bantuan")),
    )


# ─── Teks menu utama ──────────────────────────────────────────────────────────

MAIN_TEXT = "👋 *Joki Tracker Bot*\n\nPilih menu:"


async def _edit_or_reply(update, text, keyboard, preview=False):
    """Edit message jika callback query, reply jika message biasa."""
    if update.callback_query:
        await update.callback_query.edit_message_text(
            text, parse_mode='Markdown',
            reply_markup=keyboard,
            disable_web_page_preview=not preview
        )
    else:
        await update.message.reply_text(
            text, parse_mode='Markdown',
            reply_markup=keyboard,
            disable_web_page_preview=not preview
        )


# ─── /start ──────────────────────────────────────────────────────────────────

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data.clear()
    await update.message.reply_text(MAIN_TEXT, parse_mode='Markdown',
                                    reply_markup=kb_main())


# ─── /id ─────────────────────────────────────────────────────────────────────

async def get_id(update: Update, context: ContextTypes.DEFAULT_TYPE):
    cid = update.effective_chat.id
    await update.message.reply_text(
        f"🆔 Chat ID kamu: `{cid}`\n\nSalin ke variable `CHAT_ID` di Railway.",
        parse_mode='Markdown', reply_markup=KB_HOME
    )


# ─── Callback dispatcher ─────────────────────────────────────────────────────

async def cb_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data  = query.data

    # ── Menu Utama ──────────────────────────────────────────────────────
    if data == 'menu_home':
        context.user_data.clear()
        await query.edit_message_text(MAIN_TEXT, parse_mode='Markdown',
                                      reply_markup=kb_main())

    # ── Bantuan ─────────────────────────────────────────────────────────
    elif data == 'menu_bantuan':
        await query.edit_message_text(
            "📖 *Panduan Joki Tracker*\n\n"
            "*Alur kerja:*\n"
            "1⃣ Deal → ➕ Tambah Job\n"
            "2⃣ Kirim → 🔄 Update → Menunggu Approval\n"
            "3⃣ Revisi → 🔄 Update → Sedang Direvisi\n"
            "4⃣ Acc → 🔄 Update → Menunggu Payment\n"
            "5⃣ Lunas → ✅ Selesai/Lunas\n\n"
            "*Status:*\n"
            "🟡 On Proses — Lagi dikerjain\n"
            "🔵 Menunggu Approval — Sudah kirim\n"
            "🔴 Sedang Direvisi — Ada revisi\n"
            "✅ Menunggu Payment — Tinggal nunggu bayar\n\n"
            "*Format Tambah Job (pisah 2 spasi):*\n"
            "`Nomor/Nama  Grup  Keterangan  Fee  Deadline`\n"
            "_Contoh: +62 831-6896-8059  Grup Joki  Essay 5 hal  75000  30/04 18:00_\n\n"
            "⏰ Reminder otomatis tiap jam tepat\n"
            "🚨 Alert jika deadline ≤ 3 jam",
            parse_mode='Markdown',
            reply_markup=KB_HOME
        )

    # ── List Job ─────────────────────────────────────────────────────────
    elif data == 'menu_list':
        jobs = get_active_jobs()
        text = format_job_list(jobs)
        await query.edit_message_text(
            text, parse_mode='Markdown',
            disable_web_page_preview=True,
            reply_markup=kb(
                row(btn("🔄 Update", "menu_update"),
                    btn("🗑️ Hapus",  "menu_hapus")),
                row(btn("✅ Selesai", "menu_selesai"),
                    btn("🏠 Menu",   "menu_home")),
            )
        )

    # ── Tambah Job ───────────────────────────────────────────────────────
    elif data == 'menu_tambah':
        context.user_data[FORM_STATE] = 'quick_add'
        await query.edit_message_text(
            "📝 *Tambah Job*\n\n"
            "Ketik 1 baris, pisahkan tiap bagian dengan *2 spasi*:\n\n"
            "`Nomor/Nama  Grup  Keterangan  Fee  Deadline`\n\n"
            "*Contoh:*\n"
            "`+62 831-6896-8059  Grup Joki UI  Essay 5 hal  75000  30/04 18:00`\n\n"
            "_Deadline boleh tanpa tahun, otomatis 2026_",
            parse_mode='Markdown',
            reply_markup=kb(row(btn("❌ Batal", "menu_home")))
        )

    # ── Update Status ────────────────────────────────────────────────────
    elif data == 'menu_update':
        await _show_job_picker(query, 'update')

    # ── Hapus Job ────────────────────────────────────────────────────────
    elif data == 'menu_hapus':
        await _show_job_picker(query, 'hapus')

    # ── Selesai / Lunas ──────────────────────────────────────────────────
    elif data == 'menu_selesai':
        await _show_job_picker(query, 'selesai')

    # ── Pilih job untuk update ───────────────────────────────────────────
    elif data.startswith('job_upd_'):
        job_id = int(data.split('_')[2])
        await _show_status_picker(query, job_id)

    # ── Set status baru ──────────────────────────────────────────────────
    elif data.startswith('setstatus_'):
        parts      = data.split('_', 2)   # setstatus_<id>_<status>
        job_id     = int(parts[1])
        new_status = parts[2]
        await _do_set_status(query, context, job_id, new_status)

    # ── Pilih job untuk hapus ────────────────────────────────────────────
    elif data.startswith('job_del_'):
        job_id = int(data.split('_')[2])
        job    = get_job(job_id)
        if not job:
            await query.edit_message_text("❌ Job tidak ditemukan.", reply_markup=KB_HOME)
            return
        link = hunter_link(job['hunter_name'])
        await query.edit_message_text(
            f"🗑️ *Konfirmasi Hapus*\n\n"
            f"Job *#{job_id}*\n"
            f"👤 {link} | {job['group_name']}\n"
            f"📋 {job['job_desc']}\n\n"
            f"⚠️ Data akan dihapus *permanen*. Yakin?",
            parse_mode='Markdown',
            disable_web_page_preview=True,
            reply_markup=kb(
                row(btn("✅ Ya, Hapus",   f"confirm_del_{job_id}"),
                    btn("❌ Batal",        "menu_hapus")),
            )
        )

    # ── Konfirmasi hapus ─────────────────────────────────────────────────
    elif data.startswith('confirm_del_'):
        job_id = int(data.split('_')[2])
        job    = get_job(job_id)
        delete_job(job_id)
        await query.edit_message_text(
            f"🗑️ Job *#{job_id}* ({job['job_desc'] if job else '-'}) berhasil dihapus.",
            parse_mode='Markdown',
            reply_markup=kb(
                row(btn("🗑️ Hapus Lagi", "menu_hapus"),
                    btn("🏠 Menu Utama",  "menu_home")),
            )
        )

    # ── Pilih job untuk selesai/lunas ────────────────────────────────────
    elif data.startswith('job_done_'):
        job_id = int(data.split('_')[2])
        job    = get_job(job_id)
        archive_job(job_id)
        fee_fmt = f"Rp {job['fee']:,}".replace(',', '.')
        link    = hunter_link(job['hunter_name'])
        await query.edit_message_text(
            f"🎉 *Job #{job_id} lunas & diarsipkan!*\n\n"
            f"👤 {link} | {job['group_name']}\n"
            f"📋 {job['job_desc']}\n"
            f"💰 {fee_fmt}\n"
            f"✔️ Done: {job['done_at']}",
            parse_mode='Markdown',
            disable_web_page_preview=True,
            reply_markup=kb(
                row(btn("✅ Arsip Lagi", "menu_selesai"),
                    btn("🏠 Menu Utama", "menu_home")),
            )
        )


# ─── Helper: tampilkan daftar job sebagai tombol ───────────────────────────────

async def _show_job_picker(query, action_type: str):
    if action_type == 'selesai':
        jobs     = [j for j in get_active_jobs() if j['status'] == 'menunggu_payment']
        title    = "✅ *Pilih job yang sudah lunas:*"
        empty    = "📭 Tidak ada job *Menunggu Payment*."
        prefix   = 'job_done'
    elif action_type == 'hapus':
        jobs     = get_active_jobs()
        title    = "🗑️ *Pilih job yang ingin dihapus:*"
        empty    = "📭 Tidak ada job aktif."
        prefix   = 'job_del'
    else:  # update
        jobs     = get_active_jobs()
        title    = "🔄 *Pilih job untuk update status:*"
        empty    = "📭 Tidak ada job aktif."
        prefix   = 'job_upd'

    if not jobs:
        await query.edit_message_text(empty, parse_mode='Markdown',
                                      reply_markup=KB_HOME)
        return

    keyboard_rows = []
    for job in jobs:
        emoji      = STATUS_MAP.get(job['status'], '❓').split()[0]
        desc_short = job['job_desc'][:20] + ('…' if len(job['job_desc']) > 20 else '')
        label      = f"{emoji} #{job['id']} {job['hunter_name']} — {desc_short}"
        keyboard_rows.append(row(btn(label, f"{prefix}_{job['id']}")))

    keyboard_rows.append(row(btn("🏠 Menu Utama", "menu_home")))
    await query.edit_message_text(title, parse_mode='Markdown',
                                  reply_markup=InlineKeyboardMarkup(keyboard_rows))


# ─── Helper: tampilkan pilihan status untuk 1 job ─────────────────────────────

async def _show_status_picker(query, job_id: int):
    job = get_job(job_id)
    if not job:
        await query.edit_message_text("❌ Job tidak ditemukan.", reply_markup=KB_HOME)
        return

    current = STATUS_MAP.get(job['status'], '-')
    fee_fmt = f"Rp {job['fee']:,}".replace(',', '.')
    link    = hunter_link(job['hunter_name'])

    await query.edit_message_text(
        f"🔄 *Update Job #{job_id}*\n\n"
        f"👤 {link} | {job['group_name']}\n"
        f"📋 {job['job_desc']}\n"
        f"💰 {fee_fmt} | ⏰ {job['deadline']}\n"
        f"📌 Sekarang: {current}\n\n"
        f"Pilih status baru:",
        parse_mode='Markdown',
        disable_web_page_preview=True,
        reply_markup=kb(
            row(btn("🟡 On Proses",         f"setstatus_{job_id}_on_proses")),
            row(btn("🔵 Menunggu Approval",  f"setstatus_{job_id}_menunggu_approval")),
            row(btn("🔴 Sedang Direvisi",    f"setstatus_{job_id}_sedang_direvisi")),
            row(btn("✅ Menunggu Payment",   f"setstatus_{job_id}_menunggu_payment")),
            row(btn("🔙 Kembali",            "menu_update")),
        )
    )


# ─── Helper: eksekusi set status ──────────────────────────────────────────────

async def _do_set_status(query, context, job_id: int, new_status: str):
    if new_status == 'sedang_direvisi':
        # Butuh input deadline revisi → simpan state, minta teks
        context.user_data[PENDING_STATE] = {
            'action': 'revision_deadline',
            'job_id': job_id,
        }
        await query.edit_message_text(
            f"🔴 Job *#{job_id}* → Sedang Direvisi\n\n"
            f"Ketik deadline revisi:\n"
            f"`DD/MM/YYYY HH:MM` atau `DD/MM HH:MM`\n"
            f"_Contoh: 02/05/2026 20:00_",
            parse_mode='Markdown'
        )
        return

    if new_status == 'menunggu_payment':
        done_at = now_wita().strftime('%d/%m/%Y %H:%M')
        update_status(job_id, new_status, done_at=done_at)
        job  = get_job(job_id)
        link = hunter_link(job['hunter_name'])
        await query.edit_message_text(
            f"✅ *Job #{job_id} — Menunggu Payment*\n\n"
            f"👤 {link} | {job['group_name']}\n"
            f"🕐 Done: {done_at}",
            parse_mode='Markdown',
            disable_web_page_preview=True,
            reply_markup=KB_BACK_HOME
        )
        return

    update_status(job_id, new_status)
    label = STATUS_MAP.get(new_status, new_status)
    await query.edit_message_text(
        f"✅ Job *#{job_id}* diperbarui → {label}",
        parse_mode='Markdown',
        reply_markup=KB_BACK_HOME
    )


# ─── Handler semua pesan teks ─────────────────────────────────────────────────

async def any_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip()

    # ── 1. Pending state (revision deadline) ──────────────────────────
    pending = context.user_data.get(PENDING_STATE)
    if pending and pending.get('action') == 'revision_deadline':
        try:
            dl_str = parse_deadline(text)
            job_id = pending['job_id']
            update_status(job_id, 'sedang_direvisi', revision_deadline=dl_str)
            del context.user_data[PENDING_STATE]
            await update.message.reply_text(
                f"🔴 Job *#{job_id}* → Sedang Direvisi\n⏰ Deadline revisi: {dl_str}",
                parse_mode='Markdown', reply_markup=KB_BACK_HOME
            )
        except ValueError:
            await update.message.reply_text(
                "❌ Format tidak dikenali. Coba lagi:\n`DD/MM/YYYY HH:MM` atau `DD/MM HH:MM`",
                parse_mode='Markdown'
            )
        return

    # ── 2. Form tambah job ─────────────────────────────────────────────
    form_state = context.user_data.get(FORM_STATE)
    if form_state:
        await _handle_form(update, context, text, form_state)
        return

    # ── 3. Tidak ada state aktif → tampilkan menu ─────────────────────
    await update.message.reply_text(MAIN_TEXT, parse_mode='Markdown',
                                    reply_markup=kb_main())


async def _handle_form(update, context, text: str, state: str):
    """Quick-add: parse 1 baris dipisah 2 spasi."""
    import re as _re
    cancel_kb = kb(row(btn("❌ Batal", "menu_home")))

    if state != 'quick_add':
        await update.message.reply_text(MAIN_TEXT, parse_mode='Markdown',
                                        reply_markup=kb_main())
        return

    # Split by 2+ spasi
    parts = [p.strip() for p in re.split(r'  +', text)]
    parts = [p for p in parts if p]  # buang yang kosong

    if len(parts) < 5:
        await update.message.reply_text(
            "❌ Kurang lengkap. Format:\n"
            "`Nomor/Nama  Grup  Keterangan  Fee  Deadline`\n\n"
            "_Pisahkan tiap bagian dengan 2 spasi_",
            parse_mode='Markdown', reply_markup=cancel_kb
        )
        return

    hunter_raw = parts[0]
    group_raw  = parts[1]
    desc_raw   = parts[2]
    fee_raw    = _re.sub(r'\D', '', parts[3])
    dl_raw     = parts[4]

    try:
        fee    = int(fee_raw)
        dl_str = parse_deadline(dl_raw)
    except ValueError as e:
        await update.message.reply_text(
            f"❌ Error: {e}\n\n"
            "Pastikan format fee angka dan deadline `DD/MM HH:MM`",
            parse_mode='Markdown', reply_markup=cancel_kb
        )
        return

    job_id = add_job(hunter_raw, group_raw, desc_raw, fee, dl_str)
    context.user_data.pop(FORM_STATE, None)
    context.user_data.pop(FORM_DATA, None)

    fee_fmt = f"Rp {fee:,}".replace(',', '.')
    link    = hunter_link(hunter_raw)

    await update.message.reply_text(
        f"✅ *Data Berhasil Disimpan!*\n\n"
        f"🆔 ID: #{job_id}\n"
        f"👤 Hunter: {link}\n"
        f"📱 Grup: {group_raw}\n"
        f"📋 Job: {desc_raw}\n"
        f"💰 Fee: {fee_fmt}\n"
        f"⏰ Deadline: {dl_str}\n"
        f"📌 Status: 🟡 On Proses",
        parse_mode='Markdown',
        disable_web_page_preview=True,
        reply_markup=kb(
            row(btn("🔄 Update Status", f"job_upd_{job_id}"),
                btn("📋 Lihat List",     "menu_list")),
            row(btn("➕ Tambah Lagi",    "menu_tambah"),
                btn("🏠 Menu Utama",     "menu_home")),
        )
    )
