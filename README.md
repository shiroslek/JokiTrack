# 🤖 Joki Tracker Bot

Bot Telegram untuk manajemen job joki — tracking status, deadline, dan fee, dengan reminder otomatis setiap jam.

---

## 📋 Fitur

| Fitur | Keterangan |
|---|---|
| `/tambah` | Tambah job baru (step-by-step) |
| `/list` | Lihat semua job aktif, dikelompokkan per status |
| `/update` | Update status job via tombol inline |
| `/selesai` | Arsipkan job yang sudah dibayar |
| `/id` | Lihat Chat ID kamu |
| Reminder tiap jam | Ringkasan semua job aktif setiap jam tepat |
| Alert deadline | Notifikasi khusus jika deadline ≤ 3 jam |

---

## 🚀 Cara Deploy

### Langkah 1 — Buat Bot di BotFather
1. Buka Telegram, cari `@BotFather`
2. Kirim `/newbot` → ikuti instruksi
3. Salin **token** yang diberikan

### Langkah 2 — Upload ke GitHub
1. Buat repo baru di GitHub (misal: `joki-tracker-bot`)
2. Upload semua file dari folder ini ke repo tersebut

### Langkah 3 — Buat Project di Railway
1. Buka [railway.app](https://railway.app) → **New Project** → **Deploy from GitHub Repo**
2. Pilih repo `joki-tracker-bot`

### Langkah 4 — Tambahkan PostgreSQL
1. Di dalam project Railway, klik **+ New** → **Database** → **Add PostgreSQL**
2. Setelah PostgreSQL selesai dibuat, Railway otomatis menyediakan variable `DATABASE_URL`
3. Di tab **Variables** service bot kamu, klik **+ Add Reference Variable**
4. Tambahkan referensi ke `DATABASE_URL` dari PostgreSQL service

### Langkah 5 — Set Environment Variables
Di tab **Variables** service bot, tambahkan:

| Variable | Nilai |
|---|---|
| `BOT_TOKEN` | Token dari BotFather |
| `CHAT_ID` | *(lihat Langkah 6)* |
| `TZ` | `Asia/Makassar` |

### Langkah 6 — Dapatkan Chat ID
1. Setelah bot deploy (meski `CHAT_ID` belum diisi), buka bot di Telegram
2. Kirim `/id`
3. Salin angka yang muncul → tempel ke variable `CHAT_ID` di Railway
4. Railway akan otomatis restart

---

## 📌 Alur Penggunaan

```
Deal dengan hunter
      ↓
/tambah  →  Status: 🟡 On Proses
      ↓
Kirim hasil ke hunter
      ↓
/update  →  Status: 🔵 Menunggu Approval
      ↓
    [Ada revisi?]
    Ya  → /update → 🔴 Sedang Direvisi (input deadline revisi)
    Tidak
      ↓
/update  →  Status: ✅ Menunggu Payment
      ↓
Uang masuk
      ↓
/selesai  →  Job diarsipkan 🎉
```

---

## 🗄️ Database

Bot mendukung dua mode database:

| Mode | Kapan dipakai |
|---|---|
| **PostgreSQL** | Jika `DATABASE_URL` tersedia (Railway + plugin PostgreSQL) — **direkomendasikan** |
| **SQLite** | Jika `DATABASE_URL` kosong — untuk development lokal saja |

> Data di PostgreSQL **tidak hilang** meski Railway restart atau redeploy.

---

## 🛠️ Tech Stack

- Python 3.11+
- [python-telegram-bot](https://github.com/python-telegram-bot/python-telegram-bot) v20
- APScheduler v3
- PostgreSQL / SQLite
- Railway (hosting)
