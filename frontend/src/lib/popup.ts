/** Açılır pencere engelleyicisine takılmamak için sekme tıklama anında açılır,
 *  adres istek tamamlanınca verilir. Hata olursa sekme kapatılır. */
export async function openInNewTab(getUrl: () => Promise<string>): Promise<void> {
  const w = window.open("", "_blank");
  if (w) w.document.title = "Hazırlanıyor…";
  try {
    const url = await getUrl();
    if (w) w.location.href = url;
    else window.location.href = url;
  } catch (e) {
    w?.close();
    throw e;
  }
}
