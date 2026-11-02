"""Excel / CSV ile toplu lastik içe aktarma.

GET  /import/tires/template          → boş şablon (.xlsx), örnek satırlar ve açıklama sayfası
POST /import/tires?dry_run=true      → önizleme: her satırın durumu, hiçbir şey yazılmaz
POST /import/tires?dry_run=false     → içe aktar: hata varsa 422 ve hiçbir şey yazılmaz (ya hepsi ya hiçbiri)
"""

from typing import Annotated

from fastapi import APIRouter, File, HTTPException, Query, UploadFile
from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse, Response

from ..importer import MAX_BYTES, Context, ImportFileError, commit, read_rows, summarize, validate
from .deps import TenantCtx

router = APIRouter(prefix="/import", tags=["İçe aktarma"])

XLSX = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


@router.get("/tires/template", summary="Lastik içe aktarma şablonu (.xlsx)")
def template(ctx: TenantCtx):
    from ..importer import template_xlsx

    ctx.require("manager")
    return Response(template_xlsx(), media_type=XLSX,
                    headers={"Content-Disposition": 'attachment; filename="sparetwin-lastik-sablonu.xlsx"'})


def _row_out(r):
    plan = r.plan
    return {
        "row": r.n,
        "status": r.status,
        "errors": r.errors,
        "warnings": r.warnings,
        "asset_code": plan.get("asset", {}).get("code") or r.data.get("asset_code"),
        "position": plan.get("tire", {}).get("position") or r.data.get("position"),
        "size": r.data.get("size"),
        "brand": r.data.get("brand"),
        "serial_no": plan.get("tire", {}).get("serial_no") or r.data.get("serial_no"),
        "tread_mm": plan.get("tire", {}).get("tread_mm"),
    }


@router.post("/tires", summary="Lastik listesini önizle veya içe aktar")
def import_tires(
    ctx: TenantCtx,
    file: Annotated[UploadFile, File(description=".xlsx veya .csv")],
    dry_run: Annotated[bool, Query(description="true: yalnızca önizleme")] = True,
):
    ctx.require("manager")
    data = file.file.read(MAX_BYTES + 1)
    try:
        raw, unknown = read_rows(data, file.filename or "dosya.xlsx")
    except ImportFileError as e:
        raise HTTPException(422, str(e))

    with ctx.tx() as conn:
        rows = validate(Context(conn, ctx.tenant_id), raw)
        summary = summarize(rows)
        body = {"summary": summary, "unknown_columns": unknown, "rows": [_row_out(r) for r in rows]}
        if dry_run:
            return body
        if summary["errors"]:
            # Hiçbir şey yazılmadı; önizlemeyle aynı rapor döner
            return JSONResponse(
                jsonable_encoder({"detail": f"{summary['errors']} satırda hata var; hiçbir şey kaydedilmedi", **body}),
                status_code=422)
        result = commit(conn, ctx.tenant_id, ctx.user_id, rows)
    return {**body, **result}
