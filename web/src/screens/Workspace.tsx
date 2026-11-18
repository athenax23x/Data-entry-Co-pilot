import { useCallback, useEffect, useState } from "react";
import { go } from "../App";
import * as api from "../api";
import ConflictPanel from "../components/ConflictPanel";
import ContextBox from "../components/ContextBox";
import ErrorBanner from "../components/ErrorBanner";
import FieldRow from "../components/FieldRow";
import { STEPS } from "../layout.generated";
import { extraRows, getField } from "../recordpath";
import { errorMessage, formatTime, isStale, recordStatusLabel } from "../status";

export default function Workspace({ id }: { id: string }) {
  const [state, setState] = useState<{ record: api.MerchantRecord; version: number } | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const load = useCallback(async () => {
    try {
      const r = await api.getMerchant(id);
      setState({ record: r.record, version: r.version });
      return true;
    } catch (e) {
      setError(errorMessage(e));
      return false;
    }
  }, [id]);

  useEffect(() => { void load(); }, [load]);

  /** Every write goes through here: it sends the last loaded version, and on 409 shows the message and reloads. */
  async function write(send: (version: number) => Promise<api.RecordReply>, okNotice?: (r: api.RecordReply) => string): Promise<boolean> {
    if (!state) return false;
    setBusy(true);
    setError(null);
    setNotice(null);
    try {
      const r = await send(state.version);
      setState({ record: r.record, version: r.version });
      if (okNotice) setNotice(okNotice(r));
      return true;
    } catch (e) {
      setError(errorMessage(e));
      if (isStale(e)) await load();
      return false;
    } finally {
      setBusy(false);
    }
  }

  const patch = (path: string, action: "set" | "confirm" | "missing", value?: string) =>
    write((v) => api.updateField(id, path, { expected_version: v, action, value }));

  if (!state) {
    return (
      <section>
        <div className="bar"><h1>{id}</h1><button type="button" onClick={() => go("#/")}>Kembali</button></div>
        <ErrorBanner message={error} onReload={() => { setError(null); void load(); }} />
        {!error && <p className="empty">Memuat…</p>}
      </section>
    );
  }

  const { record, version } = state;
  const sources = record.sources;
  const extras = extraRows(record);

  return (
    <section>
      <div className="bar">
        <h1>{id}</h1>
        <span className={`rec rec-${record.record_status.replace(" ", "-").toLowerCase()}`}>{recordStatusLabel(record.record_status)}</span>
        <span className="muted">Versi {version}</span>
        <button type="button" onClick={() => go("#/")}>Daftar</button>
        <button type="button" onClick={() => { setError(null); setNotice(null); void load(); }}>Muat ulang</button>
      </div>
      <ErrorBanner message={error} />
      {notice && <div className="banner ok" role="status">{notice}</div>}
      <div className="layout">
        <div className="steps">
          {STEPS.map((step) => (
            <fieldset className="step" key={step.title}>
              <legend>{step.title}</legend>
              {step.fields.map((def) => (
                <FieldRow key={def.path} def={def} field={getField(record, def.path)} sources={sources} busy={busy}
                          onSet={(v) => void patch(def.path, "set", v)}
                          onConfirm={() => void patch(def.path, "confirm")}
                          onClear={() => void patch(def.path, "missing")} />
              ))}
            </fieldset>
          ))}
          {extras.length > 0 && (
            <fieldset className="step">
              <legend>Lainnya (hanya baca)</legend>
              {extras.map((r) => (
                <FieldRow key={r.label} def={{ label: r.label, path: r.label }} field={r.field} sources={sources} busy readOnly
                          onSet={() => undefined} onConfirm={() => undefined} onClear={() => undefined} />
              ))}
            </fieldset>
          )}
        </div>
        <aside className="side">
          <ConflictPanel conflicts={record.conflicts} busy={busy}
                         onResolve={(cid, value) => void write((v) => api.resolveConflict(id, cid, v, value))} />
          <ContextBox busy={busy}
                      onAdd={(text) => write((v) => api.addContext(id, v, text),
                        (r) => "Konteks ditambahkan." + (r.discarded?.length ? ` Dibuang dan tidak disimpan: ${r.discarded.join(", ")}.` : ""))} />
          <p className="muted small">Terakhir diubah {formatTime(String(record.updated_at ?? ""))}</p>
        </aside>
      </div>
    </section>
  );
}
