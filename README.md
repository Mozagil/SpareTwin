# SpareTwin

Makine imalatçıları, üretim fabrikaları ve iş makinesi filoları için **dijital parça ikizi** platformu. Her lastik, jant, hidrolik silindir, pompa veya akü, alındığı günden hurdaya ayrıldığı güne kadar kendi geçmişiyle izlenir: hangi makinede kaç saat çalıştı, nasıl aşındı, ne kadara mal oldu, ne kadar ömrü kaldı.

İlk dikey paket **TireIQ**: OTR ve iş makinesi lastikleri ile jantlar için Türkiye pazarına uyarlanmış lastik yönetimi. Aynı çekirdek, sonraki fazlarda her türlü yedek parçaya ve KOBİ üretim süreçlerine (BOM, iş emri, MRP) genişler.

| Katman | Teknoloji |
|---|---|
| Arayüz | React 19 + TypeScript (Vite) |
| API | Python 3.12 + FastAPI |
| Veritabanı | PostgreSQL 17, satır bazlı güvenlik (RLS) ile firma izolasyonu |
| Dosyalar | Sunucu diski veya S3 uyumlu depo |
| Dağıtım | Docker Compose + Caddy (otomatik HTTPS). Önce bulut, sonra müşteri sunucusu |

## Repo haritası

| Yol | İçerik |
|---|---|
| `frontend/` | React uygulaması: giriş, filo dashboard'u, makine ve parça sayfaları, kayıt, etiketler |
| `backend/sparetwin/` | FastAPI: kimlik, kayıt, filo, yaşam döngüsü, inspeksiyon, dosyalar, QR etiket |
| `backend/tests/` | 116 test: kimlik, firma izolasyonu, kayıt, Excel içe aktarma, PDF rapor, jant ve bildirimler, stok, iş kuralları, kontrol formu, görseller ve gizlilik, etiket, S3, şema sıfırlama, firma eşikleri, bildirim durumu, denetim kaydı, satınalma, bakım |
| `db/migrations/` | Şema, RLS, iş kuralları, TireIQ modülü, kimlik fonksiyonları |
| `db/seed/demo.sql` | Demo firma: 4 makine, 29 takılı parça, ölçüm geçmişi |
| `deploy/` | Canlı ortam paketi (şimdilik kullanılmıyor) |
| `prototype/index.html` | İlk tasarım taslağı (statik, demo verili) |
| `docs/` | Vizyon, mimari, veri modeli, yol haritası, UX, frontend rehberi, kararlar |

## Codespace'te çalıştırma

Codespace iki container ile açılır: Python 3.12 + Node 22 çalışma ortamı ve PostgreSQL 17. Paketler kurulur, `.env` oluşturulur.

```bash
make reset   # şemayı kur + demo veri
make dev     # API + uygulama birlikte → Ports sekmesinde 5173'ü aç
make test    # 116 backend + 37 frontend testi
```

Demo giriş bilgileri (yalnızca geliştirme):

| E-posta | Parola | Rol |
|---|---|---|
| `yonetici@demo.sparetwin.dev` | `demo-parola-2026` | owner |
| `teknisyen@demo.sparetwin.dev` | `demo-parola-2026` | technician |

Hiçbir portu herkese açmaya gerek yok. Uygulama (5173) API'ye Codespace'in içinden bağlanır. API dokümanı için Ports sekmesinden 8000 açılıp sonuna `/docs` eklenebilir.

Diğer komutlar için `make` yazın.

### Telefondan deneme (mobil kontrol formu)

1. `make dev` çalışırken telefonda tarayıcıyı aç ve GitHub'a aynı hesapla giriş yap.
2. Bilgisayarda Ports sekmesinde 5173 satırındaki adresi kopyala (`https://…-5173.app.github.dev`), telefona gönder ve aç.
3. Teknisyen hesabıyla giriş yap → alttaki menüden **Kontrol** → **QR kodunu okut**. Kamera izni istendiğinde izin ver.

Adres HTTPS olduğu için kamera çalışır; portu herkese açmaya gerek yoktur. QR etiketlerini **Etiketler** sayfasından yazdırabilir ya da ekrandaki etiketi telefonla okutabilirsin.

### Sık karşılaşılanlar

| Mesaj | Çözüm |
|---|---|
| `Python paketleri kurulu değil` / `Frontend paketleri kurulu değil` | `make setup` |
| Terminaldeki `http://localhost:5173` bağlantısı açılmıyor | O adres Codespace'in içini gösterir. Ports sekmesinde 5173 satırındaki 🌐 simgesine tıkla; 5173 listede yoksa **Add Port** → `5173` |
| `Port dolu: [5173, 8000]` | Arka planda eski sunucu kalmış: `make stop`, sonra `make dev` |
| Girişte "Sunucuya ulaşılamıyor" | API çalışmıyor: `make stop`, sonra `make dev` |
| Tarayıcı konsolunda `github.dev/pf-signin` uyarısı | Uygulamayı VS Code içindeki önizlemede değil, Ports sekmesindeki 🌐 simgesiyle ayrı sekmede aç |

### Zip'ten gelen güncellemeyi uygulama

```bash
unzip -o SpareTwin-*.zip -d /tmp/st && cp -r /tmp/st/SpareTwin/. . && rm -rf /tmp/st SpareTwin-*.zip
git status            # neler değişti
make setup && make reset && make test
```

Bir dosyanın silinmesi gerekiyorsa zip'in yanında not olarak belirtilir. `.devcontainer` değiştiyse container yeniden derlenir (**Codespaces: Rebuild Container**).

## Canlı ortam

Şimdilik yok; her şey Codespace'te çalışıyor. Sunucu ve alan adı işlerine geçildiğinde `deploy/` klasöründeki paket kullanılacak (Caddy ile HTTPS, API, PostgreSQL, yedekleme betiği).

## Şu anki durum

Faz 0 tamamlandı. Faz 1 (TireIQ MVP) yazılım tarafı tamamlandı (v1.0): görseller, mobil kontrol formu, Excel ile toplu içe aktarma, PDF rapor, jant uyumluluğu (lastikle birlikte takma, Excel), rotasyon ve uygulama içi bildirimler. v1.2: eski TireIQ taslağından devralınan firma eşikleri (kritik/izleme yüzdesi, jant ve kontrol aralığı), bildirimde ekip bazlı üstlen/gizle ve denetim kaydı; hepsi yöneticinin **Ayarlar** sayfasında. Faz 2 sürüyor: depo ve stok (v1.1) ile satınalma (v1.3: tedarikçi, talep → sipariş → teslim alma, "LD-07 için 2 lastik yaklaşıyor, stokta 1 var" ihtiyaç önerisi) ve bakım (v1.4: saat/takvim bazlı planlar, planlı ve arıza iş emirleri, duruş süresi, tamamlanınca sarf stoktan düşer ve makine durumu kendiliğinden değişir) hazır; sırada makine toplam sahip olma maliyeti. Ayrıntı: `docs/04-yol-haritasi.md`.
