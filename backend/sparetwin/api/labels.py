"""QR etiketleri.

1) POST /labels (oturumla): hangi makine/parçalar için etiket istendiği.
   Firma kontrolü burada yapılır, kısa ömürlü bir yazdırma linki döner.
2) GET /labels/sheet/{token}: A4 yazdırma sayfası. Oturum başlığı gerekmez,
   böylece arayüz yeni sekmede açabilir. Link birkaç dakika geçerlidir.

Etiket ölçüsü: 63,5 × 38,1 mm, A4'te 3 × 7 = 21 etiket (yaygın hazır etiket
kâğıdı ölçüsü, ör. L7160). QR'ın içinde yalnızca kod vardır (ST-A-..., ST-P-...).
"""

import base64
import html
import io
from datetime import UTC, datetime, timedelta
from uuid import UUID

import jwt
import segno
from fastapi import APIRouter, HTTPException
from fastapi.responses import HTMLResponse
from pydantic import BaseModel, Field, model_validator

from ..db import owner_tx
from .deps import AppSettings, TenantCtx

router = APIRouter(prefix="/labels", tags=["Etiketler"])

MAX_LABELS = 63  # 3 sayfa


class LabelsIn(BaseModel):
    asset_ids: list[UUID] = Field(default_factory=list, max_length=MAX_LABELS)
    part_ids: list[UUID] = Field(default_factory=list, max_length=MAX_LABELS)
    skip: int = Field(0, ge=0, le=20, description="Yarım kullanılmış kâğıtta atlanacak etiket sayısı")

    @model_validator(mode="after")
    def _check(self):
        n = len(self.asset_ids) + len(self.part_ids)
        if n == 0:
            raise ValueError("En az bir makine veya parça seçilmeli")
        if n > MAX_LABELS:
            raise ValueError(f"Tek seferde en fazla {MAX_LABELS} etiket")
        return self


def _pack(ids: list[UUID]) -> str:
    return "".join(base64.urlsafe_b64encode(i.bytes).decode().rstrip("=") for i in ids)


def _unpack(s: str) -> list[UUID]:
    return [UUID(bytes=base64.urlsafe_b64decode(s[i:i + 22] + "==")) for i in range(0, len(s), 22)]


@router.post("", summary="Etiket yazdırma linki oluştur")
def create_label_link(body: LabelsIn, ctx: TenantCtx, settings: AppSettings):
    with ctx.tx() as conn:
        n_assets = conn.execute(
            "select count(*) as n from public.assets where tenant_id = %s and id = any(%s)",
            [ctx.tenant_id, body.asset_ids],
        ).fetchone()["n"]
        n_parts = conn.execute(
            "select count(*) as n from public.part_items where tenant_id = %s and id = any(%s)",
            [ctx.tenant_id, body.part_ids],
        ).fetchone()["n"]
    if n_assets != len(set(body.asset_ids)) or n_parts != len(set(body.part_ids)):
        raise HTTPException(404, "Seçilen kayıtlardan bazıları bulunamadı")
    token = jwt.encode(
        {
            "type": "labels",
            "t": str(ctx.tenant_id),
            "a": _pack(body.asset_ids),
            "p": _pack(body.part_ids),
            "s": body.skip,
            "exp": datetime.now(UTC) + timedelta(minutes=settings.media_url_minutes),
        },
        settings.jwt_secret,
        algorithm=settings.jwt_algorithm,
    )
    return {
        "url": f"{settings.public_base_url.rstrip('/')}/labels/sheet/{token}",
        "count": n_assets + n_parts,
        "expires_in": settings.media_url_minutes * 60,
    }


def _qr_svg(code: str) -> str:
    buf = io.BytesIO()
    segno.make(code, error="m", micro=False).save(
        buf, kind="svg", xmldecl=False, svgns=True, nl=False, border=0, omitsize=True, dark="#000"
    )
    return buf.getvalue().decode()


@router.get("/sheet/{token}", response_class=HTMLResponse, include_in_schema=False)
def label_sheet(token: str, settings: AppSettings):
    try:
        p = jwt.decode(token, settings.jwt_secret, algorithms=[settings.jwt_algorithm])
    except jwt.PyJWTError:
        raise HTTPException(403, "Linkin süresi dolmuş, etiketleri yeniden oluşturun")
    if p.get("type") != "labels":
        raise HTTPException(403, "Geçersiz link")
    tenant, asset_ids, part_ids = UUID(p["t"]), _unpack(p["a"]), _unpack(p["p"])

    # İmzalı token firma kimliğini taşır; sorgu sahip yetkisiyle ama firma filtresiyle yapılır.
    with owner_tx() as conn:
        assets = conn.execute(
            """select a.qr_code as code, a.code as title,
                      coalesce(am.manufacturer || ' ' || am.model, '') as line1, coalesce(a.serial_no, '') as line2
                 from public.assets a left join public.asset_models am on am.id = a.model_id
                where a.tenant_id = %s and a.id = any(%s) order by a.code""",
            [tenant, asset_ids],
        ).fetchall()
        parts = conn.execute(
            """select pi.qr_code as code, coalesce(pi.serial_no, 'Seri no yok') as title,
                      p.name as line1, coalesce(p.manufacturer, '') as line2
                 from public.part_items pi join public.parts p on p.id = pi.part_id
                where pi.tenant_id = %s and pi.id = any(%s) order by p.name, pi.serial_no""",
            [tenant, part_ids],
        ).fetchall()

    cells = ['<div class="label empty"></div>'] * int(p.get("s", 0))
    for r in [*assets, *parts]:
        e = html.escape
        cells.append(
            f'<div class="label"><div class="qr">{_qr_svg(r["code"])}</div>'
            f'<div class="txt"><div class="brand" lang="en">SpareTwin</div>'
            f'<div class="title">{e(r["title"])}</div>'
            f'<div class="line">{e(r["line1"])}</div><div class="line">{e(r["line2"])}</div>'
            f'<div class="code">{e(r["code"])}</div></div></div>'
        )
    return HTMLResponse(SHEET_HTML.replace("{{CELLS}}", "".join(cells)).replace("{{N}}", str(len(assets) + len(parts))),
                        headers={"Cache-Control": "no-store", "X-Robots-Tag": "noindex"})


SHEET_HTML = """<!doctype html>
<html lang="tr"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>SpareTwin QR etiketleri</title>
<style>
  @page { size: A4; margin: 15.1mm 7.2mm 0 7.2mm; }
  * { box-sizing: border-box; }
  body { margin: 0; font-family: "Barlow", "Segoe UI", Arial, sans-serif; color: #000; background: #E4E8EA; }
  .bar { position: sticky; top: 0; display: flex; gap: 12px; align-items: center; padding: 12px 16px;
         background: #17202A; color: #fff; font-size: 15px; }
  .bar button { border: 0; border-radius: 999px; padding: 8px 18px; background: #4DB1BD; color: #0B1418;
                font: inherit; font-weight: 600; cursor: pointer; }
  .bar span { opacity: .8; }
  .sheet { width: 210mm; margin: 16px auto; background: #fff; padding: 15.1mm 7.2mm;
           display: grid; grid-template-columns: repeat(3, 63.5mm); grid-auto-rows: 38.1mm; column-gap: 2.5mm; }
  .label { display: flex; align-items: center; gap: 2.5mm; padding: 2.5mm 3mm; overflow: hidden;
           break-inside: avoid; outline: 1px dashed #C8D0D6; }
  .label.empty { outline: none; }
  .qr { flex: 0 0 26mm; height: 26mm; }
  .qr svg { width: 100%; height: 100%; display: block; }
  .txt { min-width: 0; line-height: 1.15; }
  .brand { font-size: 6.5pt; letter-spacing: .4pt; text-transform: uppercase; color: #444; }
  .title { font-size: 11pt; font-weight: 700; margin: .6mm 0 .4mm; word-break: break-all; }
  .line { font-size: 7pt; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
  .code { font-family: ui-monospace, Consolas, monospace; font-size: 6.5pt; margin-top: .8mm; word-break: break-all; }
  @media print {
    body { background: #fff; }
    .bar { display: none; }
    .sheet { margin: 0; padding: 0; width: auto; }
    .label { outline: none; }
  }
</style></head>
<body>
  <div class="bar"><button onclick="window.print()">Yazdır</button>
    <span>{{N}} etiket · A4, 63,5 × 38,1 mm (3 × 7). Yazdırırken ölçeği “%100 / gerçek boyut” seçin.</span></div>
  <div class="sheet">{{CELLS}}</div>
</body></html>"""
