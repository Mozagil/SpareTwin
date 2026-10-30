# WeWeb rehberi

WeWeb arayüzü sık güncelleniyor; menü isimleri değişmiş olabilir. Şüphede kalınca WeWeb dokümanına bakın: https://docs.weweb.io

API'nin tam ve güncel listesi her zaman `/docs` adresindeki Swagger sayfasındadır.

## 1. API taban adresi

| Ortam | Adres |
|---|---|
| Codespace (geliştirme) | `https://<codespace>-8000.app.github.dev` (port **Public** yapılmalı, README'ye bak) |
| Geliştirme sunucusu | `https://api-dev.<alan-adı>` |
| Canlı | `https://api.<alan-adı>` |

WeWeb'de bunu bir **global değişken** (`apiBase`) olarak tanımlayın; tüm isteklerde `{{apiBase}}/assets` gibi kullanın. Ortam değişince tek yerden değişir.

API tarafında WeWeb'in adresleri `CORS_ORIGINS` ayarına yazılmalı (editör önizleme adresi ve yayınlanan uygulama adresi). Tarayıcı konsolunda "CORS" hatası görürseniz eksik adres oradadır. Geliştirmede `CORS_ORIGINS=*` kullanılabilir.

## 2. Giriş: Custom Auth

WeWeb'in yeni arayüzünde **Data & API → Authentication → Custom Auth** (eski arayüzde **Plugins → Authentication → Token Based Auth**).

**Giriş workflow'u** (giriş formunun gönderiminde):

1. HTTP isteği: `POST {{apiBase}}/auth/login`, gövde `{"email": ..., "password": ...}`.
2. **Authenticate** eylemi: Access Token = `access_token`, Refresh Token = `refresh_token`, **Persist Session** açık.
3. **Set user** eylemi: yanıttaki `user` nesnesi (id, ad, e-posta, `memberships`).
4. Firma seçimi (aşağıda) ve ana sayfaya geçiş.

Hata durumunda API `{"detail": "E-posta veya parola hatalı"}` döner; `detail` alanını formun altında gösterin.

**On user load** (uygulama her açıldığında, zorunlu):

1. `GET {{apiBase}}/auth/me`, başlık `Authorization: Bearer <access token>`.
2. Başarılıysa **Set user**.
3. 401 dönerse: `POST {{apiBase}}/auth/refresh` gövde `{"refresh_token": ...}` → yeni token'larla **Authenticate** → tekrar `/auth/me` → **Set user**.
4. Refresh de 401 dönerse **Clear Session** ve giriş sayfası.

Bu adım kurulmazsa kullanıcı sayfa yenilendiğinde çıkış yapmış görünür.

**Erişim token'ı 30 dakikada dolar.** Tüm API isteklerini tek bir yardımcı (global) workflow'dan geçirin: istek 401 dönerse bir kez refresh yapıp isteği tekrarlasın. Her yenilemede yeni bir `refresh_token` gelir; eskisi artık geçersizdir, mutlaka yenisini saklayın (eski token tekrar kullanılırsa güvenlik gereği kullanıcının tüm oturumları kapanır).

**Çıkış:** `POST {{apiBase}}/auth/logout` gövde `{"refresh_token": ...}` → **Clear Session**.

## 3. Firma bağlamı

`/auth/me` ve giriş yanıtındaki `memberships` listesi kullanıcının firmalarını ve rolünü verir.

- Tek firma varsa doğrudan seçin. API bu durumda firma başlığı istemez.
- Birden fazlaysa seçim ekranı gösterin, seçilen `tenant_id`'yi global değişkende tutun ve **her istekte** `X-Tenant-Id` başlığı olarak gönderin.
- Rolü (`owner`, `admin`, `manager`, `technician`, `viewer`) arayüzde düğmeleri gizlemek için kullanın. Asıl kontrol API'de; izleyici bir işlem denerse 403 döner.

## 4. Ortak istek ayarları

Her istekte:

```
Authorization: Bearer {{access_token}}
X-Tenant-Id: {{tenantId}}        (yalnızca çok firmalı kullanıcıda)
Content-Type: application/json
```

API hataları her zaman aynı biçimde gelir; arayüzde doğrudan gösterilebilir:

| Kod | Anlamı | Örnek `detail` |
|---|---|---|
| 401 | Oturum yok veya süresi dolmuş | "Oturum geçersiz veya süresi dolmuş" |
| 403 | Yetki yok | "Bu işlem için yetkiniz yok" |
| 404 | Kayıt yok (veya başka firmanın) | "Parça bulunamadı" |
| 409 | Çakışma | "Pozisyon A2-L dolu; önce mevcut parçayı sökün" |
| 422 | Geçersiz girdi veya iş kuralı | "Motor saati geri gidemez (mevcut 12480.0, girilen 100)" |

422 girdi hatalarında ek olarak `fields` listesi gelir (`[{"field": "reason", "message": ...}]`); form alanlarının altına yazdırılabilir.

## 5. Koleksiyonlar (okuma)

| Koleksiyon | İstek | Ne zaman yenilenir | Kullanıldığı yer |
|---|---|---|---|
| `fleet` | `GET /assets` | Sayfa açılışı, işlem sonrası | Filo şeridi |
| `machine` | `GET /assets/{id}` | Makine seçilince | Şema (`positions` içinde x/y, bant, kalan saat) |
| `part` | `GET /parts/{id}` | Parça seçilince | Parça ikizi; lastikse `tire`, jantsa `rim` alanları dolu |
| `partEvents` | `GET /parts/{id}/events` | Parça seçilince | Zaman çizelgesi |
| `partMeasurements` | `GET /parts/{id}/measurements?metric=tread_depth_mm` | Parça seçilince | Aşınma grafiği |
| `stock` | `GET /parts?status=in_stock&category=tire` | Takma modalı açılınca | Takılacak parça seçimi |
| `rims` | `GET /rims/compliance` | Sayfa açılışı | Jant uyumluluğu |
| `categories` | `GET /catalog/categories` | Uygulama açılışı | İnspeksiyon formu alanları (`measurement_profile`) |

Koleksiyonları gereksiz yere sayfa açılışında değil, ilgili seçim değiştiğinde çekin.

## 6. İşlemler (yazma)

| Kullanıcı eylemi | İstek | Gövde |
|---|---|---|
| Motor saati gir | `POST /assets/{id}/meter` | `{"hours": 12510}` |
| Parça tak | `POST /parts/{id}/install` | `{"asset_id": "...", "position": "A2-L"}` |
| Parça sök | `POST /parts/{id}/remove` | `{"reason": "worn_out", "next_status": "scrapped"}` |
| Tamir, NDT, kaplama dönüşü | `POST /parts/{id}/events` | `{"event": "inspected", "reason": "ndt"}` |
| QR okut | `GET /qr/{kod}` | → `{"type": "asset" \| "part", "id": ...}` |

Her yazma işleminden sonra etkilenen koleksiyonları (`fleet`, `machine`, `part`) yenileyin.

## 7. Mobil inspeksiyon akışı

1. `POST /inspections` gövde `{"asset_id": ..., "asset_hours": 9400}` → `id`.
2. Her pozisyon için ölçümler: `PUT /inspections/{id}/measurements` gövde `{"items": [{"part_item_id": ..., "metric": "tread_depth_mm", "value": 12, "unit": "mm"}]}`. Aynı parça+ölçüm tekrar gönderilirse güncellenir; teknisyen rahatça düzeltebilir.
3. Fotoğraflar: `POST /inspections/{id}/photos`, **multipart/form-data**: `file`, `part_item_id`, `angle` (`tread`, `sidewall`...). Aynı açı tekrar yüklenirse eskisinin yerine geçer. Telefonda çekilen fotoğrafı yüklemeden önce ~1600 px'e küçültün.
4. `POST /inspections/{id}/complete`:
   - `status = "completed"` → bitti.
   - `status = "draft"` → `qc_flags` listesini gösterin. Her öğede `gate` (KK1–KK4), `position`, `message` var; dokununca ilgili pozisyona götürün.

Formdaki alanları elle değil, kategorinin `measurement_profile` listesinden üretin: her öğede `metric`, `label`, `unit`, `required`, `min`, `max` var. Yeni parça tipi eklendiğinde form kendiliğinden uyum sağlar.

## 8. Fotoğraf gösterme

`GET /media/{attachment_id}/url` → `{"url": "...", "expires_in": 600}`. Bu linki doğrudan bir resim elemanının kaynağı yapın; oturum başlığı gerekmez. Link 10 dakika sonra geçersiz olur, sayfa uzun açık kalırsa yeniden isteyin.

## 9. Makine şeması

Şema, prototipteki SVG çiziminin aynısı. `GET /assets/{id}` yanıtındaki `layout` (`loader`, `reach_stacker`, `forklift`) gövde çizimini, `positions` listesi parçaların yerini ve rengini belirler.

1. **WeWeb özel bileşeni (önerilen):** `prototype/index.html` içindeki `bodyShape`, `tireSlot`, `compSlot` fonksiyonları bir Vue bileşenine taşınır. Girdi: `layout`, `positions`. Çıktı: `select` olayı (pozisyon kodu ve `part_item_id`).
2. **Hızlı başlangıç:** WeWeb'in HTML/özel kod elemanına SVG'yi formülle üretip basmak. Yalnızca Faz 0 demosu için.

## 10. Kontrol listesi (Faz 0 sonu)

- [ ] `apiBase` global değişkeni, ortam başına doğru adres
- [ ] Giriş, **On user load** ile oturumun sayfa yenilemede korunması, çıkış
- [ ] 401'de bir kez refresh yapıp isteği tekrarlayan yardımcı workflow
- [ ] Firma seçimi ve `X-Tenant-Id`
- [ ] Filo şeridi `GET /assets`'ten
- [ ] Makine şeması özel bileşen olarak, seçim parça ikizini açıyor
- [ ] Parça ikizi: bilgiler, aşınma grafiği, zaman çizelgesi
- [ ] Takma/sökme modalı; API hata mesajları kullanıcıya görünüyor
- [ ] İki farklı firmanın kullanıcısıyla izolasyon elle de doğrulandı
