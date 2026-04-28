import re
from datetime import datetime
import pytz

WITA = pytz.timezone('Asia/Makassar')

def now_wita() -> datetime:
    """Kembalikan datetime sekarang dalam timezone WITA (UTC+8)."""
    return datetime.now(tz=WITA).replace(tzinfo=None)

STATUS_MAP = {
    'on_proses':         '🟡 On Proses',
    'menunggu_approval': '🔵 Menunggu Approval',
    'sedang_direvisi':   '🔴 Sedang Direvisi',
    'menunggu_payment':  '✅ Menunggu Payment',
}

CURRENT_YEAR = datetime.now().year


def parse_deadline(raw: str) -> str:
    """
    Terima berbagai format deadline, kembalikan 'DD/MM/YYYY HH:MM'.
    - '30/04/2026 18:00' → as-is
    - '30/04 18:00'      → tambah tahun berjalan
    - '30/04'            → tambah tahun berjalan + jam 23:59
    """
    raw = raw.strip()
    # Sudah lengkap dengan tahun
    try:
        datetime.strptime(raw, '%d/%m/%Y %H:%M')
        return raw
    except ValueError:
        pass
    # Tanpa tahun, dengan jam
    try:
        dt = datetime.strptime(raw, '%d/%m %H:%M')
        return dt.replace(year=CURRENT_YEAR).strftime('%d/%m/%Y %H:%M')
    except ValueError:
        pass
    # Tanpa tahun, tanpa jam
    try:
        dt = datetime.strptime(raw, '%d/%m')
        return dt.replace(year=CURRENT_YEAR, hour=23, minute=59).strftime('%d/%m/%Y %H:%M')
    except ValueError:
        pass
    raise ValueError(f"Format deadline tidak dikenali: {raw}")


def normalize_wa_number(number: str) -> str:
    """Normalisasi nomor WA: 08xxx → 628xxx, +62xxx → 62xxx."""
    digits = re.sub(r'\D', '', number)
    if digits.startswith('0'):
        digits = '62' + digits[1:]
    return digits


def hunter_link(hunter_name: str) -> str:
    name = hunter_name.strip()
    # Cek apakah input adalah nomor WA (boleh ada +, spasi, strip, titik)
    # Contoh valid: +62 831-6896-8059 / 081368968059 / 6281368968059
    digits_only = re.sub(r'\D', '', name)
    # Anggap nomor WA jika: hampir semua karakter adalah angka/pemisah,
    # dan panjang digit >= 9
    non_digit_chars = re.sub(r'[\d\s\+\-\.\(\)]', '', name)
    if len(digits_only) >= 9 and len(non_digit_chars) == 0:
        normalized = normalize_wa_number(name)
        return f"[{name}](https://wa.me/{normalized})"
    if name.startswith('@'):
        return f"[{name}](https://t.me/{name.lstrip('@')})"
    return name


def format_job_list(jobs, title=None):
    now    = now_wita()
    ts     = now.strftime('%d/%m/%Y %H:%M')
    header = title or f"📋 *Laporan Job — {ts}*"

    if not jobs:
        return f"{header}\n\n📭 Tidak ada job aktif saat ini."

    grouped = {k: [] for k in STATUS_MAP}
    for job in jobs:
        if job['status'] in grouped:
            grouped[job['status']].append(job)

    # ── Financial summary ──────────────────────────────────────────────
    uang_berjalan = sum(
        j['fee'] for j in jobs
        if j['status'] in ('on_proses', 'menunggu_approval', 'sedang_direvisi')
    )
    total_piutang = sum(
        j['fee'] for j in jobs if j['status'] == 'menunggu_payment'
    )

    def rupiah(n):
        return f"Rp {n:,}".replace(',', '.')

    total_job = len(jobs)
    lines = [
        header,
        f"Total aktif: *{total_job} job*",
        f"💰 Uang Berjalan: *{rupiah(uang_berjalan)}*",
        f"🏦 Total Piutang: *{rupiah(total_piutang)}*",
        "─────────────────────",
    ]

    for status_key, label in STATUS_MAP.items():
        job_list = grouped[status_key]
        if not job_list:
            continue

        lines.append(f"\n{label}")
        lines.append("─" * 20)

        for i, job in enumerate(job_list, 1):
            dl_str = (
                job['revision_deadline']
                if status_key == 'sedang_direvisi' and job['revision_deadline']
                else job['deadline']
            )
            try:
                deadline = datetime.strptime(dl_str, '%d/%m/%Y %H:%M')
                diff = (deadline - now).total_seconds()
                if diff < 0:
                    time_info = "🔥 LEWAT DEADLINE!"
                elif diff < 3600:
                    time_info = f"⚠️ {int(diff // 60)} mnt lagi!"
                elif diff < 86400:
                    time_info = f"🕐 {int(diff // 3600)} jam lagi"
                else:
                    time_info = f"📅 {int(diff // 86400)} hari lagi"
            except Exception:
                time_info = "─"

            link = hunter_link(job['hunter_name'])

            if status_key == 'menunggu_payment':
                lines.append(
                    f"{i}. *#{job['id']}* {link}\n"
                    f"   📱 {job['group_name']}\n"
                    f"   📋 {job['job_desc']}\n"
                    f"   💰 {rupiah(job['fee'])}\n"
                    f"   ✔️ Done: {job['done_at'] or '─'}"
                )
            else:
                lines.append(
                    f"{i}. *#{job['id']}* {link}\n"
                    f"   📱 {job['group_name']}\n"
                    f"   📋 {job['job_desc']}\n"
                    f"   💰 {rupiah(job['fee'])}\n"
                    f"   ⏰ {dl_str} ({time_info})"
                )

    # ── Warning deadline 24 jam ────────────────────────────────────────
    warning_jobs = []
    for job in jobs:
        if job['status'] == 'menunggu_payment':
            continue
        try:
            dl_str = (
                job['revision_deadline']
                if job['status'] == 'sedang_direvisi' and job['revision_deadline']
                else job['deadline']
            )
            diff = (datetime.strptime(dl_str, '%d/%m/%Y %H:%M') - now_wita()).total_seconds()
            if 0 < diff <= 86400:
                warning_jobs.append((job, diff))
        except Exception:
            pass

    lines.append("\n─────────────────────")
    if warning_jobs:
        warning_jobs.sort(key=lambda x: x[1])
        lines.append("⚠️ *Deadline dalam 24 jam:*")
        for job, diff in warning_jobs:
            h = int(diff // 3600)
            m = int((diff % 3600) // 60)
            sisa = f"{h}j {m}m" if h else f"{m} mnt"
            lines.append(f"  • #{job['id']} {job['hunter_name']} → sisa {sisa}")
    else:
        lines.append("✅ Tidak ada deadline mendesak")

    return "\n".join(lines)
