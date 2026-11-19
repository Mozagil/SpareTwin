import type { ReactNode } from "react";
import { Link } from "react-router";
import { useModules } from "../api/hooks";
import type { Modules } from "../api/types";
import { useAuth } from "../auth/AuthProvider";
import { Panel } from "./ui";

const NAME: Record<keyof Modules, string> = { tireiq: "Lastik ve jant", parts: "Yedek parça ve bakım", erp: "KOBİ ERP" };

/** Kapalı bir modülün sayfasına doğrudan adresle gelinirse açıklama gösterir. */
export function ModuleGate({ module, children }: { module: keyof Modules; children: ReactNode }) {
  const mods = useModules();
  const { can } = useAuth();
  if (mods[module]) return <>{children}</>;
  return (
    <Panel title={`${NAME[module]} modülü kapalı`}>
      <p className="muted">Bu firma için {NAME[module].toLowerCase()} modülü açık değil.</p>
      {can("admin") ? <Link className="btn btn-primary" to="/ayarlar">Ayarlar → Modüller</Link>
                    : <p className="muted small">Açmak için firmanızın yöneticisine başvurun.</p>}
    </Panel>
  );
}
