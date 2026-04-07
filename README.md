# ZeusX Auto-Relister Bot

Bot otomasi yang dibuat untuk membantu seller di ZeusX melakukan *re-list* (hapus dan buat ulang) seluruh produk jualan mereka secara otomatis, lengkap dengan **Web Dashboard** modern.

---

## 🚀 Fitur Utama

- **Web UI Modern**: Interface yang elegan dan responsif dengan status *real-time*.
- **Otomatisasi Penuh**: Mengambil *(scrape)* detail produk, gambar, dan membuat listing baru persis seperti halaman asli di website (mencakup Kategori, Game Utama, Harga, Stok, Game Spesifik, dan Waktu Pengiriman).
- **Manual Mode / One-Click Run**: Cukup klik Start sekali, dan bot akan me-relisting semua produk yang aktif.
- **Bypass Proteksi Anti-Bot**: Menggunakan engine Chromium *Playwright* khusus.

---

## 🛠 Instalasi Lengkap (Windows)

Ikuti langkah-langkah berikut dengan urut untuk menginstal bot di komputer Windows.

### **Step 1: Install Python**

1. Download Python dari [python.org](https://www.python.org/downloads/)
   - Pilih versi **Python 3.10** atau lebih tinggi
   - Contoh: `Python 3.10.11` atau `Python 3.11.x`

2. Jalankan installer Python yang sudah di-download

3. **PENTING!** Saat instalasi, centang 2 opsi berikut:
   - ✅ **Add Python to PATH** (di bawah tombol "Install Now")
   - ✅ **Use admin privileges when installing py.exe**

4. Klik **"Install Now"** dan tunggu sampai selesai

5. Verifikasi instalasi Python:
   - Buka CMD (tekan `Win + R`, ketik `cmd`, tekan Enter)
   - Ketik: `python --version`
   - Jika muncul versi (contoh: `Python 3.10.11`), berarti sukses ✅

---

### **Step 2: Download dan Extract Bot**

1. Download repository ini (zip) atau clone pakai Git

2. Extract folder bot ke lokasi yang mudah diakses
   - **Direkomendasikan**: `C:\BOT\` atau `D:\BOT\`
   - Hindari: Desktop atau folder Downloads (bisa bermasalah dengan permission)

3. Hasil struktur foldernya seperti ini:
   ```
   C:\BOT\
   ├── app.py
   ├── engine.py
   ├── server.py
   ├── Bot.bat
   ├── requirements.txt
   ├── templates\
   ├── images\           (folder kosong, akan terisi otomatis)
   └── ...
   ```

---

### **Step 3: Setup Virtual Environment (venv)**

Virtual environment akan mengisolasi library bot agar tidak bentrok dengan library lain.

1. Buka CMD sebagai **Administrator**:
   - Tekan `Win` → ketik `cmd` → klik kanan **Command Prompt** → pilih **"Run as administrator"**

2. Masuk ke folder bot:
   ```bash
   cd C:\BOT
   ```
   *(Ganti `C:\BOT` sesuai lokasi folder bot kamu)*

3. Buat virtual environment:
   ```bash
   python -m venv venv
   ```
   Tunggu sampai selesai (biasanya 1-2 menit)

4. Aktifkan virtual environment:
   ```bash
   venv\Scripts\activate
   ```
   Jika berhasil, akan muncul `(venv)` di depan prompt:
   ```
   (venv) C:\BOT>
   ```

---

### **Step 4: Install Dependencies**

Pastikan kamu masih di dalam virtual environment (ada tulisan `(venv)` di CMD).

1. Install library Python yang dibutuhkan:
   ```bash
   pip install -r requirements.txt
   ```
   Tunggu sampai selesai (butuh koneksi internet, sekitar 2-5 menit)

2. Install Playwright browser:
   ```bash
   playwright install chromium
   ```
   Ini akan mendownload browser Chromium khusus untuk bot (sekitar 100-200 MB)

3. **Verifikasi instalasi**:
   ```bash
   pip list
   ```
   Pastikan muncul library seperti: `fastapi`, `uvicorn`, `playwright`, `aiohttp`, dll.

---

### **Step 5: Konfigurasi Bot**

Bot membutuhkan file konfigurasi untuk menyimpan kredensial dan pengaturan.

1. Copy file `config.json.template` dan rename jadi `config.json`

2. Isi dengan kredensial ZeusX kamu:
   ```json
   {
     "interval_minutes": 10,
     "headless": false,
     "username": "username-kamu",
     "password": "password-kamu"
   }
   ```

3. **Fitur Auto-Fill**: Username dan password akan otomatis terisi saat browser login terbuka

4. Save file tersebut

⚠️ **Catatan Keamanan**: File `config.json` tidak akan di-push ke GitHub (sudah di-.gitignore), jadi aman untuk disimpan di local.

---

### **Step 6: Login ke ZeusX**

Pilih salah satu cara login:

#### **Opsi A: Auto-Fill Login (Recommended)**
1. Pastikan `config.json` sudah diisi email dan password
2. Klik **"▶️ Start Bot"** atau **"🔍 Scan My Products"**
3. Browser akan terbuka dan **form login otomatis terisi**
4. **Solve CAPTCHA manual** (klik "I'm not a robot")
5. Klik tombol **Login**
6. Selesai! Bot akan lanjut otomatis

#### **Opsi B: Login Otomatis (Import dari Chrome/Edge)**
1. Login ke ZeusX di browser Chrome/Edge kamu (https://zeusx.com/login)
2. Jangan logout, biarkan tetap login
3. Buka dashboard bot → klik tombol **"📥 Import from Chrome/Edge"**
4. Session akan otomatis tersimpan

#### **Opsi C: Login Manual (Copy Cookie)**
Jika opsi lain tidak berfungsi:
1. Copy file `auth.json.template` dan rename jadi `auth.json`
2. Buka ZeusX di browser → Login → Buka DevTools (F12)
3. Copy cookie session dari browser
4. Paste ke file `auth.json` (lihat panduan lengkap di `CARA_LOGIN_MANUAL.md`)
5. Save file

> ⚠️ **Catatan**: Google memblokir login otomatis dari browser automation. Jika pakai Google Login, gunakan **Opsi B**.

---

## 🕹 Cara Menjalankan Bot

Setelah instalasi selesai, ada beberapa cara untuk menjalankan bot:

---

### **Cara 1: Manual lewat CMD (Recommended untuk Development)**

1. Buka CMD di folder bot

2. Aktifkan virtual environment:
   ```bash
   venv\Scripts\activate
   ```

3. Jalankan server:
   ```bash
   python server.py
   ```

4. Buka browser dan akses:
   ```
   http://localhost:8000
   ```

5. Dashboard bot akan muncul dan siap digunakan!

---

### **Cara 2: Double-Click File Bot.bat (Paling Mudah)**

1. Masuk ke folder bot di File Explorer

2. Cari file bernama **`Bot.bat`**

3. **Double-click** file tersebut

4. Bot akan otomatis:
   - Mengaktifkan venv
   - Menjalankan server
   - Membuka browser ke dashboard

---

### **Cara 3: Alias Global "Bot" (Bisa jalan dari mana saja)**

Jika ingin mengetik `Bot` dari CMD mana saja (tidak harus di folder bot):

1. Copy lokasi folder bot (contoh: `C:\BOT`)

2. Tekan `Win` → ketik `Environment Variables`

3. Pilih **"Edit the system environment variables"**

4. Klik tombol **"Environment Variables..."**

5. Pada bagian **User variables**, cari variabel bernama **`Path`**

6. Klik **Edit...** → **New** → Paste lokasi folder bot → **OK**

7. Klik **OK** sampai semua jendela tertutup

8. Sekarang buka CMD baru dari mana saja, ketik:
   ```bash
   Bot
   ```
   Bot akan langsung jalan!

---

## 🔄 Update Bot (Jika Ada Perubahan)

Jika ada update dari repository GitHub:

1. Pull/update file terbaru (download ulang atau `git pull`)

2. Aktifkan venv:
   ```bash
   venv\Scripts\activate
   ```

3. Update dependencies (jika ada yang baru):
   ```bash
   pip install -r requirements.txt --upgrade
   ```

---

## ❌ Troubleshooting

### Error: "python" tidak dikenali
- Pastikan Python sudah di-add ke PATH saat instalasi
- Atau coba ketik `py` bukan `python`

### Error: "pip is not recognized"
- Install ulang Python dan pastikan centang "Add Python to PATH"

### Error: "No module named 'xxx'"
- Pastikan virtual environment sudah diaktifkan
- Jalankan ulang: `pip install -r requirements.txt`

### Error saat `playwright install`
- Pastikan koneksi internet stabil
- Coba pakai CMD Administrator

### Browser tidak terbuka otomatis
- Buka manual di browser: `http://localhost:8000`

---

## 📁 Struktur File Penting

```
C:\BOT\
├── app.py                 # Main application logic
├── engine.py              # Playwright automation engine
├── server.py              # Web server (FastAPI)
├── Bot.bat               # Shortcut untuk Windows
├── requirements.txt       # Python dependencies
├── config.json           # Konfigurasi login (local only)
├── auth.json             # Session auth (auto-generated)
├── products.json         # Data produk (auto-generated)
├── templates\
│   └── index.html        # Web UI dashboard
└── images\               # Folder gambar produk (local only)
    └── ...
```

---

## ⚠️ Catatan Penting

- **JANGAN** push file `config.json`, `auth.json`, `products.json`, dan folder `images/` ke GitHub - file-file ini sudah di-exclude via `.gitignore`
- Selalu gunakan virtual environment untuk menghindari konflik library
- Bot ini untuk personal use, gunakan dengan bijak

---

## 📝 Lisensi

Bot ini dibuat untuk keperluan otomasi personal. Gunakan dengan risiko sendiri.
