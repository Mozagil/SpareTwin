# Karar kayıtları

Her önemli karar burada: ne seçildi, neden, neyi göze aldık. Bir karar değişirse eskisi silinmez, "yerine geçti" notu düşülür.

---

## K-001 · Backend: Supabase

**Tarih:** 30 Ekim 2026 · **Durum:** Yerine geçti → K-007

**Karar:** Veritabanı, kimlik doğrulama, dosya deposu ve sunucu fonksiyonları için Supabase.

**Neden:**
- Gerçek Postgres: ilişkisel parça modeli, görünümler, fonksiyonlar, RLS. KOBİ ERP fazına kadar aynı veritabanı taşır.
- WeWeb'in yerleşik Supabase entegrasyonu var (koleksiyon, Postgres fonksiyonu çağırma, Auth, Storage).
- Migrasyonlar kod olarak repoda; Codespace'te yerelde çalıştırılıp test edilebiliyor.
- AB bölgesinde barındırma; kurumsal müşteriye kendi sunucusunda kurulum seçeneği (enTIRE'ın "veri sizin sunucunuzda" ilkesine karşılık).

**Değerlendirilen alternatif:** Xano. WeWeb ile çok iyi çalışıyor, iş kuralını görsel yazmak kolay. Ancak kurallar repoda kod olarak durmuyor, test etmek ve sürüm kontrolü zor, kendi sunucuda kurulum seçeneği sınırlı.

**Göze alınan:** İş kuralları PL/pgSQL ile yazılıyor; bu dili bilen geliştirici gerekir.

---

## K-002 · Genel parça ikizi modeli, lastik bir modül

**Tarih:** 30 Ekim 2026 · **Durum:** Kabul

**Karar:** Çekirdek tablolarda lastiğe özgü hiçbir kolon yok. Lastik ve jant, kategori + ölçüm profili + uzantı tablosu (`tire_specs`, `rim_specs`) ile tanımlanıyor.

**Neden:** "Herhangi bir makinenin yedek parçası için de aynı mantık" hedefi. TireIQ'yu ayrı ürün olarak yazıp sonra genelleştirmek, iki kez yazmak demek.

**Göze alınan:** İlk günden biraz daha soyut bir şema. Ölçümler `metric/value` satırları olduğu için bazı sorgular daha uzun. Görünümler (`v_tire_health`) bunu arayüzden gizliyor.

---

## K-003 · İş kuralları veritabanında, arayüz sadece arayüz

**Tarih:** 30 Ekim 2026 · **Durum:** Kabul

**Karar:** Durum değiştiren her işlem Postgres fonksiyonundan geçer; hesaplanan her değer görünümden okunur. Arayüzde ve API'de iş kuralı tekrar yazılmaz. (K-007 ile birlikte de geçerli: API bu fonksiyonları çağırır.)

**Neden:** Tek doğruluk kaynağı. Mobil uygulama, TPMS entegrasyonu veya müşteri ERP'si bağlandığında kurallar tekrar yazılmaz. Kurallar pgTAP ile test edilir.

---

## K-004 · Önce TireIQ, ERP üretim modülleri en son

**Tarih:** 30 Ekim 2026 · **Durum:** Önerildi, onay bekliyor

**Karar:** Faz sırası: Temel → TireIQ → yedek parça/stok/bakım → SaaS → üretim/mühendislik → akıllı katman.

**Neden:** TireIQ dar, satışı kolay, ROI'si görünür. Üretim modülleri (BOM, eBOM→mBOM, MRP) firmaya özel ve büyük; çekirdek ve ilk gelir oturmadan başlamak riskli.

**Açık soru:** Elinizde hazır bir makine imalatçısı pilot varsa Faz 4'ün BOM içe aktarma ve iş emri kısmı Faz 2'ye paralel öne çekilebilir.

---

## K-005 · Önce web, mobil sonra

**Tarih:** 30 Ekim 2026 · **Durum:** Kabul

**Karar:** Saha inspeksiyonu Faz 1'de web uygulamasının mobil uyumlu sayfasıyla yapılır; PWA Faz 3'te, native uygulama Faz 5'te ve ancak net bir ihtiyaç varsa (RFID, tam çevrimdışı).

**Neden:** Tek kod tabanı, hızlı yineleme. QR okuma ve kamera telefon tarayıcısında çalışıyor.

**Göze alınan:** Zayıf internetli sahada (maden ocağı) çevrimdışı çalışma Faz 3'e kadar sınırlı. Pilot seçerken saha bağlantısı kontrol edilmeli.

---

## K-006 · Lastik ömrü için önce doğrusal model

**Tarih:** 30 Ekim 2026 · **Durum:** Kabul

**Karar:** Kalan saat tahmini, orijinal diş derinliğinden bugüne doğrusal aşınma hızıyla hesaplanır.

**Neden:** Az veriyle çalışır, açıklanabilir ("şu hızla şu kadar kaldı"), TireIQ sunumundaki model merdiveninin ilk basamağı. Daha karmaşık model geldiğinde görünümün çıktı kolonları aynı kalır.

---

## K-007 · Kendi backend'imiz: Python + FastAPI + PostgreSQL

**Tarih:** 30 Ekim 2026 · **Durum:** Kabul · **K-001'in yerine geçer**

**Karar:** Supabase yerine kendi API'miz. Python 3.12, FastAPI, psycopg 3, PostgreSQL 17. Kimlik doğrulama kendimizde (argon2id + JWT + dönen yenileme token'ı). Dosyalar disk veya S3 uyumlu depoda.

**Neden:**
- Müşterinin kendi sunucusunda çalışabilmesi (enTIRE'ın en güçlü satış argümanı). Supabase'in kendi sunucuda kurulumu çok sayıda servisten oluşuyor ve bunu her müşteride işletmek ağır.
- Tam kontrol: kimlik, dosya, iş akışları ve ileride entegrasyonlar (TPMS, telematik, ERP) tek kod tabanında.
- Python, Faz 5'teki ömür tahmini (scikit-learn, XGBoost) ile aynı dil.

**Korunan:** PostgreSQL şeması, RLS, iş kuralı fonksiyonları ve görünümler aynen kaldı. Değişen: Supabase'in hazır kullanıcı tablosu yerine `app_users`, `auth.uid()` yerine `app.current_user_id()`, Supabase Storage yerine kendi depo katmanımız, otomatik REST yerine FastAPI uç noktaları.

**Göze alınan:** Sunucuyu, yedeği, güvenlik yamalarını biz işletiyoruz. Parola sıfırlama, davet, SSO gibi hazır gelen özellikleri kendimiz yazacağız (Faz 3).

---

## K-008 · Dağıtım: önce bulut, sonra müşteri sunucusu, tek paket

**Tarih:** 30 Ekim 2026 · **Durum:** Kabul

**Karar:** Faz 0–2 boyunca tek bir bulut kurulumu (AB bölgesinde VPS, çok firmalı). Müşteri sunucusuna kurulum Faz 3'te. İkisi aynı Docker Compose paketinden çıkar; fark `DEPLOYMENT_MODE` ve ayarlar.

**Neden:** KOBİ'lerin çoğunun IT ekibi yok; bulut onlar için daha kolay ve bizim için ürünü hızlı geliştirmenin yolu. Büyük veya verisi hassas müşteri için müşteri sunucusu seçeneği (TireIQ sunumundaki Enterprise planı).

**Bugünden uyulan kurallar:** Zorunlu dış servis yok; migrasyonlar imajda ve açılışta otomatik; dosya deposu değiştirilebilir; HTTPS Caddy ile; veritabanı dışarıya kapalı.

**Açık konular (Faz 3):** İç ağda HTTPS sertifikası, lisans dosyası, sahadan sunucuya erişim (Wi-Fi, VPN), müşteri verisiyle ortak yapay zekâ modeli eğitimi için onaylı anonim veri paylaşımı.

---

## K-009 · Dosyaya erişim yalnızca API üzerinden, kısa ömürlü linkle

**Tarih:** 30 Ekim 2026 · **Durum:** Kabul

**Karar:** Depo hiçbir zaman herkese açık değil. İstemci önce oturumla `GET /media/{id}/url` çağırır, birkaç dakika geçerli imzalı link alır. Dosya türü uzantıdan değil içerikten tespit edilir.

**Neden:** Firma izolasyonu dosyalarda da geçerli olmalı. Yerel diskte ve S3'te aynı davranış; müşteri sunucusuna taşınırken değişiklik gerekmez.

---

## K-010 · Frontend: React (WeWeb yerine)

**Tarih:** 2 Kasım 2026 · **Durum:** Kabul

**Karar:** Arayüz WeWeb yerine kendi kodumuzla: React 19 + TypeScript + Vite, veri için TanStack Query, yönlendirme için React Router. Stil, prototipteki tasarım jetonlarıyla düz CSS.

**Neden:**
- Geliştirme ve test Codespace'te `localhost` mantığıyla yapılır; API portunu dışarı açmak gerekmez (Vite, `/api` isteklerini içeriden FastAPI'ye aktarır).
- Müşteri sunucusuna kurulum (K-008) için ücretli dışa aktarma gerekmez; derleme çıktısı statik dosyadır, Caddy ile aynı sunucudan sunulur.
- Supabase'den kendi backend'imize geçişle (K-007) aynı mantık: bağımlılık yok, her şey repoda, testli.
- Ekranlar backend gibi yazılıp test edilerek zip olarak teslim edilebiliyor.

**Göze alınan:** Ekran değişiklikleri görsel editörle değil kodla yapılır.

**Güvenlik notları:** Erişim token'ı yalnızca bellekte; yenileme token'ı tarayıcı deposunda (Faz 3'te httpOnly çerezli akış değerlendirilecek). Arayüz API'ye aynı adresten bağlandığı için CORS kapalı.

---

## K-011 · Görseller sunucuda işlenir; konum bilgisi saklanmaz

**Tarih:** 2 Kasım 2026 · **Durum:** Kabul

**Karar:** Yüklenen her JPEG/PNG/WEBP sunucuda yeniden kaydedilir: telefonun yön bilgisine göre döndürülür, uzun kenarı 1600 piksele küçültülür ve bütün meta veri (GPS konumu, cihaz bilgisi) silinir. Katalog kalemi, makine modeli ve makine için firma başına tek görsel tutulur; ortak kütüphanedeki kalemlere her firma kendi görselini koyar.

**Neden:** Sahada çekilen fotoğraflar çalışanın ve sahanın konumunu içerebilir; bunu saklamak gereksiz bir KVKK riski. Küçültme, sahadaki zayıf mobil bağlantıda sayfaların hızlı açılmasını sağlar.

**Göze alınan:** Orijinal yüksek çözünürlüklü dosya saklanmaz. Hasar incelemesi için daha yüksek çözünürlük gerekirse sınır ayarlanabilir. HEIC (iPhone) dosyaları şimdilik işlenmeden saklanır; Faz 1'deki mobil formda tarayıcı fotoğrafı yüklemeden önce JPEG'e çevirecek.

**Telif notu:** Üretici görselleri otomatik olarak internetten çekilmez; firmalar kendi çektikleri ya da kullanım izni olan görselleri yükler.
