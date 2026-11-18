import { useState } from "react";
import type { FieldDef } from "../layout.generated";
import type { FieldObj, Source } from "../api";
import { SOURCE_LABEL, formatValue } from "../status";
import StatusBadge from "./StatusBadge";

interface Props {
  def: Pick<FieldDef, "label" | "path"> & Partial<Pick<FieldDef, "kind" | "sensitive">>;
  field: FieldObj | null;
  sources: Source[];
  busy: boolean;
  readOnly?: boolean;
  onSet: (value: string) => void;
  onConfirm: () => void;
  onClear: () => void;
}

export function sourceText(field: FieldObj, sources: Source[]): string {
  const src = sources.find((s) => s.source_id === field.source_document);
  const kind = src ? (SOURCE_LABEL[src.source_type] ?? src.source_type) : null;
  const parts = [kind, field.source_document, field.source_context].filter(Boolean);
  return parts.length ? parts.join(" · ") : "—";
}

export default function FieldRow({ def, field, sources, busy, readOnly, onSet, onConfirm, onClear }: Props) {
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState("");

  if (!field) {
    return <div className="field"><div className="label">{def.label}</div><div className="value muted">Tidak ada di record ini</div></div>;
  }
  const empty = field.value === null || field.value === undefined;
  const canConfirm = !empty && field.status !== "conflict" && field.status !== "verified";
  const canClear = !(empty && field.status === "missing");

  function startEdit() {
    setDraft(empty ? "" : String(field!.value));
    setEditing(true);
  }
  function save() {
    onSet(draft);
    setEditing(false);
  }

  return (
    <div className={`field ${def.sensitive ? "sensitive" : ""}`} data-path={def.path}>
      <div className="label">{def.label}</div>
      {!editing ? (
        <div className={`value ${empty ? "muted" : ""}`}>{formatValue(field.value)}</div>
      ) : (
        <div className="edit">
          {def.kind === "yesno" ? (
            <select aria-label={`Nilai ${def.label}`} value={draft} onChange={(e) => setDraft(e.target.value)}>
              <option value="">— pilih —</option><option value="Yes">Yes</option><option value="No">No</option>
            </select>
          ) : (
            <input type="text" aria-label={`Nilai ${def.label}`} value={draft} autoComplete="off" spellCheck={false}
                   onChange={(e) => setDraft(e.target.value)}
                   onKeyDown={(e) => { if (e.key === "Enter" && draft.trim()) save(); if (e.key === "Escape") setEditing(false); }} />
          )}
          <button type="button" className="primary" disabled={busy || !draft.trim()} onClick={save}>Simpan</button>
          <button type="button" onClick={() => setEditing(false)}>Batal</button>
        </div>
      )}
      <div className="meta">
        <StatusBadge status={field.status} />
        <span className="source" title="Sumber">Sumber: {sourceText(field, sources)}</span>
      </div>
      {!readOnly && !editing && (
        <div className="buttons">
          <button type="button" disabled={busy} onClick={startEdit}>Ubah</button>
          <button type="button" disabled={busy || !canConfirm} onClick={onConfirm}>Confirm</button>
          <button type="button" disabled={busy || !canClear} onClick={onClear}>Kosongkan</button>
        </div>
      )}
    </div>
  );
}
