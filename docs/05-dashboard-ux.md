# Dashboard ve kullanıcı deneyimi

Uygulama: `frontend/` (Codespace'te `make dev`, 5173 portu). İlk tasarım taslağı `prototype/index.html` olarak duruyor; React uygulaması bu taslağın görsel dilini birebir kullanır.

## İlkeler

**Makineyi göster, tabloyu değil.** Kullanıcı bir yükleyicinin arka sol lastiğini düşünür, bir tablonun 14. satırını değil. Ana ekranın merkezinde makinenin üstten görünüş şeması var; parçalar gerçek konumlarında, durum renkleriyle. Lastiğin içindeki dolgu kalan diş yüzdesini gösterir; ilk bakışta okunur.

**Her ekran bir soruya cevap verir.**

| Ekran | Soru |
|---|---|
| Filo şeridi | Hangi makinede sorun var? |
| Makine şeması | Bu makinenin hangi parçası? |
| Parça ikizi | Bu parçanın hikâyesi ne, ne kadar ömrü kaldı? |
| Öncelikli işler | Bugün ne yapmalıyım? |
| Saat başı maliyet | Hangi makine bize pahalıya patlıyor? |

**Sayı değil karar.** "Diş 14 mm" yerine "bu hızla yaklaşık 539 saat kaldı". "Ömür %95" yerine "Bakım emri aç" düğmesi. Her uyarı bir eyleme bağlanır.

**Excel görünümü yok.** Tablo yalnızca gerçekten liste gereken yerde (stok, parça arama sonuçları) ve orada da satır yüksekliği rahat, kolon sayısı az, durum rengi solda ince bir şerit.

**Saha önce.** İnspeksiyon formu telefonda tek elle, eldivenle kullanılabilir: büyük dokunma alanları, tek ekranda tek pozisyon, sayısal klavye, kamera doğrudan açılır.

## Görsel dil

| Jeton | Açık | Koyu | Kullanım |
|---|---|---|---|
| `bg` | #E4E8EA | #10151A | Sayfa zemini (beton grisi) |
| `surface` | #F7F8F8 | #172028 | Paneller |
| `ink` | #17202A | #E3E8EC | Metin |
| `muted` | #55616D | #95A2AD | İkincil metin |
| `brand` | #0F5B66 | #4DB1BD | Ana eylem, seçili durum (petrol) |
| `ok` | #2C8A55 | #4CB97A | %40 üzeri |
| `watch` | #C08600 | #E2A82A | %20–40 |
| `critical` | #C23F2B | #E5654F | %20 altı |
| `rubber` | #2B3138 | #0B0F13 | Lastik çizimi |

Yazı tipi: **Barlow** (gövde) ve **Barlow Condensed** (başlık ve sayılar). Endüstriyel tabela harflerinden türemiş, dar alanda okunaklı, Türkçe karakterleri tam.

Durum renkleri her zaman metinle birlikte kullanılır (renk körlüğü): "Kritik", "%13", "2 kritik parça".

## Ekran listesi (frontend sayfaları)

| Sayfa | Yol | Faz | Durum | API |
|---|---|---|---|---|
| Giriş, firma seçimi | (oturum yoksa) | 0 | ✅ | `POST /auth/login`, `/auth/refresh` |
| Filo durumu | `/` | 0 | ✅ | `GET /assets`, `/assets/{id}`, `/parts`, `/reports/tire-cost` |
| Makine | `/makine/:id` | 0 | ✅ | `GET /assets/{id}`; tak, sök, saat gir |
| Parça ikizi | `/parca/:id` | 0 | ✅ | `GET /parts/{id}`, `/events`, `/wear`; sök, kayıt ekle |
| Parçalar | `/parcalar` | 0 | ✅ | `GET /parts` (filtreler adres çubuğunda) |
| Kayıt | `/kayit?sekme=…` | 0 | ✅ | teslim al, makine, katalog kalemi, makine modeli, saha |
| Excel'den içe aktar | `/kayit?sekme=excel` | 1 | ✅ | `GET /import/tires/template`, `POST /import/tires?dry_run=` |
| QR etiketleri | `/etiketler` | 0 | ✅ | `POST /labels` → yazdırma sayfası yeni sekmede |
| QR / seri no arama | üst çubuk | 0 | ✅ | `GET /qr/{kod}` |
| Saha kontrolü (mobil) | `/kontrol`, `/kontrol/:id` | 1 | ✅ | `POST /inspections`, `GET .../sheet`, `PUT .../measurements`, `POST .../photos`, `POST .../complete` |
| Jant uyumluluğu | `/jantlar` | 1 | | `GET /rims/compliance` |
| Raporlar | `/raporlar` | 1 | | PDF uç noktası |
| Stok, bakım planı | `/stok`, `/bakim` | 2 | | Faz 2 |
| Ayarlar | `/ayarlar` | 0–3 | | firma, kullanıcılar, kategoriler, şablonlar |

## Mobil inspeksiyon akışı (Faz 1)

1. **Makineyi tanımla:** QR okut veya listeden seç. Motor saatini gir (son değer önerilir).
2. **Pozisyon seç:** Makine şeması küçük haliyle gelir; ölçülmemiş pozisyonlar boş, ölçülenler tikli.
3. **Ölç:** Profildeki alanlar (lastikte diş derinliği, basınç). Önceki değer gri ipucu olarak görünür; aralık dışı değerde anında uyarı.
4. **Fotoğrafla:** Zorunlu açılar tek tek istenir (taban, yanak). Hasar varsa yakın çekim + hasar tipi.
5. **Bitir:** `POST /inspections/{id}/complete` çağrılır. Eksik varsa kalite kapısı listesi pozisyon pozisyon gösterilir, dokununca ilgili adıma gider.

Hedef süre: lastik başına 1 dakikanın altında.
