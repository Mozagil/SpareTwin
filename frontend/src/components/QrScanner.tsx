// Kamerayla QR okuma. Tarayıcının kendi okuyucusu (BarcodeDetector, Android Chrome)
// varsa onu, yoksa (iPhone Safari) jsQR kütüphanesini kullanır.
// Kamera izni yoksa veya kamera açılamazsa kod elle girilebilir.
import { useEffect, useRef, useState, type FormEvent } from "react";
import jsQR from "jsqr";

interface Detector {
  detect(source: CanvasImageSource): Promise<{ rawValue: string }[]>;
}

type DetectorCtor = (new (o: { formats: string[] }) => Detector) & { getSupportedFormats?: () => Promise<string[]> };

/** Tarayıcının yerleşik okuyucusu, yalnızca QR'ı gerçekten destekliyorsa.
 *  (Masaüstü Chrome'un bazı sürümlerinde BarcodeDetector tanımlı ama QR desteklemiyor.) */
async function nativeDetector(): Promise<Detector | null> {
  const BD = (window as unknown as { BarcodeDetector?: DetectorCtor }).BarcodeDetector;
  if (!BD) return null;
  try {
    const formats = (await BD.getSupportedFormats?.()) ?? [];
    return formats.includes("qr_code") ? new BD({ formats: ["qr_code"] }) : null;
  } catch {
    return null;
  }
}

export function QrScanner({ onCode, onClose }: { onCode: (code: string) => void; onClose: () => void }) {
  const video = useRef<HTMLVideoElement>(null);
  const [error, setError] = useState<string | null>(null);
  const [manual, setManual] = useState("");
  const done = useRef(false);

  useEffect(() => {
    let stream: MediaStream | null = null;
    let raf = 0;
    let stopped = false;
    const canvas = document.createElement("canvas");
    const ctx = canvas.getContext("2d", { willReadFrequently: true });
    let detector: Detector | null = null;

    const finish = (code: string) => {
      if (done.current) return;
      done.current = true;
      navigator.vibrate?.(60);
      onCode(code.trim());
    };

    const tick = async () => {
      if (stopped) return;
      const v = video.current;
      if (v && v.readyState >= 2 && v.videoWidth > 0) {
        try {
          let fallback = !detector;
          if (detector) {
            try {
              const found = await detector.detect(v);
              if (found[0]?.rawValue) return finish(found[0].rawValue);
            } catch {
              detector = null; // yerleşik okuyucu çalışmadı: kalıcı olarak jsQR'a geç
              fallback = true;
            }
          }
          if (fallback && ctx) {
            // Hız için kareyi küçültüp tara
            const scale = Math.min(1, 640 / v.videoWidth);
            canvas.width = Math.round(v.videoWidth * scale);
            canvas.height = Math.round(v.videoHeight * scale);
            ctx.drawImage(v, 0, 0, canvas.width, canvas.height);
            const data = ctx.getImageData(0, 0, canvas.width, canvas.height);
            const r = jsQR(data.data, data.width, data.height, { inversionAttempts: "dontInvert" });
            if (r?.data) return finish(r.data);
          }
        } catch {
          /* tek karelik hata önemsiz, devam */
        }
      }
      raf = requestAnimationFrame(tick);
    };

    (async () => {
      if (!navigator.mediaDevices?.getUserMedia) {
        setError("Bu tarayıcı kameraya erişemiyor. Kodu aşağıya elle yazın.");
        return;
      }
      detector = await nativeDetector();
      try {
        stream = await navigator.mediaDevices.getUserMedia({
          video: { facingMode: { ideal: "environment" }, width: { ideal: 1280 }, height: { ideal: 720 } },
          audio: false,
        });
        if (stopped) return stream.getTracks().forEach((t) => t.stop());
        if (video.current) {
          video.current.srcObject = stream;
          await video.current.play().catch(() => undefined);
        }
        raf = requestAnimationFrame(tick);
      } catch (e) {
        const name = (e as { name?: string }).name;
        setError(
          name === "NotAllowedError"
            ? "Kamera izni verilmedi. Tarayıcı ayarlarından izin verin ya da kodu elle yazın."
            : "Kamera açılamadı. Kodu aşağıya elle yazın.",
        );
      }
    })();

    return () => {
      stopped = true;
      cancelAnimationFrame(raf);
      stream?.getTracks().forEach((t) => t.stop());
    };
  }, [onCode]);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && onClose();
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose]);

  const submit = (e: FormEvent) => {
    e.preventDefault();
    if (manual.trim()) onCode(manual.trim().toUpperCase());
  };

  return (
    <div className="scanner" role="dialog" aria-modal="true" aria-label="QR kodu okut">
      <div className="scanner-top">
        <strong>QR kodu okut</strong>
        <button className="scanner-close" onClick={onClose} aria-label="Kapat">×</button>
      </div>
      <div className="scanner-view">
        {!error && <video ref={video} playsInline muted aria-label="Kamera görüntüsü" />}
        {!error && <div className="scanner-frame" aria-hidden="true" />}
        {error && <p className="scanner-error" role="alert">{error}</p>}
      </div>
      <p className="scanner-hint">Etiketi çerçevenin içine getirin; okunduğunda kendiliğinden devam eder.</p>
      <form className="scanner-manual" onSubmit={submit}>
        <input value={manual} onChange={(e) => setManual(e.target.value)} placeholder="ST-A-… veya ST-P-…"
               aria-label="QR kodunu elle yaz" autoCapitalize="characters" />
        <button className="btn btn-primary" disabled={!manual.trim()}>Devam</button>
      </form>
    </div>
  );
}
