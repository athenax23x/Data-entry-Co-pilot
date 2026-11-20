import { useState } from "react";
import type { FieldDef } from "../layout.generated";
import type { FieldObj, Source } from "../api";
import { SOURCE_LABEL, formatValue } from "../status";
import { draftFor, ruleFor, toUsDate } from "../inputs";
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
  const kind = src ? (src.label ?? SOURCE_LABEL[src.source_type] ?? src.source_type) : null;
  const parts = [kind, field.source_document, field.source_context].filter(Boolean);
  return parts.length ? parts.join(" · ") : "—";
}

export default function FieldRow({ def, field, sources, busy, readOnly, onSet, onConfirm, onClear }: Props) {
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState("");
  const [copied, setCopied] = useState<"ok" | "fail" | null>(null);

  if (!field) {
    return <div className="field"><div className="label">{def.label}</div><div className="value muted">Tidak ada di record ini</div></div>;
  }
  const empty = field.value === null || field.value === undefined;
  const isDate = def.kind === "date";
  const shown = isDate && !empty ? toUsDate(field.value) : field.value;      // dates: MM/DD/YYYY, like a US driver license
  const rule = ruleFor(def.kind);
  const draftOk = rule ? rule.ok(draft) : !!draft.trim();
  const canConfirm = !empty && field.status !== "conflict" && field.status !== "verified";
  const canClear = !(empty && field.status === "missing");

  function startEdit() {
    setDraft(empty ? "" : draftFor(def.kind, field!.value));
    setEditing(true);
  }
  // One click copies the value exactly as shown, to paste into the Paykings form. It stays on this laptop.
  async function copy() {
    try {
      await navigator.clipboard.writeText(String(shown));
      setCopied("ok");
    } catch {
      setCopied("fail");
    }
    window.setTimeout(() => setCopied(null), 1800);
  }
  function save() {
    onSet(draft);
    setEditing(false);
  }

  return (
    <div className={`field ${def.sensitive ? "sensitive" : ""}`} data-path={def.path}>
      <div className="label">{def.label}</div>
      {!editing ? (
        empty ? (
          <div className="value muted">{formatValue(field.value)}</div>
        ) : (
          <button type="button" className="value copyable" title="Klik untuk menyalin" aria-label={`Salin ${def.label}`}
                  onClick={() => void copy()}>
            {formatValue(shown)}
            {copied && <span className={`copied ${copied}`} role="status">{copied === "ok" ? "Tersalin" : "Gagal menyalin"}</span>}
          </button>
        )
      ) : (
        <div className="edit">
          {def.kind === "yesno" ? (
            <select aria-label={`Nilai ${def.label}`} value={draft} onChange={(e) => setDraft(e.target.value)}>
              <option value="">— pilih —</option><option value="Yes">Yes</option><option value="No">No</option>
            </select>
          ) : rule ? (
            <input type="text" inputMode={def.kind === "percent" || def.kind === "amount" ? "decimal" : "numeric"}
                   aria-label={`Nilai ${def.label}`} value={draft} autoComplete="off"
                   placeholder={rule.placeholder} spellCheck={false}
                   onChange={(e) => setDraft(rule.mask(e.target.value))}
                   onKeyDown={(e) => { if (e.key === "Enter" && draftOk) save(); if (e.key === "Escape") setEditing(false); }} />
          ) : (
            <input type="text" aria-label={`Nilai ${def.label}`} value={draft} autoComplete="off" spellCheck={false}
                   onChange={(e) => setDraft(e.target.value)}
                   onKeyDown={(e) => { if (e.key === "Enter" && draft.trim()) save(); if (e.key === "Escape") setEditing(false); }} />
          )}
          <button type="button" className="primary" disabled={busy || !draftOk} onClick={save}>Simpan</button>
          {rule && draft && !draftOk && <span className="muted small">{rule.hint}</span>}
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
