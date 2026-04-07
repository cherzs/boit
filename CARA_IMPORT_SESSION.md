# Cara Import Session dari Chrome/Edge

Jika fitur "📥 Import from Chrome/Edge" tidak berfungsi, gunakan cara manual berikut.

## 🚀 Cara 1: Import Otomatis (Recommended)

### Langkah-langkah:

1. **Buka Chrome atau Edge browser** (bukan browser bot)

2. **Login ke ZeusX**:
   - Buka https://www.zeusx.com
   - Login dengan username dan password
   - Pastikan sudah masuk ke dashboard

3. **JANGAN tutup browser** - Biarkan tetap terbuka

4. **Buka Dashboard Bot** di tab/window lain

5. **Klik tombol "📥 Import from Chrome/Edge"**

6. **Tunggu** sampai muncul pesan "✅ Session imported!"

### Kalau Gagal:
- Pastikan Chrome/Edge tidak sedang di-close
- Coba refresh dashboard bot
- Kalau masih gagal, gunakan **Cara 2** di bawah

---

## 📝 Cara 2: Export Manual dengan Extension

### Step 1: Install Extension

1. Buka Chrome/Edge
2. Install extension **"EditThisCookie"** atau **"Cookie-Editor"**:
   - Chrome: https://chrome.google.com/webstore/detail/editthiscookie/fngmhnnpilhplaeedifhccceomclgfbg
   - Edge: https://microsoftedge.microsoft.com/addons/detail/editthiscookie/ajfboagkmmckmckihjfafaphjmdogme

### Step 2: Export Cookies

1. **Login ke ZeusX** di Chrome/Edge
2. Klik icon extension **EditThisCookie** di toolbar
3. Klik tombol **Export** (icon panah ke bawah)
4. Pilih format **JSON**
5. Copy hasil export (teks JSON)

### Step 3: Buat auth.json

1. Di folder bot, buat file baru: `auth.json`
2. Paste hasil export tadi
3. Format yang benar:

```json
{
  "cookies": [
    {
      "name": "session",
      "value": "paste_value_disini",
      "domain": ".zeusx.com",
      "path": "/",
      "expires": 1769999999,
      "httpOnly": true,
      "secure": true,
      "sameSite": "Lax"
    }
  ],
  "origins": []
}
```

4. **Save file**

### Step 4: Verifikasi

1. Refresh dashboard bot
2. Seharusnya muncul "✅ Session active"
3. Bot siap digunakan!

---

## 🔧 Cara 3: Copy dari DevTools (Advanced)

### Step 1: Buka DevTools

1. Login ke ZeusX di Chrome/Edge
2. Tekan **F12** atau klik kanan → "Inspect"
3. Pilih tab **Application** (Chrome) atau **Storage** (Edge)

### Step 2: Ambil Cookies

1. Di sidebar kiri, klik **Cookies** → **https://www.zeusx.com**
2. Cari cookie dengan nama seperti:
   - `session`
   - `auth`
   - `remember_me`
   - Atau yang domain-nya `.zeusx.com`
3. **Copy nilai (Value)** dari setiap cookie

### Step 3: Buat auth.json

Buat file `auth.json` dengan format:

```json
{
  "cookies": [
    {
      "name": "session",
      "value": "PASTE_VALUE_SESSION_DISINI",
      "domain": ".zeusx.com",
      "path": "/",
      "expires": -1,
      "httpOnly": true,
      "secure": true,
      "sameSite": "Lax"
    },
    {
      "name": "remember_me",
      "value": "PASTE_VALUE_REMEMBER_ME_DISINI",
      "domain": ".zeusx.com",
      "path": "/",
      "expires": 1769999999,
      "httpOnly": false,
      "secure": true,
      "sameSite": "Lax"
    }
  ],
  "origins": []
}
```

---

## ⚠️ Catatan Penting

1. **Session Expired**: Session biasanya bertahan 24 jam - 7 hari
2. **Kalau Error**: Ulangi proses import
3. **Alternatif**: Gunakan fitur **Auto-Fill Login** (lebih mudah):
   - Isi `config.json` dengan username/password
   - Klik "▶️ Start Bot"
   - Solve CAPTCHA manual
   - Login otomatis

---

## 🆘 Masih Tidak Bisa?

Silakan gunakan cara **Auto-Fill Login**:

1. Edit `config.json`:
```json
{
    "username": "username-zeusx-kamu",
    "password": "password-kamu"
}
```

2. Klik **"▶️ Start Bot"**

3. Browser terbuka dengan form sudah terisi

4. **Solve CAPTCHA** dan klik Login

5. Bot akan jalan otomatis!
