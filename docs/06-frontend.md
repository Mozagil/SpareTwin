# Frontend rehberi

React 19 + TypeScript + Vite. Kod: `frontend/src/`.

## Çalıştırma

```bash
make dev     # API (8000) + frontend (5173) birlikte; Ports sekmesinde 5173'ü aç
make test    # backend + frontend testleri
make build   # üretim derlemesi → frontend/dist
```

Tarayıcı yalnızca 5173 ile konuşur. `/api` ile başlayan istekleri Vite, Codespace'in içinden FastAPI'ye aktarır (`vite.config.ts`). 8000 portunu dışarı açmak gerekmez; API dokümanına (`/docs`) bakmak için Ports sekmesinden 8000 açılabilir.

## Klasör yapısı

| Yol | İçerik |
|---|---|
| `src/api/client.ts` | `fetch` sarmalayıcısı: token, 401'de tek seferlik yenileme, `X-Tenant-Id`, Türkçe `ApiError` |
| `src/api/hooks.ts` | Tüm okuma/yazma işlemleri (TanStack Query). Yazmadan sonra ilgili ekranlar kendiliğinden tazelenir |
| `src/api/types.ts` | API yanıt tipleri (backend ile eşleşir) |
| `src/auth/AuthProvider.tsx` | Oturum durumu, firma seçimi, `can("manager")` gibi rol kontrolü |
| `src/components/MachineSchematic.tsx` | Makine üstten görünüş şeması (pozisyon x/y şablondan) |
| `src/components/PartActions.tsx` | Parça ikizi paneli; takma, sökme, olay kaydı pencereleri |
| `src/components/WearChart.tsx` | Diş derinliği – parça saati grafiği ve tahmin |
| `src/components/QrScanner.tsx` | Kamerayla QR okuma: tarayıcının QR desteği varsa onu, yoksa jsQR'ı kullanır; kamera yoksa elle giriş |
| `src/pages/Inspection*.tsx`, `src/lib/inspection.ts`, `src/lib/image.ts` | Mobil kontrol formu, aralık uyarıları, telefonda fotoğraf küçültme |
| `src/components/Images.tsx` | Görsel kutusu (yükle/değiştir/kaldır), saha fotoğrafı şeridi, büyütme penceresi |
| `src/components/ui.tsx` | Panel, Modal, Field, BandChip, ErrorNote… |
| `src/pages/` | Sayfalar (bkz. `05-dashboard-ux.md` ekran listesi) |
| `src/lib/format.ts` | Türkçe sayı/tarih biçimleri, durum ve sebep etiketleri |
| `src/styles/app.css` | Tasarım jetonları (açık/koyu tema) ve tüm stiller |

## Kurallar

- **İş kuralı yazılmaz.** Kalan saat, sağlık bandı, saat başı maliyet gibi her değer API'den gelir. Arayüz yalnızca gösterir ve biçimlendirir.
- **Yetki API'dedir.** `can()` yalnızca düğmeleri gizlemek içindir; asıl kontrol backend'de (izleyici bir işlem denerse 403).
- **Hata mesajları API'den gelir.** `ErrorNote` bileşeni `detail` ve alan listesini (`fields`) olduğu gibi gösterir.
- **Erişilebilirlik:** Form alanları `Field` ile (etiket + açıklama `aria-describedby`); şema öğeleri klavyeyle seçilebilir; durum renkleri her zaman metinle birlikte.
- **Durum sayfa adresinde:** Parça listesi filtreleri ve kayıt sekmesi URL'de tutulur; bağlantı paylaşılabilir.

## Oturum

| Konu | Davranış |
|---|---|
| Erişim token'ı | Yalnızca bellekte (30 dk) |
| Yenileme token'ı | `localStorage` (`st.refresh`); her yenilemede değişir |
| Sayfa yenileme | Açılışta yenileme token'ıyla sessizce yeni oturum |
| 401 | Bir kez yenileme denenir; aynı anda gelen 401'ler tek yenilemeyi bekler |
| Yenileme reddedilirse | Oturum temizlenir, giriş ekranı |
| Firma | Tek firmada otomatik; çok firmada seçim ekranı, `X-Tenant-Id` başlığı |

## Yeni bir sayfa eklemek

1. `src/api/types.ts` içine yanıt tipini, `src/api/hooks.ts` içine hook'u ekle.
2. `src/pages/YeniSayfa.tsx` oluştur; `Panel`, `Loading`, `ErrorNote` ile kur.
3. `src/App.tsx` içine rota, gerekiyorsa `components/Layout.tsx` içine menü öğesi ekle.
4. `npx tsc --noEmit` ve `npm test` ile kontrol et.

## Testler

- `src/api/client.test.ts`: token, yenileme, eşzamanlı 401, hata biçimi, firma başlığı.
- `src/components/MachineSchematic.test.tsx`: durum etiketleri, boş ve ölçümsüz pozisyon, klavye ile seçim.
- `src/components/Images.test.tsx`: rol bazlı "Görsel ekle", model görselinde kaldırma yok, büyütme penceresinde klavye ile gezinme.

Uçtan uca senaryo (giriş → dashboard → QR arama → lastik değişimi → kayıt → etiket → rol kısıtı → mobil) bu sürüm teslim edilmeden önce gerçek tarayıcıda çalıştırıldı.
