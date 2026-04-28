import re
from datetime import datetime

STATUS_MAP = {
    'on_proses':         '🟡 On Proses',
    'menunggu_approval': '🔵 Menunggu Approval',
    'sedang_direvisi':   '🔴 Sedang Direvisi',
    'menunggu_payment':  '✅ Menunggu Payment',
}


def hunter_link(hunter_name: str) -> str:
    name = hunter_name.strip()
    digits_only = re.sub(r'\D', '', name)
    if digits_only and len(digits_only) >= 9:
        return f"[{name}](https://wa.me/{digits_only})"
    if name.startswith('@'):
        return f"[{name}](https://t.me/{name.lstrip('@')})"
    return name


def format_job_list(jobs, title=None):
    now = datetime.now()
    ts  = now.strftime('%d/%m/%Y %H:%M')

    if not jobs:
        header = title or f"📋 *Laporan Job — {ts}*"
        return f"{header}\n\n📭 Tidak ada job aktif saat ini."

    grouped = {k: [] for k in STATUS_MAP}
    for job in jobs:
        if job['status'] in grouped:
            grouped[job['status']].append(job)

    total = len(jobs)
    header = title or f"📋 *Laporan Job — {ts}*"

    lines = [
        header,
        f"Total aktif: *{total} job*",
        "─────────────────────",
    ]

    for status_key, label in STATUS_MAP.items():
        job_list = grouped[status_key]
        if not job_list:
            continue

        lines.append(f"\n{label}")
        lines.append(f"{'─' * 20}")

        for i, job in enumerate(job_list, 1):
            # Pilih deadline relevan
            if status_key == 'sedang_direvisi' and job['revision_deadline']:
                dl_str = job['revision_deadline']
            else:
                dl_str = job['deadline']

            # Sisa waktu
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

            fee_str = f"Rp {job['fee']:,}".replace(',', '.')
            link    = hunter_link(job['hunter_name'])

            if status_key == 'menunggu_payment':
                lines.append(
                    f"{i}. *#{job['id']}* {link}\n"
                    f"   📱 {job['group_name']}\n"
                    f"   📋 {job['job_desc']}\n"
                    f"   💰 {fee_str}\n"
                    f"   ✔️ Done: {job['done_at'] or '─'}"
                )
            else:
                lines.append(
                    f"{i}. *#{job['id']}* {link}\n"
                    f"   📱 {job['group_name']}\n"
                    f"   📋 {job['job_desc']}\n"
                    f"   💰 {fee_str}\n"
                    f"   ⏰ {dl_str} ({time_info})"
                )

    lines.append("\n─────────────────────")

    # Hitung job mendekati deadline (< 24 jam)
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
            diff = (datetime.strptime(dl_str, '%d/%m/%Y %H:%M') - now).total_seconds()
            if 0 < diff <= 86400:
                warning_jobs.append((job, diff))
        except Exception:
            pass

    if warning_jobs:
        warning_jobs.sort(key=lambda x: x[1])
        lines.append("⚠️ *Deadline dalam 24 jam:*")
        for job, diff in warning_jobs:
            h = int(diff // 3600)
            m = int((diff % 3600) // 60)
            sisa = f"{h} jam {m} mnt" if h else f"{m} mnt"
            lines.append(f"  • #{job['id']} {job['hunter_name']} → sisa {sisa}")

    return "\n".join(lines)
