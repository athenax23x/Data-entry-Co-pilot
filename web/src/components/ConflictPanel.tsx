import type { Conflict } from "../api";
import { formatValue } from "../status";
import { fieldLabel } from "../labels";
import { pointerToPath } from "../recordpath";

export function conflictLabel(c: Conflict): string {
  return fieldLabel(pointerToPath(c.field_path));
}

export default function ConflictPanel({ conflicts, busy, onResolve }: {
  conflicts: Conflict[]; busy: boolean; onResolve: (cid: string, value: string) => void;
}) {
  const open = conflicts.filter((c) => c.resolution.state === "open");
  return (
    <section className="panel" aria-label="Konflik">
      <h2>Konflik ({open.length})</h2>
      {open.length === 0 && <p className="muted">Tidak ada konflik.</p>}
      {open.map((c) => (
        <div className="conflict" key={c.conflict_id}>
          <div className="label">{conflictLabel(c)} <span className="muted">({c.conflict_id})</span></div>
          <div className="choice">
            <span>Nilai dipertahankan: <strong>{formatValue(c.current_value)}</strong></span>
            {c.current_value !== null && (
              <button type="button" disabled={busy} onClick={() => onResolve(c.conflict_id, String(c.current_value))}>Pertahankan ini</button>
            )}
          </div>
          {c.candidates.map((cand, i) => cand.value !== null && (
            <div className="choice" key={i}>
              <span>Kandidat: <strong>{formatValue(cand.value)}</strong>
                <span className="muted"> · {cand.source_document ?? "—"}{cand.source_context ? ` · ${cand.source_context}` : ""}</span></span>
              <button type="button" disabled={busy} onClick={() => onResolve(c.conflict_id, String(cand.value))}>Pilih ini</button>
            </div>
          ))}
        </div>
      ))}
    </section>
  );
}
