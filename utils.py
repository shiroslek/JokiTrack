import re
from datetime import datetime

STATUS_MAP = {
    'on_proses':         '🟡 On Proses',
    'menunggu_approval': '🔵 Menunggu Approval',
    'sedang_direvisi':   '🔴 Sedang Direvisi',
    'menunggu_payment':  '✅ Menunggu Payment',
}


def hunter_link(hunter_name: str) -> str:
    """
    Ubah nomor/nama hunter jadi link klik-langsung:
    - Jika berupa angka (nomor WA) → link wa.me
    - Jika berupa @username Telegram → link t.me
    - Selain itu → teks biasa
    """
    name = hunter_name.strip()

    # Nomor WA: bersihkan karakter non-digit lalu buat link wa.me
    digits_only = re.sub(r'\D', '', name)
    if digits_only and len(digits_only) >= 9:
        return f"[{name}](https://wa.me/{digits_only})"

    # Username Telegram
    if name.startswith('@'):
        username = name.lstrip('@')
        return f"[{name}](https://t.me/{username})"

    return name


def format_job_list(jobs, title="📋 *Daftar Job Aktif*"):
    if not jobs:
        return "📭 Tidak ada job aktif saat ini."

    grouped = {k: [] for k in STATUS_MAP}
    for job in jobs:
        if job['status'] in grouped:
            grouped[job['status']].append(job)

    now = datetime.now()
    lines = [title] if title else []

    for status_key, label in STATUS_MAP.items():
        job_list = grouped[status_key]
        if not job_list:
            continue
        lines.append(f"\n{label} ({len(job_list)})")

        for job in job_list:
            if status_key == 'sedang_direvisi' and job['revision_deadline']:
                dl_str = job['revision_deadline']
            else:
                dl_str = job['deadline']

            # Hitung sisa waktu
            try:
                deadline = datetime.strptime(dl_str, '%d/%m/%Y %H:%M')
                diff = (deadline - now).total_seconds()
                if diff < 0:
                    time_info = "🔥 LEWAT DEADLINE!"
                elif diff < 3600:
                    time_info = f"⚠️ {int(diff // 60)} menit lagi!"
                elif diff < 86400:
                    time_info = f"🕐 {int(diff // 3600)} jam lagi"
                else:
                    time_info = f"📅 {int(diff // 86400)} hari lagi"
            except Exception:
                time_info = "-"

            fee_str = f"Rp {job['fee']:,}".replace(',', '.')
            link = hunter_link(job['hunter_name'])

            if status_key == 'menunggu_payment':
                done_info = f"\n   ✔️ Done: {job['done_at']}" if job['done_at'] else ""
                lines.append(
                    f"• #{job['id']} {link} | {job['group_name']}\n"
                    f"   {job['job_desc']} | {fee_str}{done_info}"
                )
            else:
                lines.append(
                    f"• #{job['id']} {link} | {job['job_desc']}\n"
                    f"   {fee_str} | ⏰ {dl_str} ({time_info})"
                )

    return "\n".join(lines)
