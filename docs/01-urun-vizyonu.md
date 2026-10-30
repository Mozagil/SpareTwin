# Ürün vizyonu

## Tek cümlede

SpareTwin, KOBİ ve orta ölçekli üretim, makine imalatı ve iş makinesi firmalarına, makinelerindeki her kritik parçanın dijital ikizini tutan, bu ikizlerden "neyi ne zaman değiştirmeli, neyi stokta tutmalı, gerçekte neye mal oluyor" sorularına cevap üreten bir SaaS platformudur.

## İki fikir nasıl birleşiyor?

Elimizde iki ayrı plan vardı:

**TireIQ** (Temmuz 2026 sunumu): İş makinesi ve OTR lastikleri için enTIRE Wheels benzeri, Türkiye'ye uygun fiyatlı lastik ve jant yönetimi. Odak: lastik yaşam döngüsü, QR ile saha inspeksiyonu, saat bazlı ömür takibi, ileride TPMS ve yapay zekâ ile ömür tahmini.

**KOBİ ERP** (Temmuz 2026 yol haritası): Makine imalatı KOBİ'leri için satınalma, stok, üretim, satış çekirdeği ve üstüne mühendislik zekâsı (CAD'den BOM, eBOM→mBOM, MRP, fire, hesaplama araçları).

İkisinin ortak paydası **parça**. TireIQ'da parça bir lastik; ERP'de parça bir BOM kalemi. Fark şu: TireIQ parçayı **sahada, makinenin üzerinde** izler; ERP parçayı **fabrikada, üretim ve stok akışında** izler. SpareTwin bu iki yarıyı tek bir parça modelinde birleştirir:

```
          Tedarik ──► Stok ──► Montaj ──► Sahada çalışma ──► Sökme ──► Tamir / Kaplama / Hurda
          (ERP)       (ERP)    (ikiz)      (ikiz: ölçüm,      (ikiz)    (ikiz + maliyet)
                                            inspeksiyon)
```

Böylece:

- TireIQ, çekirdeğin üzerinde **ilk dikey paket** olur. Lastiğe özgü her şey (diş derinliği, kaplama, jant uyumluluğu) bir modülde durur.
- Aynı mantık **her makinenin her yedek parçasına** uygulanır: hidrolik silindirde çökme ölçümü, pompada çalışma saati, akünün gerilimi. Yeni parça tipi eklemek kod değil, kütüphaneye bir kategori ve ölçüm profili eklemektir.
- ERP tarafı (stok, satınalma, BOM, iş emri) sonraki fazlarda bu parça modelinin **öncesine** (tedarik ve üretim) bağlanır.

## Hedef kitle

| Segment | Örnek | İlk ihtiyacı | Neden önemli |
|---|---|---|---|
| İş makinesi filoları | Madencilik, liman, inşaat, belediye | Lastik ve kritik parça takibi | Lastik maliyeti en görünür kalem, ROI hızlı |
| Makine kiralama firmaları | Forklift, platform, yükleyici kiralama | Parça geçmişi, kiralama dönüşü hasar tespiti | Makine başına maliyet doğrudan kârlılığı belirler |
| Üretim fabrikaları | Pres, CNC, konveyör hatları | Yedek parça stoğu ve bakım | Duruş maliyeti yüksek |
| Makine imalatçıları | Forklift ataşmanı, sac/kaynak imalatı | BOM, iş emri, üretim maliyeti | ERP fazlarıyla gelir |

İlk pilot hedefi TireIQ sunumundaki gibi **liman ve maden filoları**: lastik maliyeti yüksek, saha kontrollü, kazanç kolay gösterilir.

## Değer önerisi

| Konu | Bugün (KOBİ) | SpareTwin |
|---|---|---|
| Parça geçmişi | Kağıt form, dağınık Excel, ustabaşının hafızası | Her parçanın tek kayıtta tüm yaşamı |
| Değişim kararı | Göz kararı, ya erken ya geç | Ölçülen aşınma hızından kalan saat tahmini |
| Maliyet | "Lastiğe yılda ne harcıyoruz" bile belirsiz | Parça, makine ve saat başına gerçek maliyet |
| Saha verisi | Fotoğrafsız, doğrulanmamış | QR ile kimlik, zorunlu fotoğraf, 4 kalite kapısı |
| Stok | Kritik parça ihtiyaç anında yok | Yaklaşan değişimlere göre stok uyarısı |
| Fiyat | Kurumsal çözümler pahalı ve uzun sözleşmeli | Aylık abonelik, modül bazlı |

## enTIRE'dan öğrendiklerimiz

enTIRE Wheels'i referans alırken kopyalanacak özellikten çok, **güven veren ilkeler** önemli:

1. **Bağımsızlık.** enTIRE, hiçbir lastik üreticisine veya servis sağlayıcıya bağlı olmamasını en öne koyuyor. SpareTwin de marka bağımsız olmalı; bir üreticinin lastiğini satmak için değil, müşterinin maliyetini düşürmek için var.
2. **Veri müşterinindir.** enTIRE verinin müşterinin kontrolünde, kendi sunucusunda kalmasını vurguluyor. Bizim karşılığımız: her an tam dışa aktarma, AB bölgesinde barındırma ve Faz 3 sonrasında aynı paketin müşterinin kendi sunucusuna kurulabilmesi (backend'i bu yüzden baştan kendimiz, Docker ile kurduk).
3. **Jant uyumluluğu ayrı bir konu.** Çok parçalı OTR jantların muayene periyodu güvenlik meselesi. Bu yüzden jant, lastikten ayrı izlenir ve NDT periyodu takip edilir (`v_rim_compliance`).
4. **Veri girişi hizmeti.** enTIRE'ın "Bureau" adıyla sunduğu veri girişi hizmeti, KOBİ'de en büyük engeli (veri girmeye vakit yok) çözer. Bizde pilot dönemde ilk envanter girişini ekip olarak yapmak, sonra ücretli hizmet olarak sunmak mantıklı.
5. **Kaplama (retread) takibi.** Kaplanabilir karkasın ikinci ömrü ciddi tasarruf. Parça ikizinde `refurbishing` durumu ve `refurbished` olayı bunun için var.

## Konumlandırma cümlesi

> "Ağır ekipmanınızın lastiklerini ve kritik parçalarını, marka bağımsız ve verisi size ait bir platformda izleyin. Neyi ne zaman değiştireceğinizi tahminle değil ölçümle bilin."

Genel filo yönetimi yazılımı değiliz (araç takip, yakıt, sürücü). Parça odaklıyız; derinliğimiz burada.

## Kapsam dışı (bilinçli olarak)

- Muhasebe, e-fatura, bordro, SGK. Gerekirse Logo/Mikro/Netsis ile entegrasyon, yerine geçmek değil.
- GPS araç takibi ve sürücü yönetimi.
- 3D CAD dosyası saklamak. ERP fazında bile yalnızca BOM metadata'sı alınır (KOBİ ERP planındaki "3D dosya hiç yüklenmez" ilkesi aynen geçerli).
- Tam mühendislik analizi (FEA). Hesaplama araçları "ön kontrol" olarak konumlanır.
