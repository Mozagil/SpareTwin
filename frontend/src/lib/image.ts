/**
 * Telefonda çekilen fotoğrafı yüklemeden önce küçültür (uzun kenar 1600 px, JPEG).
 * Tarayıcı fotoğrafı EXIF yönüne göre zaten doğru çizer; çıktıda meta veri (GPS) kalmaz.
 * iPhone'un HEIC fotoğrafları da tarayıcı tarafından açılıp JPEG'e çevrilir.
 */
export async function shrinkImage(file: Blob, max = 1600, quality = 0.85): Promise<Blob> {
  const url = URL.createObjectURL(file);
  try {
    const img = await new Promise<HTMLImageElement>((resolve, reject) => {
      const i = new Image();
      i.onload = () => resolve(i);
      i.onerror = () => reject(new Error("Fotoğraf açılamadı"));
      i.src = url;
    });
    const scale = Math.min(1, max / Math.max(img.naturalWidth, img.naturalHeight));
    const w = Math.round(img.naturalWidth * scale);
    const h = Math.round(img.naturalHeight * scale);
    const canvas = document.createElement("canvas");
    canvas.width = w;
    canvas.height = h;
    canvas.getContext("2d")!.drawImage(img, 0, 0, w, h);
    return await new Promise<Blob>((resolve, reject) =>
      canvas.toBlob((b) => (b ? resolve(b) : reject(new Error("Fotoğraf hazırlanamadı"))), "image/jpeg", quality),
    );
  } finally {
    URL.revokeObjectURL(url);
  }
}
