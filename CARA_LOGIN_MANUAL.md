# Cara Login Manual (Copy Cookie dari Browser)

Jika login otomatis tidak berfungsi, kamu bisa membuat `auth.json` secara manual.

## Langkah-langkah:

### 1. Login ke ZeusX di Browser

- Buka Chrome/Edge/Firefox
- Pergi ke https://zeusx.com/login
- Login dengan akun kamu (bisa pakai Google Login)

### 2. Ambil Cookie Session

**Chrome/Edge:**
1. Tekan `F12` atau klik kanan → "Inspect"
2. Pilih tab "Application" (Chrome) atau "Storage" (Firefox)
3. Di sidebar kiri, klik "Cookies" → "https://zeusx.com"
4. Cari cookie bernama `session` atau `remember_me`
5. Copy nilai (value) dari cookie tersebut

**Atau pakai Extension:**
1. Install extension "EditThisCookie" (Chrome) atau "Cookie-Editor" (Firefox)
2. Buka https://zeusx.com
3. Klik icon extension
4. Export cookies dalam format JSON

### 3. Edit File auth.json

1. Copy file `auth.json.template` dan rename jadi `auth.json`
2. Ganti nilai `value` dengan cookie yang kamu copy:

```json
{
  "cookies": [
    {
      "name": "session",
      "value": "paste_cookie_session_disini",
      "domain": ".zeusx.com",
      "path": "/",
      "expires": -1,
      "httpOnly": true,
      "secure": true,
      "sameSite": "Lax"
    }
  ],
  "origins": []
}
```

### 4. Simpan dan Test

1. Save file `auth.json`
2. Refresh dashboard bot
3. Status seharusnya jadi "Session active ✅"

---

## Tips:

- Cookie `session` biasanya expired dalam 24 jam
- Cookie `remember_me` bisa bertahan lebih lama (30 hari)
- Jika bot error "Session expired", ulangi langkah di atas
- Jangan share file `auth.json` ke orang lain (berisi data login)
