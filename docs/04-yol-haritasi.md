# Yol haritası

## Sıralama mantığı

1. **Önce dar ve derin.** TireIQ tek bir parça tipiyle başlar ama genel ikiz motorunun üzerine kurulur. Satış kolay (lastik maliyeti herkesin derdi), geliştirme odaklı kalır.
2. **Sonra genişle.** Aynı motor, kod değişmeden her yedek parçaya açılır; stok, satınalma ve bakım eklenir. Bu noktada ürün "lastik programı" olmaktan çıkıp "parça yönetim platformu" olur.
3. **En son üretim.** KOBİ ERP'nin üretim ve mühendislik tarafı (BOM, iş emri, MRP) en büyük ve en firmaya özel iş. Ancak çekirdek oturduktan ve ilk gelir geldikten sonra başlanır.
4. **Mobil ve yapay zekâ veriye bağlı.** Native uygulama ve ömür tahmini modeli, sahada gerçek kullanım ve yeterli ölçüm biriktikten sonra anlam kazanır.

```mermaid
gantt
  dateFormat  YYYY-MM
  axisFormat  %b %y
  section Çekirdek
  Faz 0 · Temel ve ikiz motoru        :f0, 2026-11, 2M
  section TireIQ
  Faz 1 · TireIQ MVP ve pilot         :f1, after f0, 3M
  section Genişleme
  Faz 2 · Yedek parça, stok, bakım    :f2, after f1, 4M
  Faz 3 · SaaS ürünleşme              :f3, after f1, 4M
  section ERP
  Faz 4 · Üretim ve mühendislik       :f4, after f2, 6M
  section Akıllı katman
  Faz 5 · Sensör, AI, native mobil    :f5, after f3, 6M
```

Süreler 1–2 kişilik bir geliştirme ekibi için kaba tahmindir; her faz pilot geri bildirimine göre netleşir. Faz 2 ve Faz 3 paralel yürüyebilir.

---

## Faz 0 · Temel ve ikiz motoru

**Hedef:** Bir makineyi ve parçalarını sisteme girip, QR okutunca parçanın tüm geçmişini görmek.

| Kapsam | Durum |
|---|---|
| Çok kiracılı şema, roller, RLS | ✅ Hazır (`db/migrations/0001`, `0002`) |
| Parça ikizi iş kuralları: takma, sökme, sayaç, olay defteri, kalite kapıları | ✅ Hazır (`0003`) |
| TireIQ uzantıları ve ortak kütüphane (3 makine şablonu, 6 kategori) | ✅ Hazır (`0004`, düzeltme `0007`) |
| Kendi kimlik sistemimiz: argon2 parola, JWT, dönen yenileme token'ı | ✅ Hazır (`0005`) |
| FastAPI: filo, makine, parça, yaşam döngüsü, inspeksiyon, fotoğraf, QR | ✅ Hazır |
| Kayıt: saha, makine modeli, katalog (lastik/jant bilgisiyle), makine, parça teslim alma | ✅ Hazır (`0006`) |
| QR kodu otomatik atama ve A4 etiket yazdırma sayfası | ✅ Hazır (API tarafı) |
| 43 otomatik test | ✅ Hazır |
| Codespace ortamı (Python 3.12 + PostgreSQL), GitHub | ✅ Hazır |
| Dashboard görsel prototipi | ✅ Hazır (`prototype/`) |
| React frontend: giriş, oturum yenileme, firma seçimi, rol bazlı menü | ✅ Hazır (`frontend/`) |
| Filo dashboard'u: filo şeridi, makine şeması, parça ikizi, aşınma grafiği, öncelikli işler, maliyet | ✅ Hazır |
| Makine ve parça sayfaları: takma, sökme, motor saati, olay kaydı | ✅ Hazır |
| Kayıt formları, parça listesi, QR etiket yazdırma, QR/seri no arama | ✅ Hazır |
| Frontend testleri (8) ve 10 adımlık uçtan uca tarayıcı senaryosu | ✅ Hazır |
| Senin Codespace'inde doğrulama (`make dev`) | ⏳ Sırada |

**Sonraya ertelendi (sunucu ve alan adı işleriyle birlikte):** geliştirme/canlı sunucu, alan adı, hata izleme ve uptime kontrolü. Faz 0 boyunca her şey Codespace'te çalışır.

**Bitiş kriteri:** Arayüzden yeni bir makine ve lastikleri girilip QR etiketleri yazdırılabiliyor; demo filo dashboard'da görünüyor; bir lastik sökülüp yenisi takıldığında dashboard anında doğru sonucu gösteriyor.

**Kapsam dışı:** Mobil form, rapor, faturalama.

---

## Faz 1 · TireIQ MVP ve pilot

**Hedef:** İlk pilot filo (liman veya maden) lastiklerini ve jantlarını gerçek sahada SpareTwin ile izliyor.

| Kapsam | Not |
|---|---|
| ✅ **Görseller** | Katalog kalemi, makine modeli ve makine görseli; parça ikizinde saha fotoğrafları ve büyütme penceresi. Yüklenen her görselde yön düzeltme, 1600 px'e küçültme ve GPS/meta veri silme |
| ✅ **Mobil kontrol formu** (`/kontrol`) | Kamerayla QR okutma (Android ve iPhone), motor saati, pozisyon kartları, önceki ölçüm ipucu ve anlık aralık uyarısı, zorunlu fotoğraf yuvaları, "kaydet, sonraki", yarım kalan kontrole devam, 4 kalite kapısı, iptal |
| ✅ Fotoğraf yükleme, sıkıştırma, zorunlu açılar | Telefonda 1600 px'e küçültülür, sunucuda GPS silinir |
| ✅ Ölçümler yalnızca tamamlanan kontrolden sayılır | Taslak veya iptal edilmiş kontroldeki değer dashboard'u etkilemez (`0009`) |
| ✅ Lastik ve jant yaşam döngüsü ekranları | Takma (lastik jantıyla birlikte, tek işlem), sökme (stoğa / tamire / kaplamaya / hurdaya), tek adımda rotasyon (doluysa yer değiştirir, saatler korunur), tamir, kaplamadan dönüş, NDT kaydı |
| ✅ **Jant uyumluluğu** (`/jantlar`) | Her lastik pozisyonunun jant pozisyonu (`A1-L-J`), gecikmiş / yaklaşan / güncel listesi, tek tıkla "muayene yapıldı" kaydı (`0010`) |
| ✅ Doğrusal aşınma ve kalan saat tahmini | `v_tire_health`; parça ikizinde grafik |
| ✅ Saat başı maliyet | Bugüne kadar (parça ikizi) ve ömür sonu beklenen (dashboard, rapor) |
| ✅ **Toplu içe aktarma (Excel/CSV)** | Şablon indirme, esnek sütun başlıkları, Türkçe sayı/tarih, önizleme (satır satır hata ve uyarı), ya hepsi ya hiçbiri, yeni makine ve katalog kalemi oluşturma, yeni lastiklerin etiketlerini yazdırma |
| ✅ **PDF durum raporu** | Tüm filo veya tek makine: yönetici özeti, makineler, öncelikli işler, saat başı maliyet, jant muayenesi, stok uyarıları, tamamlanmış kontrollerin saha fotoğrafları. Türkçe karakterler için Barlow gömülü |
| ✅ **Uygulama içi bildirimler** | Üst çubukta zil: kritik parça, jant muayenesi, düşük stok, 30 gündür kontrol edilmeyen makine. Kişiye özel okundu bilgisi; durum değişince yeniden okunmamış olur. E-posta, sunucu aşamasında aynı listeye bağlanacak |
| ✅ Sökme sebep kodları ve sebep raporu | Sabit liste: aşınma, kesik, darbe, ayrışma, basınç kaybı, sızıntı, rotasyon, diğer; API listede olmayan sebebi kabul etmez. Firmaya özel sebep bilerek yok (K-019). Rapor Parçalar › Sökme sebepleri'nde (`GET /reports/removal-reasons`): sebep bazında adet, pay ve sökme anındaki ortalama çalışma saati; katalog kalemine ve makineye göre dağılım; dönem ve parça tipi süzgeci. Rotasyon ayrı sayılır |

| ✅ Excel'de jant sütunları | Jant seri no, ebat, NDT periyodu; stoktaki jant takılır, yoksa oluşturulur |
| ✅ "Jant kaydı yok" bildirimi | Lastiği takılı ama jantı kaydedilmemiş pozisyonlar: muayene takibi yapılamadığı uyarısı |
| ✅ **Firma eşikleri** (`/ayarlar`, v1.2) | Kritik ve izleme yüzdesi, jant "yaklaşıyor" yüzdesi, kontrol aralığı (gün) firma başına ayarlanır; dashboard, bildirim ve rapor aynı eşiği kullanır (`0013`). Eski TireIQ taslağından devralındı (K-014) |
| ✅ **Bildirimde ekip durumu** (v1.2) | "Üstlen" (biri ilgileniyor, kim/ne zaman) ve "gizle" (durum değişene kadar). Durum kötüleşince kayıt kendiliğinden düşer, sorun geçince kapanır |

**Faz 1 yazılımı tamamlandı (v1.0).** Kalan tek kalem sökme sebeplerinin firmaya özel düzenlenmesi; Faz 3'teki ayarlar ekranına taşındı.

**Pilot için gerekenler (yazılım dışı ve sunucu):** Sunucu ve alan adı, gerçek kullanıcı hesapları ve parola sıfırlama, e-posta bildirimleri, yedekleme. Bunlar Faz 3'teki "SaaS ürünleşme" maddeleriyle örtüşüyor; pilot öncesinde asgari kısmı öne çekilecek.

**Pilot programı:** 2–3 firma, ücretsiz veya indirimli. İlk envanter girişini biz yapıyoruz (enTIRE "Bureau" modeli). Karşılığında aylık geri bildirim görüşmesi ve referans izni.

**Bitiş kriteri:** En az 1 filoda 100+ tamamlanmış inspeksiyon, saha ekibi formu yardımsız kullanıyor, yönetici aylık raporu kendisi açıyor.

---

## Faz 2 · Her makine için yedek parça: stok, satınalma, bakım

**Hedef:** Lastik dışındaki kritik parçalar da ikizle izleniyor; "ne zaman değişecek" sorusu "stokta var mı, ne zaman sipariş vermeliyim" sorusuna bağlanıyor.

| Kapsam | Not |
|---|---|
| ✅ **Parça tipi ve ölçüm profili yönetimi** (Kayıt › Parça tipleri) | Firma kendi parça tipini tanımlar (şanzıman, zincir, palet…): seri numaralı ya da miktarla; sahada ölçülecek değerler (ad, birim, alt/üst sınır, zorunlu) ve zorunlu fotoğraflar. Kontrol formu, katalog ve süzgeçler yeni tipi kendiliğinden tanır. Ortak tipler salt okunur; kod ve izleme şekli kayıttan sonra değişmez; kullanılan tip silinemez (`api/library.py`) |
| ✅ **Pozisyon şablonu düzenleyici** (Kayıt › Pozisyon şablonları) | Firma kendi makine tipini çizer: yuvalar şemada sürüklenir ya da ok tuşlarıyla taşınır, ortak şablon kopyalanıp uyarlanır, lastiklere tek tıkla jant yuvası eklenir. Üzerinde parça takılı yuva silinemez, tipi değiştirilemez; modele bağlı şablon silinemez. **Makine resmi:** hazır gövde çizimi uymuyorsa şablona makinenin üstten fotoğrafı ya da teknik çizimi yüklenir (`0018`); yuvalar resmin üzerine yerleştirilir, makine şeması da o resimle çizilir. **Model şablonu değiştirme** (Kayıt › Makine modeli › Kayıtlı modeller): takılı her parçanın yuvası yeni şablonda aynı kod ve tiple varsa geçilir, yoksa hangi yuvaların engellediği söylenir |
| ✅ **Model parça listesi (BOM)** (Kayıt › Makine modeli › Parça listesi) | Modelde izlenen kritik kalemler (`0019`, `model_parts`): hangi yuvaya hangi katalog kalemi uyar (bir yuvaya birden çok alternatif), makine başına hangi sarf / yedek kullanılır. Elle ya da Excel'den (şablon indirilir; parça no ile eşleşir; hata varsa hiçbir satır yazılmaz, hatalar satır numarasıyla döner). Parça takarken stokta yalnızca listeye uyanlar gösterilir (isteyen diğerlerini açar); boş yuvada neyin takılacağı ve stokta olup olmadığı makine sayfasında görünür. Kurallar K-020. ⏳ Bakım planı sarflarını ve satınalma ihtiyacını listeden besleme |
| ✅ **Depo ve stok hareketleri** (`/stok`) | Sarf malzemeleri (filtre, yağ, keçe) adet/litre/takım ile: giriş, makineye çıkış, sayım düzeltmesi, depolar arası transfer. Seviye hareketlerden hesaplanır, defter değiştirilemez, eksi stok yok, ağırlıklı ortalama maliyet. Seri numaralı stok aynı ekranda (`0012`) |
| ✅ **Kritik stok uyarısı ve yaklaşan değişime göre ihtiyaç** | Kritik seviye uyarısı (bildirim, dashboard, rapor) sarf dahil. "LD-07 için 2 lastik yaklaşıyor, stokta 1 var" önerisi `v_purchase_needs` ile: kritik ya da firmanın *değişim ufku* (varsayılan 500 saat) içinde ömrü biten takılı parçalar + kritik seviye − stok − siparişte. Bildirimde, dashboard'un öncelikli işlerinde ve Satınalma › İhtiyaç'ta; tek tıkla talebe dönüşür |
| ✅ **Tedarikçi, satınalma talebi, sipariş, teslim alma** (`/satinalma`) | KOBİ ERP planındaki satınalma modülünün sade hali (`0014`): talep (teknisyen) → sipariş (yönetici, tedarikçi şart) → kısmi / tam teslim (teknisyen); iptal yalnızca teslimat başlamadan. Teslim alma stokla aynı kapıdan geçer: sarf kalemi `stock_move('in')` ile sipariş no + irsaliye referansıyla, seri numaralı parça `part_items` + `received` olayıyla. Geciken sipariş bildirimi |
| ✅ **Tedarikçi karşılaştırma** (Satınalma › Karşılaştırma) | Ek veri girişi yok: verilmiş siparişler ve teslim alma kayıtlarından (`GET /purchasing/supplier-comparison`). Kalem bazında hangi tedarikçiden kaç kez, ne kadar, ortalama ve son fiyat, ortalama teslim süresi, zamanında teslim oranı, eksik teslim; alım dağılımı çubuğu; "En ucuz / En hızlı" işareti ve tek cümlelik sonuç. Tedarikçi özeti ve harcama dağılımı; dönem 3 / 6 / 12 / 24 ay. Sipariş açarken kalemin altında son 12 ayın tedarikçi fiyat ve teslim özeti. Kurallar K-018. ⏳ Fiyat teklifi toplama (tedarikçinin link üzerinden kendi teklifini girmesi; e-posta altyapısı ister, Faz 3) |
| ✅ **Bakım planları** (`/bakim`) | Saat ve/veya takvim periyodu (`0015`); tek makine ya da modelin tüm makineleri; kontrol listesi ve her bakımda kullanılan sarf. Sıradaki bakım `v_maintenance_due` ile: son tamamlanan emir + periyot (hiç yapılmadıysa sıradaki periyot katı); firmanın *yaklaşıyor* eşiği (50 saat / 7 gün). Bildirimde, dashboard'un öncelikli işlerinde, makine sayfasında; tek tıkla iş emrine dönüşür |
| ✅ **Arıza ve duruş kaydı** | İş emri `kind = breakdown`: sebep (hidrolik, elektrik, …), ilgili parça, duruş başlangıcı → çalışmaya dönüş = duruş süresi. Açık arıza emri makineyi *down*, süren planlı emir *maintenance* yapar; emir kapanınca makine kendiliğinden *active* (K-016). Arızalı makine bildirimi |
| ✅ **Makine toplam sahip olma maliyeti** (Bakım › Maliyet) | `asset_tco()` ile (`0016`) makine başına seçilen dönemde (3 / 6 / 12 / 24 ay) parça + sarf + işçilik + dış servis + duruş; çalışma saatinden saat başı maliyet; saha süzgeci, filo toplamı ve kalem dağılımı. Duruş maliyeti = duruş süresi × *duruş saat maliyeti*: firma oranı (Ayarlar) ya da makineye özel oran (`0017`, rapordaki orana tıklanarak; yönetici). Aynı süzgeçle PDF ve Excel çıktısı (`/reports/tco.pdf`, `/reports/tco.xlsx`). Kurallar K-017. Bakım › Takvim'deki özet (`v_asset_maintenance`) yerinde |

**Bitiş kriteri:** Pilot firmalardan biri en az bir lastik dışı parça grubunu (hidrolik, akü veya zincir) aktif izliyor ve stok uyarısıyla en az bir sipariş açılmış.

---

## Faz 3 · SaaS ürünleşme

**Hedef:** Bir firma satış ekibiyle konuşmadan kaydolup, ödeme yapıp kullanmaya başlayabiliyor.

| Kapsam | Not |
|---|---|
| Kendi kendine kayıt ve firma oluşturma | Davet ile ekip ekleme |
| Abonelik ve ödeme | Türkiye için iyzico veya PayTR, yurt dışı için Stripe değerlendirilecek |
| Plan limitleri | TireIQ sunumundaki Starter / Pro / Enterprise yapısı, parça sayısı limiti |
| Onboarding sihirbazı | İlk saha, ilk makine, ilk QR etiketi |
| Raporlar ve dışa aktarma | Tüm veri CSV/JSON, zamanlanmış e-posta raporu |
| 🟡 Denetim kaydı ve rol ayrıntıları | ✅ Denetim kaydı v1.2'de öne çekildi: durum değiştiren her istek kim/ne/ne zaman olarak yazılır, yönetici `/ayarlar`'da görür (`0013`). ⏳ Rol ayrıntıları (özel yetkiler) |
| KVKK metinleri, kullanım koşulları, veri işleme sözleşmesi | Hukuki kontrol gerekli |
| PWA | Ana ekrana ekleme, zayıf internette çalışma (çevrimdışı kuyruk) |
| Giriş güvenliği | Deneme sınırı, e-posta ile parola sıfırlama, davet akışı |
| **Müşteri sunucusu kurulum paketi** | Frontend derlemesi aynı sunucuda, iç ağ HTTPS, imzalı lisans dosyası, tek komutla güncelleme, tanılama paketi |
| Çoklu dil | Türkçe + İngilizce (ihracat pazarı) |

**Bitiş kriteri:** İlk 5 ödeme yapan müşteri (TireIQ sunumundaki hedef) ve en az bir müşteri sunucusuna deneme kurulumu.

---

## Faz 4 · Üretim ve mühendislik (KOBİ ERP)

**Hedef:** Makine imalatı yapan KOBİ, ürettiği makinenin BOM'unu, iş emirlerini ve gerçek maliyetini SpareTwin'de yönetiyor.

KOBİ ERP yol haritasındaki Faz 1–3 burada, parça kataloğunu ortak kullanarak gelir:

| Kapsam | Not |
|---|---|
| ✅ **Ürün ağacı** (`/uretim`) ve Excel içe aktarma | `0020`, `boms` + `bom_lines`. Ürün de bileşen de aynı katalog kalemidir; kendi ağacı olan bileşen alt montajdır (çok seviye). Ağaç açılır / kapanır; 1 ürün için toplam miktar, stok ve malzeme maliyeti (yapraklardan yukarı; stok ortalama maliyeti, yoksa liste fiyatı) görünür. Elle ya da Excel'den (Ürün parça no, Bileşen parça no, Miktar, Not; alt montajlar aynı dosyada; hata varsa hiçbir satır yazılmaz). Döngü engellenir. 3D dosya yok, yalnızca metadata. Kurallar K-021 |
| eBOM → mBOM kural motoru | Firmaya özel kurallar; ilk müşteriyle birlikte tasarlanır |
| ✅ **Rota, üretim emri, işlem süresi** (Üretim › Üretim emirleri, İşlem raporu) | `0021`. Rota: ürün ağacının sıralı işlemleri ve 1 birim için planlanan süre (Üretim › Ürün ağaçları, ağacın altında). Üretim emri (`UE-2026-0001`): ürün, miktar, termin; işlemler rotadan emre kopyalanır (plan = birim süre × miktar), rota sonradan değişse de emir değişmez. İşlem başında Başla / Durdur / Bitti: süre kişi bazında tutulur, bir kişi aynı anda tek işlemde çalışır, aynı işlemde birden çok kişi çalışabilir; telefonda işlem satırı kart olur. Emir bütün işlemler bitince tamamlanır; iptal süren kayıtları kapatır. İşlem raporu: biten işlemlerde planlanan / gerçekleşen süre ve sapma, dönem 3 / 6 / 12 / 24 ay (`GET /production/reports/operations`). Kurallar K-022. ⏳ Emir stokla konuşmuyor: malzeme tüketimi ve mamul girişi sonraki kalemlerle (üretilebilirlik, fire, maliyet) gelir |
| ✅ **Üretilebilirlik ve tedarik açığı** (Üretim › Ürün ağaçları, ağacın altında) | Yeni tablo yok; ürün ağacı, stok ve yoldaki siparişlerden hesaplanır (`GET /production/boms/{id}/buildable?qty=`). Eldeki stokla kaç birim üretilir (listede de görünür); istenen miktar için kalem bazında gerekli, stokta, eksik, siparişte, alınacak. Stokta hazır alt montaj önce kullanılır, kalanı bileşenlerine açılır; aynı kalem birkaç dalda geçiyorsa stok bir kez paylaşılır. Eksikler tek tıkla satınalma talebine dönüşür. Kurallar K-023. ⏳ Açık üretim emirlerinin ayırdığı malzeme düşülmüyor (emir henüz stokla konuşmuyor); tarih / termin bazlı planlama yok |
| ✅ **Fire / hurda takibi** (Üretim › Üretim emirleri › emir; Üretim › Raporlar) | Migrasyon 0022. Emir artık stokla konuşur: emir açılırken ürün ağacının birinci seviye bileşenleri emre kopyalanır (plan = ağaçtaki miktar × emir miktarı); emir tamamlanırken depo, sağlam / hurda ürün ve malzeme başına kullanılan miktar girilir (`POST /production/orders/{id}/finish`). Kullanılan malzeme stoktan düşer, sağlam ürün stoğa girer; stok yetmiyorsa emir tamamlanmaz. Plandan fazla malzeme (fire) ve hurda ürün için sebep zorunlu (7 sabit sebep). Rapor: ürün bazında hurda oranı, malzeme bazında plan / kullanılan / fire tutarı, sebep dağılımı (`GET /production/reports/scrap`). Kurallar K-024. ⏳ Seri numarasıyla izlenen kalemlerde (silindir, pompa…) stok hareketi yapılmaz; açık emir malzeme ayırmaz; sebep listesi firmaya göre düzenlenemez |
| ✅ **Üretim maliyeti** (Üretim › Üretim emirleri › emir; Üretim › Raporlar) | Migrasyon 0023. Malzeme + işçilik + makine saati; emir tamamlanırken hesaplanır ve emre yazılır (`prod_complete`). Malzeme: kullanılan miktar × tüketim anındaki birim maliyet. İşçilik: tutulan süre × firmanın *işçilik saat maliyeti* (Ayarlar). Makine: işlemin süresi × işlemin makine saat maliyeti (rotada işleme yazılır, emre kopyalanır; boşsa makine maliyeti yok). Birim maliyet = toplam / sağlam ürün; sağlam ürün stoğa bu maliyetle girer. Emirde plan / gerçekleşen / fark dökümü (açık emirde yalnızca plan); rapor: ürün bazında malzeme, işçilik, makine, toplam ve birim maliyet, dönem 3 / 6 / 12 / 24 ay (`GET /production/reports/cost`). Kurallar K-025. ⏳ Genel gider payı yok; kişiye göre ücret yok (tek firma oranı); makine süresi kişi süresinden gelir; 0023'ten önce tamamlanan emirlerin maliyeti yok |
| ✅ **Teslim edilen makinenin ikizini müşteriye devretme** (Makine sayfası › Müşteriye devret; Kayıt › Makine devral) | Migrasyon 0024. Devreden firma makine için tek kullanımlık devir kodu üretir (`DV-…`, 30 gün geçerli, devralınana kadar iptal edilebilir); alıcı firma kodu kendi hesabında sorgular, makineyi, devredeni ve takılı parçaları görür, filo kodunu ve sahayı seçip devralır. Makine, takılı parça ikizleri ve geçmişleri (olay defteri, ölçümler, kontroller, fotoğraflar, sayaç) alıcıya taşınır; kopya çıkmaz, QR etiketleri aynı kalır, her parçaya "Aktarıldı" olayı yazılır. Devredene özel katalog kalemi, parça tipi, model ve pozisyon şablonu (resmiyle) alıcıda yoksa kopyalanır. Maliyet geçmez (alış fiyatı, olay maliyeti, liste fiyatı). İki tarafta devir geçmişi (`GET /transfers`). Kurallar K-026. ⏳ Takılı olmayan (stoktaki) parçalar, model parça listesi, bakım planları ve iş emirleri geçmez; katalog kalemi görseli kopyalanmaz; devir geri alınamaz (alıcı geri devredebilir); alıcının SpareTwin hesabı olmalı |
| Mühendislik hesap araçları | Büküm payı, hidrolik silindir kuvveti/debisi; "ön kontrol" uyarısıyla |

**Ön koşul:** En az bir makine imalatçısı pilot ve örnek BOM seti.

---

## Faz 5 · Akıllı katman ve mobil

| Kapsam | Ön koşul |
|---|---|
| TPMS entegrasyonu (basınç, sıcaklık) | Açık API'li sensör üreticisiyle başla; ölçüm tablosu bölümlenir |
| Telematik ile otomatik motor saati | Makine üreticisi API'leri veya CAN-bus ağ geçidi |
| Yapay zekâ ile ömür tahmini | 1.000+ tamamlanmış lastik ömrü verisi; TireIQ sunumundaki model merdiveni |
| Native mobil uygulama | PWA'nın yetmediği net bir ihtiyaç (RFID okuma, tam çevrimdışı) |
| SolidWorks eklentisi | Faz 4'te CSV akışı oturmuş olmalı |
| Tedarikçi portalı | Lastik bayisi/servisin doğrudan kayıt girmesi (enTIRE SupplierNet benzeri) |

---

## Riskler

| Risk | Olasılık | Önlem |
|---|---|---|
| Saha ekibi veri girmiyor | Yüksek | Formda en az alan, QR ile 3 saniyede kimlik, ilk girişi biz yapıyoruz, yöneticiye "kim girmedi" değil "hangi makine eksik" raporu |
| Ekran değişiklikleri kod gerektirir (görsel editör yok) | Orta | Bileşenler küçük ve tek tasarım diliyle; kurallar veritabanında olduğu için arayüz ince kalır |
| Kendi backend'imizin işletme yükü (güncelleme, yedek, güvenlik yaması) | Orta | Docker ile tekrarlanabilir kurulum, otomatik yedek, testli migrasyonlar; Faz 1'de izleme |
| Çok sayıda müşteri sunucusunu güncel tutmak | Orta (Faz 3+) | Sürümlü imajlar, açılışta otomatik migrasyon, tek komutla güncelleme |
| Kapsam şişmesi (her şey ERP olsun) | Yüksek | Faz bitiş kriterleri net; Faz 4 ancak Faz 3 kriteri tutunca başlar |
| Rakip kurumsal çözümler | Orta | KOBİ fiyatı, Türkçe destek, marka bağımsızlık, hızlı kurulum |
| Az veriyle yanlış tahmin güveni | Orta | Doğrusal model + "yetersiz veri" uyarısı, tahmin aralığı gösterimi |
| Tek kişiye bağımlı geliştirme | Orta | Her şey bu repoda, testli, dokümanlı |
