---
name: web-recon-endpoint-finder
description: Metodologi reverse-engineering website umum — untuk menemukan endpoint API tersembunyi, mekanisme auth, struktur data, dan cara mengintegrasikan layanan web apapun (bukan hanya AI). Gunakan ketika user ingin "cari endpoint website ini", "reverse engineer", "scrape API", "integrasi tanpa SDK resmi", atau "cari cara akses data dari website X".
---

# Web Recon & Endpoint Finder

Metodologi ini terinspirasi dari pendekatan gpt4free namun **berlaku untuk semua jenis website** — e-commerce, media sosial, berita, fintech, travel, AI, SaaS, dan lainnya. Tujuannya: menemukan bagaimana sebuah website berkomunikasi dengan backend-nya, lalu mereplikasi komunikasi tersebut secara programatik.

---

## ⚠️ ATURAN WAJIB

1. **Hanya untuk tujuan legal** — scraping/recon untuk riset, integrasi pribadi, atau reverse-engineering yang diizinkan ToS.
2. **Jangan bypass paywall berbayar** tanpa izin eksplisit pemilik layanan.
3. **Hormati rate limit** — jangan buat request berlebihan yang bisa membebani server target.
4. **Tidak untuk credential stuffing** atau akses akun orang lain.

---

## Alur Kerja (Urutan Wajib)

### FASE 1 — Profiling Awal Website

```bash
TARGET="https://target.com"

# 1. Cek headers server — dapat info: tech stack, CDN, security headers
curl -s -I "$TARGET" \
  -H "User-Agent: Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/138.0.0.0 Safari/537.36" \
  --max-time 10

# 2. Probe endpoint umum sekaligus
for ep in \
  "/api" "/api/v1" "/api/v2" "/v1" "/v2" \
  "/api/config" "/config.json" "/manifest.json" "/.well-known/openid-configuration" \
  "/graphql" "/gql" "/query" \
  "/api/auth" "/auth" "/login" "/api/login" "/api/session" \
  "/api/user" "/api/me" "/api/profile" \
  "/api/search" "/search" \
  "/api/data" "/data" \
  "/sitemap.xml" "/robots.txt" \
  "/swagger.json" "/openapi.json" "/api-docs" "/docs/api"; do
  code=$(curl -s -o /dev/null -w "%{http_code}" "$TARGET$ep" \
    -H "User-Agent: Mozilla/5.0 Chrome/138.0.0.0" --max-time 8 2>/dev/null)
  [ "$code" != "404" ] && echo "$code  $ep"
done
```

**Interpretasi kode HTTP:**
| Kode | Arti | Tindakan |
|---|---|---|
| `200` | Terbuka | Test langsung |
| `401` | Ada, butuh auth | Cari token/session |
| `403` | Ada, diblokir | Coba bypass header |
| `404` | Tidak ada | Coba variasi path lain |
| `405` | Method salah | Ganti GET↔POST |
| `307/302` | Redirect | Follow redirect-nya |
| `429` | Rate limited | Tambah delay / rotasi IP |
| `500` | Server error | Endpoint ada tapi payload salah |

---

### FASE 2 — Identifikasi Tech Stack

```bash
TARGET="https://target.com"

# Dari headers HTTP
curl -sI "$TARGET" | grep -iE "server|x-powered-by|x-framework|cf-ray|x-vercel|x-amz"

# Dari HTML meta tags
curl -s "$TARGET" | grep -iE '<meta[^>]+(generator|framework|version)[^>]+>'

# Dari robots.txt — sering ada path yang terbuka
curl -s "$TARGET/robots.txt"

# Dari HTML — cari link ke JS bundle
curl -s "$TARGET" | grep -oE 'src="[^"]+\.(js|mjs)"' | head -10
curl -s "$TARGET" | grep -oE "src='[^']+\.(js|mjs)'" | head -10

# Dari HTML — cari link API/backend hints
curl -s "$TARGET" | grep -oE '"(https?://[^"]{0,100}api[^"]{0,100})"' | sort -u | head -20
```

**Tanda-tanda tech stack:**
- `x-powered-by: Next.js` → Next.js, cek `/_next/static/` dan `__NEXT_DATA__`
- `x-powered-by: Express` → Node.js Express
- `cf-ray` header → Cloudflare, gunakan `--tlsv1.3`
- `x-vercel-id` → Vercel hosting
- `X-Amz-*` → AWS, mungkin ada S3 bucket publik
- Nuxt.js → cek `__nuxt` di HTML
- Django → cek `/admin/`, CSRF token pattern

---

### FASE 3 — Ekstrak Endpoint dari Source JS

Ini adalah teknik paling efektif untuk SPA (Single Page App).

```bash
TARGET="https://target.com"

# A. Dapatkan daftar JS bundle dari HTML
JS_FILES=$(curl -s "$TARGET" | grep -oE '"(/[^"]+\.(js|mjs))"' | tr -d '"' | sort -u)
echo "$JS_FILES"

# B. Cari endpoint dari setiap JS bundle
for JS in $JS_FILES; do
  JS_URL="$TARGET$JS"
  echo "=== $JS_URL ==="

  # Cari semua path /api/... dan /v1/...
  curl -s "$JS_URL" --max-time 30 | grep -oE '"(/api[^"]{0,100})"' | sort -u | head -20
  curl -s "$JS_URL" --max-time 30 | grep -oE '"(/v[0-9][^"]{0,100})"' | sort -u | head -20

  # Cari fetch() dan axios calls
  curl -s "$JS_URL" --max-time 30 | grep -oE 'fetch\("([^"]{0,100})"\)' | head -15
  curl -s "$JS_URL" --max-time 30 | grep -oE "axios\.(get|post|put|delete)\(['\"]([^'\"]{0,100})" | head -15

  # Cari base URL variable
  curl -s "$JS_URL" --max-time 30 | grep -oE '(BASE_URL|API_URL|apiUrl|baseUrl|ENDPOINT)[^,;]{0,100}' | head -10

  # Cari template literal endpoint
  curl -s "$JS_URL" --max-time 30 | grep -oE '`\$\{[a-zA-Z_]+\}/[a-z/_-]{0,60}`' | head -10
done

# C. Untuk CDN-hosted bundle (URL berbeda dari domain utama)
CDN_JS="https://cdn.target.com/assets/index-XXXX.js"
curl -s "$CDN_JS" --max-time 30 \
  | grep -oE '"(/[a-z/_-]{2,80})"' | sort -u | head -40
```

**Teknik tambahan untuk Next.js:**
```bash
# __NEXT_DATA__ di HTML berisi props awal + config API
curl -s "$TARGET" | grep -oE '<script id="__NEXT_DATA__"[^>]*>([^<]+)<' | head -1

# Next.js API routes — coba enumerasi
for ep in "/api/auth/session" "/api/auth/providers" "/api/trpc" "/api/hello"; do
  curl -s -o /dev/null -w "%{http_code}  $ep\n" "$TARGET$ep" --max-time 5
done
```

---

### FASE 4 — Analisis dengan Browser DevTools (Panduan Manual)

Ketika curl tidak cukup, gunakan DevTools browser:

```
1. Buka website target di Chrome/Firefox
2. F12 → tab "Network"
3. Filter: "Fetch/XHR" (untuk API calls saja)
4. Lakukan aksi yang ingin di-recon (search, login, scroll, klik tombol)
5. Klik request yang menarik → lihat:
   - Headers tab: URL, Method, Request Headers (auth, cookies)
   - Payload tab: Request body (JSON/FormData)
   - Response tab: Format response JSON
6. Klik kanan request → "Copy as cURL" → paste ke terminal untuk replay

Untuk GraphQL:
- Filter by "graphql" di search box Network
- Lihat tab Payload → operationName, query/mutation string, variables
- Copy as cURL dan replay

Untuk WebSocket:
- Filter "WS" di Network tab
- Lihat tab Messages untuk protocol & format pesan
```

---

### FASE 5 — Mekanisme Auth

#### A. Session/Cookie Biasa
```bash
# Login dan simpan cookie
curl -s -c /tmp/cookies.txt -X POST "$TARGET/api/login" \
  -H "Content-Type: application/json" \
  -H "User-Agent: Mozilla/5.0 Chrome/138.0.0.0" \
  -d '{"email":"user@example.com","password":"password123"}'

# Gunakan cookie untuk request berikutnya
curl -s -b /tmp/cookies.txt "$TARGET/api/protected-resource" \
  -H "User-Agent: Mozilla/5.0 Chrome/138.0.0.0"
```

#### B. Bearer Token (JWT)
```bash
# Login dapat token
TOKEN=$(curl -s -X POST "$TARGET/api/auth/signin" \
  -H "Content-Type: application/json" \
  -d '{"email":"user@example.com","password":"pass"}' \
  | grep -oE '"token":"([^"]+)"' | cut -d'"' -f4)

echo "Token: $TOKEN"

# Decode JWT tanpa library (lihat payload)
echo "$TOKEN" | cut -d'.' -f2 | base64 -d 2>/dev/null | python3 -m json.tool

# Gunakan token
curl -s "$TARGET/api/user/profile" \
  -H "Authorization: Bearer $TOKEN"
```

#### C. Guest/Anonymous (tanpa registrasi)
```bash
# Banyak website buat session anonim otomatis
curl -s "$TARGET/api/session" \
  -H "User-Agent: Mozilla/5.0 Chrome/138.0.0.0" \
  -H "Accept: application/json"

# Atau via guest login
curl -s -X POST "$TARGET/api/auth/guest" \
  -H "Content-Type: application/json" \
  -d '{}'
```

#### D. OAuth / SSO
```bash
# Cek /.well-known/openid-configuration
curl -s "$TARGET/.well-known/openid-configuration" | python3 -m json.tool

# Atau ambil authorization_url dari login page
curl -s "$TARGET/login" | grep -oE 'https://[^"]+oauth[^"]+' | head -5
```

#### E. API Key di Header
```bash
# Cari di JS bundle
curl -s "JS_BUNDLE_URL" | grep -oE '(x-api-key|apikey|api_key|X-Client-ID)[^,;]{0,80}' | head -10

# Test dengan API key dari bundle
curl -s "$TARGET/api/endpoint" \
  -H "X-API-Key: KEY_DARI_JS_BUNDLE"
```

#### F. HMAC / Signature (website yang lebih protektif)
```bash
# Cari di JS bundle — cari fungsi sign/hmac/signature
curl -s "JS_BUNDLE_URL" | grep -oE '(hmac|HMAC|signature|sign)\([^)]{0,200}\)' | head -10

# Cari secret key yang digunakan
curl -s "JS_BUNDLE_URL" | grep -oE '"(secret|SECRET|key|KEY)":\s*"[^"]{10,64}"' | head -5
```

---

### FASE 6 — Analisis Format Request & Response

```bash
# Setelah dapat token/cookie, test endpoint utama
TOKEN="..."
COOKIE="session=abc123"

# GET request
curl -s "$TARGET/api/endpoint" \
  -H "Authorization: Bearer $TOKEN" \
  -H "User-Agent: Mozilla/5.0 Chrome/138.0.0.0" \
  | python3 -m json.tool | head -50

# POST dengan JSON
curl -s -X POST "$TARGET/api/endpoint" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -H "User-Agent: Mozilla/5.0 Chrome/138.0.0.0" \
  -d '{"key":"value"}' \
  | python3 -m json.tool | head -50

# POST dengan Form data
curl -s -X POST "$TARGET/api/endpoint" \
  -H "Cookie: $COOKIE" \
  -F "field1=value1" \
  -F "field2=value2"

# GraphQL
curl -s -X POST "$TARGET/graphql" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "operationName": "GetUser",
    "query": "query GetUser { me { id name email } }",
    "variables": {}
  }' | python3 -m json.tool

# WebSocket test (pakai websocat jika tersedia)
# websocat "wss://target.com/ws" --header "Authorization: Bearer $TOKEN"
```

---

### FASE 7 — Test Streaming Response

```bash
# SSE (Server-Sent Events)
curl -s -X POST "$TARGET/api/stream" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Accept: text/event-stream" \
  -H "Content-Type: application/json" \
  -d '{"query":"test"}' \
  --max-time 30 | head -30

# NDJSON (Newline-Delimited JSON)
curl -s "$TARGET/api/live-feed" \
  -H "Authorization: Bearer $TOKEN" \
  --max-time 10 | head -5 | python3 -m json.tool

# Chunked transfer encoding
curl -s --raw "$TARGET/api/chunked" --max-time 10 | head -20
```

---

### FASE 8 — Bypass Proteksi Umum

| Proteksi | Cara Bypass |
|---|---|
| **Cloudflare** | `--tlsv1.3` + Chrome User-Agent + Origin/Referer header |
| **Rate limiting** | Tambah delay `sleep 1`, rotasi UUID/session, atau gunakan pool session |
| **CORS** | Buat proxy server lokal (tidak bisa bypass dari browser, bisa dari server) |
| **Captcha login** | Cari endpoint guest/anonim yang tidak butuh captcha |
| **X-Signature / HMAC** | Reverse-engineer dari JS bundle, temukan secret + algoritma signing |
| **Hotlink protection gambar** | Tambah header `Referer: https://target.com/` + Chrome UA |
| **Token expiry** | Cache token + deteksi 401 → refresh otomatis |
| **User-Agent detection** | Gunakan Chrome UA terbaru: `Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/138.0.0.0 Safari/537.36` |
| **IP geofencing** | Proxy atau VPS di region yang diizinkan |
| **Fingerprinting TLS** | Gunakan curl dengan `--tlsv1.3` atau impersonasi Chrome via library |
| **Anti-bot (bot score)** | Tambah header `sec-ch-ua`, `sec-fetch-*`, `Accept-Language` seperti browser nyata |

**Header browser lengkap untuk bypass fingerprinting:**
```bash
curl -s "$TARGET/api/endpoint" \
  --tlsv1.3 \
  -H "User-Agent: Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/138.0.0.0 Safari/537.36" \
  -H "Accept: application/json, text/plain, */*" \
  -H "Accept-Language: en-US,en;q=0.9" \
  -H "Accept-Encoding: gzip, deflate, br" \
  -H "Origin: https://target.com" \
  -H "Referer: https://target.com/" \
  -H "Sec-Ch-Ua: \"Chromium\";v=\"138\", \"Google Chrome\";v=\"138\"" \
  -H "Sec-Ch-Ua-Mobile: ?0" \
  -H "Sec-Ch-Ua-Platform: \"Windows\"" \
  -H "Sec-Fetch-Dest: empty" \
  -H "Sec-Fetch-Mode: cors" \
  -H "Sec-Fetch-Site: same-origin" \
  -H "Connection: keep-alive"
```

---

### FASE 9 — Analisis GraphQL (jika website pakai GraphQL)

```bash
TARGET="https://target.com"
TOKEN="..."

# 1. Introspection query — dapatkan seluruh skema
curl -s -X POST "$TARGET/graphql" \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $TOKEN" \
  -d '{
    "query": "{ __schema { types { name kind fields { name type { name kind ofType { name kind } } } } } }"
  }' | python3 -m json.tool | grep '"name"' | sort -u | head -50

# 2. Temukan semua Query yang tersedia
curl -s -X POST "$TARGET/graphql" \
  -H "Content-Type: application/json" \
  -d '{"query":"{ __schema { queryType { fields { name description args { name type { name } } } } } }"}' \
  | python3 -m json.tool

# 3. Temukan semua Mutation
curl -s -X POST "$TARGET/graphql" \
  -H "Content-Type: application/json" \
  -d '{"query":"{ __schema { mutationType { fields { name description } } } }"}' \
  | python3 -m json.tool

# 4. Test query sederhana
curl -s -X POST "$TARGET/graphql" \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $TOKEN" \
  -d '{"query":"{ me { id email name } }"}' \
  | python3 -m json.tool
```

---

### FASE 10 — Dokumentasi Hasil Recon

Setelah selesai recon, dokumentasikan:

```markdown
## Hasil Recon: target.com

### Tech Stack
- Frontend: Next.js / React
- Hosting: Vercel
- CDN: Cloudflare
- Backend: Node.js Express / Python FastAPI / etc

### Auth Mechanism
- Tipe: Bearer JWT / Cookie / API Key
- Cara dapat token: POST /api/auth/login dengan email+password
- Token TTL: ~24 jam (dari JWT exp field)
- Refresh: POST /api/auth/refresh dengan refresh_token

### Endpoint Utama
| Endpoint | Method | Auth | Deskripsi |
|---|---|---|---|
| /api/search | GET | ❌ | Search publik |
| /api/user/me | GET | ✅ Bearer | Profile user |
| /api/posts | POST | ✅ Bearer | Buat post baru |

### Format Request
- Content-Type: application/json
- Wajib header: User-Agent Chrome, Origin, Referer

### Format Response
- JSON standar dengan field: data, meta, error
- Pagination: cursor-based via `cursor` field

### Proteksi yang Ada
- Cloudflare → bypass dengan --tlsv1.3
- Rate limit: ~100 req/menit per IP
- CSRF token di form (tidak di JSON API)

### Catatan Khusus
- Model/versi API: v2 lebih stabil dari v1
- Ada endpoint undocumented: /api/internal/... (dari JS bundle)
```

---

## Tips Penting

1. **Selalu mulai dari robots.txt dan sitemap.xml** — sering ada petunjuk path yang tidak terdaftar di navigasi.
2. **Cek Network tab DevTools lebih dulu** dari curl — lebih cepat untuk memahami flow auth.
3. **Copy as cURL dari DevTools** adalah cara tercepat mendapat request yang valid untuk direplikasi.
4. **Decode JWT** untuk pahami field yang tersedia dan TTL token.
5. **Gunakan `python3 -m json.tool`** untuk pretty-print JSON response di terminal.
6. **Simpan cookie ke file** (`-c cookies.txt`) lalu reuse (`-b cookies.txt`) untuk session-based auth.
7. **Perhatikan `X-Request-ID`, `X-Trace-ID`** — beberapa server butuh UUID ini di header.
8. **Cari versi API** di JS bundle — `/v2/` mungkin tidak diumumkan tapi lebih stabil/lengkap.
9. **Test payload minimal** dulu — tambah field satu per satu sampai dapat response yang benar.
10. **Cek response header `X-RateLimit-*`** untuk tahu berapa limit yang berlaku.

## Tools yang Berguna

```bash
# Pretty print JSON
echo '{"key":"val"}' | python3 -m json.tool

# Decode JWT
TOKEN="eyJ..."
echo "$TOKEN" | cut -d'.' -f2 | base64 -d 2>/dev/null

# Generate UUID
python3 -c "import uuid; print(uuid.uuid4())"

# URL encode
python3 -c "import urllib.parse; print(urllib.parse.quote('hello world'))"

# Extract cookies dari curl verbose
curl -v "https://target.com" 2>&1 | grep "Set-Cookie"

# Follow redirects dan lihat tiap hop
curl -sL -D - "https://target.com/api/redirect" -o /dev/null

# Test dengan timeout ketat
curl -s --max-time 5 --connect-timeout 3 "https://target.com/api/test"
```
