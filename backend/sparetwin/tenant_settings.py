"""Firma ayarları: tenants.settings (jsonb) içindeki eşikler.

Varsayılanlar burada tek yerde durur; aynı değerler SQL görünümlerinde
(0013) coalesce ile tekrarlanır. Birini değiştirirsen diğerini de değiştir.
"""

from __future__ import annotations

from typing import Any
from uuid import UUID

import psycopg

DEFAULT_THRESHOLDS: dict[str, float] = {
    "critical_pct": 20,              # kalan ömür / diş bu yüzdenin altındaysa kritik
    "watch_pct": 40,                 # bu yüzdenin altındaysa izlemede
    "rim_due_soon_pct": 90,          # NDT periyodunun bu yüzdesi dolunca "yaklaşıyor"
    "inspection_interval_days": 30,  # bu kadar gün kontrol edilmeyen makine bildirilir
}

THRESHOLD_LIMITS: dict[str, tuple[float, float]] = {
    "critical_pct": (1, 95),
    "watch_pct": (2, 99),
    "rim_due_soon_pct": (50, 99),
    "inspection_interval_days": (1, 365),
}


def thresholds(conn: psycopg.Connection, tenant_id: UUID) -> dict[str, float]:
    """Firmanın eşikleri; eksik anahtarlar varsayılanla doldurulur."""
    row = conn.execute("select settings from public.tenants where id = %s", [tenant_id]).fetchone()
    raw: dict[str, Any] = (row["settings"] or {}).get("thresholds", {}) if row else {}
    out = dict(DEFAULT_THRESHOLDS)
    for k in out:
        v = raw.get(k)
        if isinstance(v, (int, float)) and not isinstance(v, bool):
            out[k] = v
    return out
