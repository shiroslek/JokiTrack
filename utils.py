from datetime import datetime

STATUS_MAP = {
    'on_proses':         '🟡 On Proses',
    'menunggu_approval': '🔵 Menunggu Approval',
    'sedang_direvisi':   '🔴 Sedang Direvisi',
    'menunggu_payment':  '✅ Menunggu Payment',
}


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
            # Pilih deadline yang relevan
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

            if status_key == 'menunggu_payment':
                done_info = f"\n   ✔️ Done: {job['done_at']}" if job['done_at'] else ""
                lines.append(
                    f"• #{job['id']} *{job['hunter_name']}* | {job['group_name']}\n"
                    f"   {job['job_desc']} | {fee_str}{done_info}"
                )
            else:
                lines.append(
                    f"• #{job['id']} *{job['hunter_name']}* | {job['job_desc']}\n"
                    f"   {fee_str} | ⏰ {dl_str} ({time_info})"
                )

    return "\n".join(lines)
