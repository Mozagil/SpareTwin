# SpareTwin

Makine imalatçıları, üretim fabrikaları ve iş makinesi filoları için **dijital parça ikizi** platformu. Her lastik, jant, hidrolik silindir, pompa veya akü, alındığı günden hurdaya ayrıldığı güne kadar kendi geçmişiyle izlenir: hangi makinede kaç saat çalıştı, nasıl aşındı, ne kadara mal oldu, ne kadar ömrü kaldı.

İlk dikey paket **TireIQ**: OTR ve iş makinesi lastikleri ile jantlar için Türkiye pazarına uyarlanmış lastik yönetimi. Aynı çekirdek, sonraki fazlarda her türlü yedek parçaya ve KOBİ üretim süreçlerine (BOM, iş emri, MRP) genişler.

| Katman | Teknoloji |
|---|---|
| Arayüz | WeWeb (REST API'ye bağlanır) |
| API | Python 3.12 + FastAPI |
| Veritabanı | PostgreSQL 17, satır bazlı güvenlik (RLS) ile firma izolasyonu |
| Dosyalar | Sunucu diski veya S3 uyumlu depo |
| Dağıtım | Docker Compose + Caddy (otomatik HTTPS). Önce bulut, sonra müşteri sunucusu |

## Repo haritası

| Yol | İçerik |
|---|---|
| `backend/sparetwin/` | FastAPI uygulaması: kimlik, kayıt, filo, yaşam döngüsü, inspeksiyon, dosyalar, QR etiket |
| `backend/tests/` | 43 test: kimlik, firma izolasyonu, kayıt, iş kuralları, fotoğraf, etiket, S3 |
| `db/migrations/` | Şema, RLS, iş kuralları, TireIQ modülü, kimlik fonksiyonları |
| `db/seed/demo.sql` | Demo firma: 4 makine, 29 takılı parça, ölçüm geçmişi |
| `deploy/` | Canlı ortam: compose, Caddyfile, yedekleme betiği |
| `prototype/index.html` | Filo dashboard prototipi (WeWeb için görsel referans) |
| `docs/` | Vizyon, mimari, veri modeli, yol haritası, UX, WeWeb rehberi, kararlar |

## Codespace'te başlangıç

Codespace iki container ile açılır (Python 3.12 + PostgreSQL 17); Python paketleri kurulur ve `.env` oluşturulur.

```bash
make reset      # şemayı kur + demo veri
make api        # API: 8000 portu, dokümantasyon /docs
make test       # 43 test
make prototype  # dashboard prototipi: 8080 portu
```

Demo giriş bilgileri (yalnızca geliştirme):

| E-posta | Parola | Rol |
|---|---|---|
| `yonetici@demo.sparetwin.dev` | `demo-parola-2026` | owner |
| `teknisyen@demo.sparetwin.dev` | `demo-parola-2026` | technician |

API'yi denemenin en kolay yolu: `make api` → **Ports** sekmesinde 8000 → tarayıcıda `/docs` → **POST /auth/login** ile giriş → dönen `access_token`'ı sağ üstteki **Authorize** düğmesine yapıştır.

### WeWeb'i Codespace'teki API'ye bağlamak (geliştirme)

WeWeb bulutta çalıştığı için API'ye internetten ulaşması gerekir:

1. **Ports** sekmesinde 8000 portuna sağ tık → **Port Visibility → Public**.
2. Görünen `https://...-8000.app.github.dev` adresini kopyala; `.env` içinde `PUBLIC_BASE_URL` olarak yaz ve `make api`'yi yeniden başlat.
3. WeWeb'de bu adresi API taban adresi olarak kullan (`docs/06-weweb-rehberi.md`).

Şirket hesabında portu herkese açma yasaklanmışsa bu adım çalışmaz; o durumda Faz 0 sonundaki geliştirme sunucusunu (`deploy/`) bekleriz. Herkese açık portta yalnızca demo veri olmalı.

### Zip'ten gelen güncellemeyi uygulama

```bash
unzip -o SpareTwin-*.zip -d /tmp/st && cp -r /tmp/st/SpareTwin/. . && rm -rf /tmp/st SpareTwin-*.zip
git status            # neler değişti
make reset && make test
```

Bir dosyanın silinmesi gerekiyorsa (bu sürümdeki `supabase/` klasörü ve `package.json` gibi) zip'in yanında not olarak belirtilir.

## Canlı ortam

Şimdilik yok; her şey Codespace'te çalışıyor. Sunucu ve alan adı işlerine geçildiğinde `deploy/` klasöründeki paket kullanılacak (Caddy ile HTTPS, API, PostgreSQL, yedekleme betiği).

## Şu anki durum

Faz 0'ın backend tarafı hazır ve test edildi (kayıt ve QR etiket dahil). Sıradaki iş: WeWeb arayüzünü Codespace'teki API'ye bağlamak. Ayrıntı: `docs/04-yol-haritasi.md`.
