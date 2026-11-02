import { Link, useParams } from "react-router";
import { usePart } from "../api/hooks";
import { PartTwin } from "../components/PartActions";
import { Panel } from "../components/ui";
import { STATUS_LABEL, usd } from "../lib/format";

export function PartPage() {
  const { id } = useParams();
  const part = usePart(id);
  const p = part.data;
  return (
    <>
      <div className="page-head">
        <div>
          <p className="crumbs">
            <Link to="/parcalar">Parçalar</Link>
            {p?.asset_code && p.current_asset_id && <> / <Link to={`/makine/${p.current_asset_id}`}>{p.asset_code}</Link></>}
            {" "}/ {p?.serial_no ?? "parça"}
          </p>
          <h1>{p ? `${p.serial_no ?? p.part_name}` : "Parça"}</h1>
          {p && <p className="sub">{p.manufacturer} {p.part_no} · {STATUS_LABEL[p.status]} · QR {p.qr_code} · toplam maliyet {usd(p.cost_total)}</p>}
        </div>
      </div>
      <Panel className="narrow">{id && <PartTwin partId={id} />}</Panel>
    </>
  );
}
