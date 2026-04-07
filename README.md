# ZeusX Auto-Relister Bot

Bot otomasi yang dibuat untuk membantu seller di ZeusX melakukan *re-list* (hapus dan buat ulang) seluruh produk jualan mereka secara otomatis, lengkap dengan **Web Dashboard** modern.

---

## 🚀 Fitur Utama

- **Web UI Modern**: Interface yang elegan dan responsif dengan status *real-time*.
- **Otomatisasi Penuh**: Mengambil *(scrape)* detail produk, gambar, dan membuat listing baru persis seperti halaman asli di website (mencakup Kategori, Game Utama, Harga, Stok, Game Spesifik, dan Waktu Pengiriman).
- **Manual Mode / One-Click Run**: Cukup klik Start sekali, dan bot akan me-relisting semua produk yang aktif.
- **Bypass Proteksi Anti-Bot**: Menggunakan engine Chromium *Playwright* khusus.

---

## 🛠 Instalasi Pertama (Developer/Admin)

Pastikan **Python 3.10+** (atau lebih tinggi) sudah terinstal di komputer. Saat install Python di Windows, **WAJIB mencentang "Add Python to PATH"**.

1. Buka CMD/Terminal di dalam folder ini.
2. Install semua file kebutuhan (*library* Python):
   ```bash
   pip install -r requirements.txt
   playwright install
   ```

---

## 🕹 Cara Menjalankan Bot

### **Pilihan 1: Cara Standar (Manual lewat CMD)**
1. Buka CMD di dalam folder bot ini.
2. Ketik perintah:
   ```bash
   python server.py
   ```
3. Buka browser dan pergi ke `http://localhost:8000`

### **Pilihan 2: Cara Cepat (Sistem Alias "Bot")**
Bagi pengguna Windows, Anda bisa mengatur agar bot bisa dinyalakan dari foldernya tanpa harus buka CMD manual, atau bahkan **darimana saja hanya dengan mengetik kata `Bot`**.

#### **Cara A: Lewat Shortcut / Klik Kanan (Paling Gampang)**
1. Cari file bernama **`Bot.bat`** di dalam folder bot ini.
2. Cukup klik ganda (Double-Click) file tersebut. Server akan menyala dan otomatis membuka browser ke halaman dashboard.

#### **Cara B: Bikin Alias "Bot" Global di CMD (Disarankan)**
Jika ingin lebih terlihat *pro*—di mana Anda bisa membuka CMD baru dari lokasi acak (misal Desktop atau Disk D:\) lalu sekadar mengetik `Bot`—ikuti langkah berikut:

1. **Copy lokasi folder bot ini**. Misalnya tergeletak di `C:\ZeusX_Bot`. (Penting: Sebaiknya jangan taruh di Desktop atau folder sementara. Pindahkan ke Root Drive seperti `C:\` atau `D:\` terlebih dahulu).
2. Tekan tombol logo **Windows** di keyboard, ketik tulisan `Environment Variables`.
3. Pilih hasil pencarian yang berjudul: **"Edit the system environment variables"**.
4. Akan muncul jendela peringatan kecil, klik tombol **"Environment Variables..."** di bagian kanan bawah.
5. Pada kotak bagian atas (bernama *User variables for [Nama Usermu]*), cari variabel yang bernama **`Path`**.
6. Klik pada baris `Path` tersebut, lalu tekan tombol **Edit...**
7. Klik tombol **New** (di sebelah kanan atas).
8. **Paste (tempel)** lokasi folder bot yang tadi kamu salin (misal: `C:\ZeusX_Bot`).
9. Tekan **OK**, lalu tekan **OK** lagi, dan **OK** sekali lagi untuk menyimpan dan menutup jendelanya.

**Selesai! Saatnya Mencoba:**
Tutup / silang aplikasi CMD jika ada yang sedang terbuka. Sekarang, coba buka aplikasi CMD baru, atau buka Windows Run (tekan `Win + R`), dan ketik:
```bash
Bot
```
Lalu tekan Enter. Bot akan langsung *on* dan membuka browser secara otomatis, tak peduli di folder apa CMD kamu sedang berada!
