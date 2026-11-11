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

---

## K-012 · Toplu içe aktarma: önce önizleme, sonra ya hepsi ya hiçbiri

**Tarih:** 2 Kasım 2026 · **Durum:** Kabul

**Karar:** Excel/CSV yüklenince önce her satır doğrulanır ve sonuç gösterilir; hiçbir şey yazılmaz. Onaylanınca aynı doğrulama tek bir veritabanı işlemi içinde tekrarlanır; tek satırda bile hata varsa hiçbir şey kaydedilmez. Lastik takma, normal arayüzdeki ile aynı veritabanı fonksiyonundan (`install_part_item`) geçer.

**Neden:** Yarım kalan bir içe aktarma (300 satırın 180'i kaydedilmiş) düzeltmesi en zor veri karmaşasıdır. Kullanıcı hatayı Excel'de düzeltip aynı dosyayı tekrar yükler. Kuralların tek yerde olması, içe aktarılan verinin elle girilenle aynı kurallara uymasını sağlar.

**Dayanıklılık:** Sütun başlıkları esnek eşlenir ("Seri no", "Seri numarası", "Serial"), Türkçe ondalık ("12,5") ve tarih ("15.10.2026") okunur, Türkçe Windows Excel'in noktalı virgüllü CSV'si kabul edilir. Excel dosyaları `defusedxml` ile okunur (XML tabanlı saldırılara karşı).

**Sınırlar:** Tek seferde 2.000 satır, 5 MB. Şimdilik yalnızca takılı lastikler; stoktaki lastikler ve diğer parça tipleri sonraki adımlarda.

---

## K-013 · Stok seviyesi hareketlerden hesaplanır

**Tarih:** 4 Kasım 2026 · **Durum:** Kabul

**Karar:** Sarf malzemeleri için ayrı bir "stok miktarı" alanı tutulmaz; seviye her zaman `stock_movements` defterinin toplamıdır. Defter değiştirilemez; sayım farkı yeni bir "sayım düzeltmesi" hareketiyle yazılır. Eksi stoğa düşülemez (aynı kalem+depo için hareketler sıraya girer). Çıkışlar ağırlıklı ortalama maliyetle yazılır ve makineye bağlanabilir.

**Neden:** Miktar alanı ile hareket geçmişi zamanla çelişir ("sistemde 12 yazıyor ama hareketler 10 diyor"). Tek kaynak bu çelişkiyi imkânsız kılar ve her sayının nereden geldiği izlenebilir. Makineye bağlanan çıkışlar, toplam sahip olma maliyetinin (Faz 2 sonu) temelidir.

**Seri numaralı parçalar:** Lastik, jant, silindir gibi parçalar zaten tek tek izleniyor; stoktakiler aynı görünümde sayılır, girişleri "Parça teslim al" ile yapılır.

---

## K-014 · TireIQ taslağı arşivlendi; üç parçası SpareTwin'e taşındı

**Tarih:** 9 Kasım 2026 · **Durum:** Kabul

**Karar:** Ayrı bir monorepo olarak başlanan ve commit atılmadan bırakılan TireIQ taslağı (FastAPI + SQLAlchemy + Next.js, yalnızca lastik) devam ettirilmez. Yol haritasına uyan üç parçası SpareTwin'e, bizim mimariyle (RLS, kurallar veritabanında, bildirimler güncel veriden) yeniden yazılarak alındı:

1. **Firma başına uyarı eşikleri.** Koda gömülü %20 / %40 / %90 / 30 gün değerleri `tenants.settings->'thresholds'` içine taşındı; görünümler (`v_part_health`, `v_rim_compliance`) ve bildirimler firmanın ayarını okur, yoksa aynı varsayılanlar geçerli.
2. **Uyarı yaşam döngüsü.** TireIQ'daki tekilleştirme / yükselme / kendiliğinden kapanma kuralları, bildirim anahtarının durumu da içermesi sayesinde tablo eklemeden karşılandı: ekip bazlı "üstlen" ve "gizle" durumu anahtara bağlıdır; durum kötüleşince anahtar değişir ve kayıt düşer, sorun geçince anahtar listeden çıkar ve kayıt temizlenir. Okundu bilgisi kişisel kalır.
3. **Denetim kaydı.** Faz 3'ten öne çekildi. Uç noktalara dokunmadan HTTP ara katmanı yazar; uygulama rolünün tabloya yazma yetkisi yoktur, yalnızca yöneticiler okur.

**Alınmayanlar:** Aşınma ölçeği (bizde zaten kullanılabilir derinlik üzerinden hesaplanıyor), `@tireiq/ui` design system paketi (kendi görsel dilimiz oturmuş), uygulama katmanında kiracı filtresi (bizde RLS veritabanında zorluyor).

**Neden:** TireIQ lastiğe kilitli, SpareTwin genel parça modeli; iki kod tabanı taşımak iki kat bakım demek. Taslaktaki iyi fikirler kodla değil kuralla alındı, böylece aynı davranış her parça tipi için geçerli.

**Göze alınan:** Eşik değişikliği bütün filoya anında uygulanır; geçmişe dönük "o gün kritik miydi" sorusu için denetim kaydındaki eşik değişiklikleri referanstır.

## K-015 · Satınalma teslimatı stok kapısından geçer; ihtiyaç kuralla hesaplanır

**Karar:** Satınalma modülü (`0014`) kendi stok sayısı tutmaz. Teslim alma, kalem türüne göre zaten var olan iki girişten birini çağırır: sarf kalemi için `stock_move('in')` (maliyet = sipariş fiyatı, referans = sipariş no / irsaliye), seri numaralı parça için `part_items` + `received` olayı. Talep ve sipariş aynı tabloda yaşar (`status`: draft → ordered → partial → received, ya da cancelled); durum satırlardaki teslim miktarından hesaplanır. İhtiyaç önerisi bir görünümdür (`v_purchase_needs`): yaklaşan değişimler (kritik ya da *değişim ufku* saatinden az ömrü kalan takılı parçalar) + kritik seviye − stok − siparişte.

**Neden:** "Stokta kaç var" sorusunun tek cevabı olmalı (K-013). Ayrı bir satınalma stoğu ya da "yolda" sayacı tutulsa defterle çelişirdi. İhtiyacın görünüm olması, bildirim, dashboard ve Satınalma sayfasının aynı cümleyi söylemesini sağlar; eşik (ufuk) firma ayarıdır.

**Göze alınan:** Talep aşamasında kalem değişebilir, sipariş verildikten sonra değişmez (yeni talep açılır); kısmi teslimatlı sipariş iptal edilemez, kalanı kapatılır. Fiyat teklifi karşılaştırma ve tedarikçi performansı bu sürümde yok.

## K-016 · Makine durumu iş emirlerinden türer; bakım sarfı stok kapısından düşer

**Karar:** Bakım modülü (`0015`) makine durumunu elle değil kuralla yönetir: açık arıza emri varken makine `down`, süren planlı emir varken `maintenance`, emir kalmayınca `active` (`app.asset_refresh_status`, iş emri tetikleyicisiyle). Duruş süresi arıza emrinin *makine durdu* → *çalışmaya döndü* farkıdır; ayrı duruş kaydı yok. Planın sarf listesi (filtre 4 adet, yağ 60 litre) emre kopyalanır ve emir tamamlanınca `stock_move('out')` ile makineye kullanım olarak düşer (referans = emir no); stok yetmezse emir tamamlanamaz. Tamamlarken girilen makine saati sayaçtan büyükse `record_meter_reading` ile sayaç da ilerler. Sıradaki bakım bir görünümdür (`v_maintenance_due`): son tamamlanan emrin saati/tarihi + periyot; hiç yapılmamışsa saat için bir sonraki periyot katı, takvim için plan tarihi + periyot.

**Neden:** "Makine çalışıyor mu" sorusunun tek cevabı olmalı; elle `down` işaretlenen ama emri olmayan makine ile emri olup `active` görünen makine aynı anda var olamaz. Sarfın stoktan emirle düşmesi, K-013'teki tek defter ilkesini korur ve bakım maliyetini (işçilik + dış servis + sarf) kendiliğinden toplar. Görünüm olması, bildirim, dashboard, makine sayfası ve Bakım › Takvim'in aynı cümleyi söylemesini sağlar; *yaklaşıyor* eşiği firma ayarıdır.

**Göze alınan:** Seri numaralı parça değişimi (lastik, silindir) emrin sarf listesine girmez; makine sayfasından tak/sök ile yapılır ve kendi maliyetini taşır. Planlı emirde iptal yöneticiye, başlatma ve tamamlama teknisyene aittir. Elle `maintenance` durumu, bir emir kapanınca `active`'e döner.

## K-017 · Toplam sahip olma maliyeti defterlerden toplanır; parça ilk takıldığı makineye yazılır

**Karar:** Maliyet raporu (`0016`, `asset_tco`) yeni tablo tutmaz; her kalem kendi defterinden okunur. *Parça:* seri numaralı parçanın alış maliyeti ilk takıldığı makineye ve takıldığı güne yazılır; tamir / yenileme gibi olay maliyetleri olayın makinesine, makine yazılmamışsa parçanın o andan önce en son takıldığı makineye gider. *Sarf:* stok defterinden makineye yapılan çıkışlar (iş emrinin sarfı da buradan geçtiği için bir kez sayılır). *İşçilik ve dış servis:* tamamlanan iş emirleri. *Duruş:* arıza emirlerinin duruş aralığının döneme düşen kısmı × firmanın duruş saat maliyeti (`thresholds.downtime_cost_per_hour`, varsayılan 0 = hesaplanmaz); süren arıza bugüne kadar sayılır, iptal edilen emir sayılmaz. Saat başı maliyet, toplamın dönemdeki çalışma saatine bölümüdür; çalışma saati sayaç okumaları, tamamlanan kontroller ve iş emirlerindeki makine saatinden, dönem başı iki okuma arasından interpolasyonla bulunur.

**Neden:** Stok (K-013) ve bakım (K-016) ile aynı ilke: bir sayının tek kaynağı olmalı. Ayrı bir maliyet tablosu defterlerle zamanla çelişirdi. Alışı ilk takılışa yazmak "bu makineye bu yıl ne harcadık" sorusuna nakit bazlı, açıklaması tek cümle olan bir cevap verir; rotasyonla başka makineye geçen lastik iki kez sayılmaz.

**Göze alınan:** Nakit bazlı olduğu için lastik takımı değişen ay maliyet sıçrar; ömre yayılmış (amortisman) görünüm yok, lastikte bunu saat başı beklenen maliyet (`v_tire_health`) veriyor. İkinci el aktarılan parçanın maliyeti ilk makinede kalır. Duruş saat maliyeti firma oranıdır; makineye özel oran (`0017`, `assets.downtime_cost_per_hour`) doluysa onun yerine geçer, 0 da geçerli bir orandır (o makinenin duruşu maliyet yazmaz). Oran tarihçesi tutulmaz: değişen oran geçmiş dönemin raporunu da değiştirir. Saat kaydı dönem başını kapsamıyorsa saat başı maliyet olduğundan yüksek çıkar; arayüz bunu yıldızla belirtir.
