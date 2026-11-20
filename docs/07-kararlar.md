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

## K-018 · Tedarikçi karşılaştırma veri girişi istemez; sipariş ve teslim alma kayıtlarından hesaplanır

**Karar:** Tedarikçi karşılaştırma (`GET /purchasing/supplier-comparison`) yeni tablo ya da giriş ekranı açmaz. Kaynak, verilmiş siparişlerdir (`ordered`, `partial`, `received`; talep ve iptal sayılmaz), dönem sipariş tarihine göredir. *Kaç kez:* kalemin geçtiği sipariş sayısı (açık sipariş de alımdır). *Fiyat:* miktar ağırlıklı ortalama birim fiyat ve son alış fiyatı. *Teslim süresi:* sipariş tarihinden kalemin son teslimatına kadar; yalnızca tamamı teslim alınan kalemler ölçülür. *Zamanında:* son teslimat siparişteki beklenen tarihte ya da öncesindeyse. *Eksik teslim:* kalanı kapatılan kalem. "En ucuz" ve "En hızlı" işareti, o kalemde en az iki tedarikçinin verisi varsa ve biri açıkça öndeyse konur; eşitlikte kimse işaretlenmez. Tek bir puan üretilmez.

**Neden:** Teklifleri elle girip yan yana bakmak Excel'de yapılanı programa taşımaktan öteye geçmez; kullanıcı zaten yaptığı işi (sipariş ver, teslim al) yaparken karşılaştırma kendiliğinden çıkmalı. Tek puan yerine iki ayrı işaret, "neden bu tedarikçi" sorusunun cevabını gizlemez: ucuz olan geç getiriyorsa kararı işin aciliyeti verir. Aynı özet sipariş açarken kalemin altında görünür; karar orada verilir.

**Göze alınan:** Sipariş geçmişi biriktikçe anlam kazanır; ilk aylarda tablo boş ya da tek tedarikçili görünür. Karşılaştırma aynı katalog kalemi içindir; muadil ürün ayrı kalemse yan yana gelmez. Beklenen tarihi girilmemiş sipariş zamanında oranına girmez. Fiyat teklifi toplama (tedarikçinin link üzerinden kendi teklifini girmesi) e-posta altyapısıyla birlikte Faz 3'e bırakıldı.

## K-019 · Sökme sebebi sabit listeden seçilir; firmaya özel sebep yok

**Karar:** Parça sökülürken sebep sekiz maddelik sabit listeden seçilir (aşınma, kesik / yırtık, darbe, ayrışma, basınç kaybı, sızıntı, rotasyon, diğer); API listede olmayan değeri reddeder. Firmanın kendi sebebini eklemesi yol haritasından çıkarıldı. Sebep raporu (`GET /reports/removal-reasons`) sökme olaylarını (`part_events`, `removed`) sebebe, katalog kalemine ve makineye göre sayar; her grupta sökme anındaki ortalama çalışma saatini verir. Rotasyon bir sökme sebebi değil yer değişimidir: ayrı sayılır, paylara girmez. Listede olmayan eski kodlar raporda "diğer" altında toplanır.

**Neden:** Serbest ya da firmaya özel sebep, aynı şeyi birkaç ada böler ("kesik", "yırtık", "kesilme"); zaman içinde ve firmalar arasında karşılaştırma yapılamaz. Sabit liste, veriyi baştan temiz toplar; ileride lastik modeli ya da saha bazında "hangi sebep ömrü ne kadar kısaltıyor" sorusu ancak böyle cevaplanır. Ayrıntı isteyen teknisyen sökme notuna yazar.

**Göze alınan:** Listeye uymayan durum "diğer"e düşer; "diğer" payı büyürse listeye yeni madde eklemek gerekir (herkes için, migrasyonsuz: liste kodda). Sebepler lastik ağırlıklıdır; lastik dışı parçalarda çoğu sökme "aşınma", "sızıntı" ya da "diğer" olur.

## K-020 · Model parça listesi yol gösterir, engel koymaz; tam katalog değil kritik kalemler

**Karar:** Model parça listesi (`0019`, `model_parts`) firmaya aittir ve iki tür satır tutar: yuvaya bağlı ("bu yuvaya bu katalog kalemi uyar"; miktar hep 1, bir yuvaya birden çok alternatif yazılabilir) ve makine geneli (sarf ya da yedek; miktar makine başına kullanım). Yuvaya yalnızca seri numaralı ve yuvanın parça tipindeki kalem yazılır. Takma kuralı değişmez: `install_part_item` yine yalnızca yuvanın parça tipini denetler. Liste arayüzde yol gösterir: takma penceresi stokta önce listeye uyanları gösterir, kullanıcı isterse diğerlerini açar; boş yuvada uygun kalem ve stok durumu görünür. Excel içe aktarma parça numarasıyla eşleşir ve ya hepsini yazar ya hiçbirini.

**Neden:** Üreticinin binlerce satırlık tam parça kataloğunu kimse girmez; girilse de bakımı yapılmaz. Hedef, firmanın zaten izlediği 20 ila 50 kritik kalemdir. Listeyi katı kural yapmak (listede olmayan parça takılamaz) sahada işi durdurur: muadil lastik geldiğinde teknisyen takamaz, liste de çoğu zaman eksiktir. Yol göstermek yanlış ebat takma hatasını azaltır ama kararı sahaya bırakır.

**Göze alınan:** Listede olmayan parça takılabilir; arayüz bunu "listede yok" diye işaretler ama engellemez. Şablondan silinen yuvanın satırı listede kalır ("şablonda yok" görünür). Liste şimdilik bakım planı sarflarını ve satınalma ihtiyacını beslemiyor; ikisi de aynı tablodan okunacak şekilde sonraya bırakıldı.

## K-021 · Ürün ağacı: ürün başına tek ağaç, alt montaj ayrı tablo değil

**Karar:** Üretim BOM'u (`0020`) iki tablodur: `boms` (üretilen katalog kalemi başına bir ağaç) ve `bom_lines` (bileşen, 1 birim ürün için miktar). Ürün ve bileşen aynı katalogdadır (`parts`). Alt montaj ayrı bir kavram değildir: kendi ağacı olan bileşen alt montajdır. Malzeme maliyeti yapraklardan yukarı toplanır; yaprağın maliyeti stok ortalama maliyeti, yoksa liste fiyatıdır; ikisi de yoksa sıfır sayılır ve ekranda işaretlenir. Döngü API'de engellenir. Model parça listesi (`model_parts`, K-020) ayrı kalır: o sahadaki makinenin bakımına, bu üretime bakar.

**Neden:** Tek katalog, stok ve satınalmanın üretimle aynı kalemlerden konuşmasını sağlar (üretilebilirlik ve tedarik açığı bu ağaçtan hesaplanacak). Alt montajı ayrı tablo yapmak aynı bilgiyi iki yerde tutmak olurdu.

**Göze alınan:** Revizyon (A, B sürümleri), alternatif bileşen ve fire payı yok; ilk imalatçı pilotuyla gerekirse eklenir. Excel biçimi kendi tasarımımızdır, gerçek bir müşteri dosyasıyla denenmedi.

## K-022 · Üretim emri: işlemler rotadan kopyalanır, süre başla / durdur kaydından gelir

**Karar:** Rota (`0021`, `bom_operations`) ürün ağacına bağlı sıralı işlem listesidir; süre 1 birim ürün içindir ve boş bırakılabilir. Üretim emri açılırken işlemler emre kopyalanır (`production_order_ops`, plan = birim süre × miktar). Gerçekleşen süre elle girilmez: işlem başında Başla / Durdur ile açılıp kapanan zaman kayıtlarının (`production_time_logs`) toplamıdır. Bir kişinin aynı anda tek açık kaydı olur; aynı işlemde birden çok kişi çalışabilir. "Bitti" işlemde süren bütün kayıtları kapatır; süre tutulmadan da bitti işaretlenebilir. Emir bütün işlemler bitmeden tamamlanamaz; iptal süren kayıtları kapatır ve emir işlem raporuna girmez. Kurallar veritabanı fonksiyonlarındadır (`prod_op_start`, `prod_op_stop`, `prod_set_status`). Rota ve emir açma / iptal yönetici, başla / durdur / bitir ve tamamlama teknisyen yetkisidir.

**Neden:** Kopyalama, rota değişince açık emrin planının ve geçmiş raporun kaymasını önler. Sürenin kayıttan gelmesi, gün sonunda tahminle doldurulan formdan daha güvenilirdir ve kişi bazında ayrıntıyı bedavaya verir. Tek açık kayıt kuralı, unutulan sayaçların iki işe birden süre yazmasını engeller.

**Göze alınan:** Emir stokla konuşmuyor: malzeme tüketimi ve mamul girişi yok (üretilebilirlik, fire ve üretim maliyeti kalemleriyle gelecek). İş istasyonu / makine ataması, işlemler arası zorunlu sıra, vardiya ve mola yok; durdurmayı unutan kişinin süresi akmaya devam eder ve düzeltme ekranı yok. Alt montaj için emir kendiliğinden açılmaz. Rapor işlemleri ada göre toplar; aynı işlem farklı ürünlerde farklı yazıldıysa ayrı satır olur.

## K-023 · Üretilebilirlik: anlık hesap, seviye seviye netleştirme

**Karar:** Üretilebilirlik ve tedarik açığı saklanmaz; her soruda ürün ağacı (`boms`, `bom_lines`), stok (`v_stock_totals`) ve yoldaki siparişlerden (`v_purchase_on_order`) hesaplanır. İhtiyaç yukarıdan aşağı netleştirilir: her bileşende önce eldeki stok kullanılır; yetmeyen kısım bileşen alt montajsa onun bileşenlerine açılır, satın alınan kalemse eksik yazılır. Aynı kalem ağacın birkaç dalında geçiyorsa stok bir kez paylaşılır. "Kaç birim üretilir" eksik çıkmayan en büyük tam sayıdır. "Eksik" stoka göredir; "alınacak" eksikten verilmiş siparişlerin kalan miktarı düşülerek bulunur (talep aşamasındaki sipariş sayılmaz). Üretilecek ürünün kendi stoku hesaba katılmaz: soru "kaç tane daha yapabilirim"dir.

**Neden:** Saklanan bir plan tablosu, stok ve sipariş her değiştiğinde eskir ve yeniden üretilmesi gerekir; KOBİ ölçeğinde ağaçlar küçük olduğu için anlık hesap hem doğru hem yeterince hızlıdır. Alt montaj stokunu önce kullanmak, rafta hazır duran silindir varken bileşenlerini yeniden satın aldırmamak içindir.

**Göze alınan:** Zaman boyutu yok: termin, tedarik süresi ve "ne zaman sipariş vermeliyim" hesaplanmaz. Açık üretim emirlerinin ihtiyacı düşülmez (emir stokla konuşmuyor, K-022); iki ürün aynı stoku ayrı ayrı "üretilebilir" gösterebilir. Depo ayrımı yok, firma toplam stoku kullanılır. Talep açıldıktan sonra sipariş verilene kadar aynı eksik yeniden talep edilebilir; ekran bunu engellemez. Fire payı ve asgari sipariş miktarı yok.

## K-024 · Üretim emri stoku tamamlanırken işler; fire ve hurda emirde tutulur

**Karar:** Emir açılırken ürün ağacının birinci seviye bileşenleri emre kopyalanır (`production_order_materials`, plan = ağaçtaki miktar × emir miktarı); ağaç sonradan değişse de emrin planı değişmez. Stok tek noktada, emir tamamlanırken işlenir (`prod_complete`): seçilen depodan her malzemenin gerçekleşen kullanımı çıkar, sağlam ürün aynı depoya girer; hepsi tek işlemdir, bir kalemin stoku yetmiyorsa hiçbiri yazılmaz. Fire = kullanılan − planlanan malzeme (eksi değer tasarruf); hurda = üretilip kullanılamayan ürün. Plandan fazla malzeme ve hurda için sebep zorunludur; sebepler sabit bir listedir (malzeme hatası, işçilik hatası, makine / kalıp arızası, ayar / deneme üretimi, ölçü dışı, taşıma / depolama hasarı, diğer). Alt montaj bileşenlerine açılmaz: stokta hazır olmalı, kendi emriyle üretilir.

**Neden:** KOBİ atölyesinde malzeme çoğunlukla iş bitince sayılır; işlem başına ya da gün içinde tüketim girmek kimsenin yapmayacağı bir yüktür. Tek noktada işlemek stokla emrin birbirinden ayrışmasını da önler. Sabit sebep listesi raporu karşılaştırılabilir tutar; serbest metin dağılım vermez.

**Göze alınan:** Emir sürerken malzeme stokta görünmeye devam eder; açık emir malzeme ayırmaz (üretilebilirlik hesabı da bunu bilmez, K-023). Seri numarasıyla tek tek izlenen kalemlerde (silindir, pompa, lastik) stok hareketi yapılmaz, yalnızca plan / kullanılan kaydedilir; bu kalemlerin giriş-çıkışı elle yapılır. Mamul stoğa maliyetsiz girer; birim maliyet "üretim maliyeti" kalemiyle gelecek. Hurda ürünün kendisi stoğa girmez ve değeri raporda yoktur (yalnızca malzeme firesinin tutarı var). Kısmi tamamlama yok: emir bir kerede kapanır. Tamamlanmış emir geri alınamaz; düzeltme stok sayımıyla yapılır.

## K-025 · Üretim maliyeti emir tamamlanırken hesaplanır ve emre yazılır

**Karar:** Üretim maliyeti üç kalemdir ve emir tamamlanırken (`prod_complete`, `0023`) hesaplanıp emre yazılır. *Malzeme:* her malzemenin kullanılan miktarı × tüketim anındaki birim maliyeti (stok ortalama maliyeti; seri numaralı kalemde liste fiyatı). *İşçilik:* emrin zaman kayıtlarının toplamı × firmanın işçilik saat maliyeti (`thresholds.labor_cost_per_hour`, Ayarlar; varsayılan 0). *Makine:* işlemin zaman kayıtları × işlemin makine saat maliyeti; oran rotada işleme yazılır (`bom_operations.machine_rate`), emir açılırken emre kopyalanır, boşsa o işlemde makine maliyeti yoktur. Birim maliyet = toplam / sağlam ürün: hurdanın maliyeti sağlam ürüne biner. Sağlam ürün stoğa bu birim maliyetle girer; böylece alt montaj üst ürünün malzeme maliyetine kendi üretim maliyetiyle taşınır. Planlanan maliyet saklanmaz: planlanan miktar ve süre, tamamlanmış emirde gerçekleşenle aynı fiyat ve oranla çarpılır (fark yalnızca miktar ve süreden gelir); açık emirde bugünkü stok maliyeti ve oranla.

**Neden:** Emre yazmak, oran ya da stok maliyeti sonradan değişince kapanmış emrin ve geçmiş raporun kaymasını önler; TCO'da göze alınan "oran tarihçesi yok" sorunu (K-017) burada baştan yaşanmaz. Makine oranını ayrı bir iş istasyonu tablosu yerine rotadaki işleme yazmak, KOBİ atölyesinin zaten bildiği tek bilgiyi ister ("lazer saati şu kadar") ve yeni bir tanım ekranı açmaz. Süre zaten başla / durdur kaydından geldiği için (K-022) işçilik ve makine maliyeti ek veri girişi istemez.

**Göze alınan:** İşçilik tek firma oranıdır; kişiye ya da işleme göre ücret yok. Makine süresi kişi süresinden gelir: aynı işlemde iki kişi çalışırsa makine saati iki kez sayılır, süre tutulmadan "bitti" denen işlemin işçilik ve makine maliyeti sıfırdır. Genel gider (kira, enerji, amortisman) payı yok. Maliyeti bilinmeyen malzeme sıfır sayılır. Üretilen ürün seri numarasıyla izleniyorsa stok hareketi yapılmaz (K-024), birim maliyet yalnızca emirde ve raporda görünür. `0023`'ten önce tamamlanan emirlerin maliyeti hesaplanmaz; raporda yer almazlar.

## K-026 · Makine devri taşımadır, kopya değil; iki taraf kodla onaylar

**Karar:** Teslim edilen makinenin ikizi alıcı firmaya *taşınır* (`0024`): makine, üzerinde takılı parça ikizleri ve bunların olay defteri, ölçümleri, kontrolleri, fotoğrafları ve sayaç okumaları aynı satırlar olarak kalır, yalnızca `tenant_id` değişir. Devir iki adımdır: devreden (manager ve üstü) makine için tek kullanımlık kod üretir (`DV-` + 10 karakter, 30 gün geçerli, iptal edilebilir); alıcı (manager ve üstü) kodu sorgulayıp ne alacağını görür, filo kodunu ve sahayı seçip devralır. Firmalar birbirini göremediği için dört işlem de yetkiyi kendi denetleyen `SECURITY DEFINER` fonksiyonlardır; `asset_transfers` tablosuna API rolü yalnızca okuma yapar. Devredene özel katalog kalemi, parça tipi, makine modeli ve pozisyon şablonu alıcıda aranır (aynı üretici + parça no; aynı model adı ve takılı parçaların yuvalarını karşılayan şablon), yoksa kopyalanır; şablon ve model görseli de çoğaltılır. Maliyet geçmez: parça alış fiyatı, olay maliyeti, liste fiyatı ve makineye özel duruş oranı boşaltılır. Her parçaya `transferred` olayı yazılır. Açık iş emri ya da taslak kontrol varken devir başlatılamaz ve tamamlanamaz.

**Neden:** Fiziksel makine tektir; kopya, iki firmada ayrı ayrı yaşayan iki "ikiz" ve aynı QR etiketine iki kayıt demektir. Taşıma, parçanın geçmişini kesintisiz tek defterde tutar. Kod, devredenin alıcının firmasını bilmesini (ve firmaların birbirini aramasını) gerektirmez; alıcının açık onayı olmadan kimsenin filosuna makine düşmez, kodu bilmeyen de makineyi alamaz. Alış fiyatları üreticinin ticari sırrıdır; alıcı kendi maliyetini kendi girer.

**Göze alınan:** Devir geri alınamaz; yanlış firmaya gittiyse alıcı aynı yolla geri devreder, ama boşaltılan maliyetler geri gelmez. Devreden makineyi ve parçalarını artık göremez; elinde yalnızca devir kaydı (makine kodu, seri, model, parça sayısı, kime, ne zaman) kalır. Devredenin o makineye ait kapanmış iş emirleri, stok hareketleri ve satınalma satırları kendisinde kalır ama makineyi gösteremez (iş emri listesi ve TCO raporunda görünmez); makineye bağlı bakım planları pasifleşir. Yalnızca takılı parçalar geçer; stoktaki yedekler, model parça listesi ve bakım planları geçmez. Alıcıda maliyeti boşalan parçaların saat başı maliyeti sıfır görünür. Alıcıda aynı kalemden aynı seri numarası varsa devir durur. Katalog kalemi görseli kopyalanmaz. Alıcının SpareTwin hesabı olmalıdır; hesapsız müşteriye "salt okunur ikiz" yok.

## K-027 · eBOM ayrı tutulur; mBOM ondan firma kurallarıyla türetilir, dönüşüm saklanmaz

**Karar:** Mühendislik ağacı (eBOM: `eboms`, `ebom_lines`, `0025`) üretimin kullandığı ürün ağacından (mBOM: `boms`, `bom_lines`) ayrı tablolardadır. Firma `bom_rules` içinde beş tip kural tanımlar: *düzleştir* (alt montaj ayrı üretilmez, bileşenleri üst ürüne açılır), *çıkar* (kalem mBOM'a girmez), *değiştir* (A yerine B, oranla), *sarf ekle* (ürün başına ya da eşleşen her birim için) ve *fire payı* (miktar yüzdeyle artar). Eşleşme tek kalem, parça tipi ya da bütün kalemlerdir. Uygulama sırası sabittir ve yukarıdaki sıradır; kuralların tanımlanma sırası sonucu değiştirmez. Aynı kaleme birden çok fire kuralı uyuyorsa en özeli geçerlidir (tek kalem > parça tipi > tümü). Sarf ekleme, değiştirme sonrasındaki ağaca bakar: eklenen sarf başka bir sarfı tetiklemez, ama fire payı eklenen kaleme de uygulanır. Dönüşüm saklanmaz, her okumada hesaplanır (`sparetwin/ebom.py`); ürün ağacı yalnızca kullanıcı "Üretim ağacına yaz" deyince, o ürün için güncellenir: satırlar dönüşümün sonucuyla değiştirilir, rota ve açılmış emirler (malzemesi emre kopyalanmıştır, K-024) etkilenmez.

**Neden:** Emir, üretilebilirlik, fire ve maliyet zaten `boms` üzerine kurulu; eBOM'u ayrı tutmak bunların hiçbirine dokunmadan tasarım ile üretim arasındaki farkı görünür kılar. Sabit sıra, "kuralı hangi sıraya koymalıyım" sorusunu ve sıraya bağlı sürprizleri ortadan kaldırır. Dönüşümü saklamamak, eBOM ya da kural değişince eski bir kopyanın geçerli sanılmasını önler; yazmayı elle bırakmak ise bir kural değişikliğinin açık planları ve üretilebilirlik hesabını habersiz değiştirmesini engeller: kullanıcı önce farkı (yeni / değişecek / silinecek) görür.

**Göze alınan:** Kural seti ilk müşteriden önce varsayımla yazıldı; gerçek kullanımda değişebilir. Kurallar firma geneldir: ürüne, ürün grubuna ya da müşteriye özel kural yok; koşullu formül (ölçüye, ağırlığa göre miktar) yok. Fire payı adetle sayılan kalemde kesirli miktar verir (1 keçe → 1,1); yuvarlama emir miktarıyla çarpıldıktan sonra kullanıcıya kalır. Kural değişince ürün ağaçları kendiliğinden güncellenmez; listede "fark var" görünür ve ürün ürün yazılır. Ürün ağacına elle eklenen satır, eBOM'dan yeniden yazınca silinir (önizleme "silinecek" diye gösterir). eBOM'un revizyon geçmişi tutulmaz. Düzleştirme yalnızca kendi eBOM'u olan alt montajda çalışır.
