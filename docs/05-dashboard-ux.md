# Dashboard ve kullanıcı deneyimi

Referans: `prototype/index.html` (Codespace'te `make prototype`). Prototip demo veriyle çalışır ve hesapları API'nin döndürdüğü değerlerle aynı formüllerle yapar; WeWeb'de birebir aynı ekran kurulacak.

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

## Ekran listesi (WeWeb sayfaları)

| Sayfa | Yol | Faz | API |
|---|---|---|---|
| Giriş | `/giris` | 0 | `POST /auth/login` |
| Filo durumu | `/` | 0 | `GET /assets` |
| Makine detayı | `/makine/:id` | 0 | `GET /assets/{id}` (pozisyonlar ve takılı parçalar dahil) |
| Parça ikizi | `/parca/:id` | 0 | `GET /parts/{id}`, `/parts/{id}/events`, `/parts/{id}/measurements` |
| QR sonucu | `/q/:qr` | 0 | `GET /qr/{code}` → makine veya parçaya yönlendirir |
| İnspeksiyon (mobil) | `/inspeksiyon/:id` | 1 | `POST /inspections`, `PUT .../measurements`, `POST .../photos`, `POST .../complete` |
| Takma / sökme | modal | 1 | `POST /parts/{id}/install`, `POST /parts/{id}/remove` |
| Jant uyumluluğu | `/jantlar` | 1 | `GET /rims/compliance` |
| Raporlar | `/raporlar` | 1 | PDF uç noktası (Faz 1) |
| Stok | `/stok` | 2 | `GET /parts?status=in_stock` + stok uç noktaları (Faz 2) |
| Bakım planı | `/bakim` | 2 | Faz 2 |
| Ayarlar | `/ayarlar` | 0–3 | firma, kullanıcılar, kategoriler, şablonlar |

## Mobil inspeksiyon akışı (Faz 1)

1. **Makineyi tanımla:** QR okut veya listeden seç. Motor saatini gir (son değer önerilir).
2. **Pozisyon seç:** Makine şeması küçük haliyle gelir; ölçülmemiş pozisyonlar boş, ölçülenler tikli.
3. **Ölç:** Profildeki alanlar (lastikte diş derinliği, basınç). Önceki değer gri ipucu olarak görünür; aralık dışı değerde anında uyarı.
4. **Fotoğrafla:** Zorunlu açılar tek tek istenir (taban, yanak). Hasar varsa yakın çekim + hasar tipi.
5. **Bitir:** `POST /inspections/{id}/complete` çağrılır. Eksik varsa kalite kapısı listesi pozisyon pozisyon gösterilir, dokununca ilgili adıma gider.

Hedef süre: lastik başına 1 dakikanın altında.
