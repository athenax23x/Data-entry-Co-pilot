import { useEffect, useMemo, useState } from "react";
import type { MerchantRecord } from "../api";
import { STEPS } from "../layout.generated";
import { getField } from "../recordpath";
import { formatValue } from "../status";
import { toUsDate } from "../inputs";

// "Mode isi form" (M20): walk the Paykings form in its own order, one value at a time.
// "Salin & lanjut" copies the current value and moves to the next one, so the person only switches windows and pastes.
// Which fields were copied is kept in memory for this page, never the values themselves.

export interface QueueItem { step: string; label: string; path: string; value: string; sensitive: boolean }

export function fillQueue(record: MerchantRecord): { items: QueueItem[]; empty: { step: string; label: string }[] } {
  const items: QueueItem[] = [];
  const empty: { step: string; label: string }[] = [];
  for (const step of STEPS) {
    for (const def of step.fields) {
      const f = getField(record, def.path);
      if (!f) continue;
      if (f.value === null || f.value === undefined || f.value === "") empty.push({ step: step.title, label: def.label });
      else items.push({ step: step.title, label: def.label, path: def.path,
                        value: def.kind === "date" ? toUsDate(f.value) : String(f.value), sensitive: def.sensitive });
    }
  }
  return { items, empty };
}

// Progress is kept in memory only (the app never uses browser storage): it survives switching tabs and merchants,
// and is gone when the page is reloaded. Paths only, never values.
const progress = new Map<string, string[]>();
const readDone = (id: string): string[] => progress.get(id) ?? [];
const writeDone = (id: string, done: string[]): void => { progress.set(id, done); };
export const resetFillProgressForTests = () => progress.clear();

export default function FillMode({ merchantId, record }: { merchantId: string; record: MerchantRecord }) {
  const { items, empty } = useMemo(() => fillQueue(record), [record]);
  const [done, setDone] = useState<string[]>(() => readDone(merchantId));
  const [pos, setPos] = useState(() => {
    const d = new Set(readDone(merchantId));
    const i = fillQueue(record).items.findIndex((it) => !d.has(it.path));
    return i < 0 ? 0 : i;
  });
  const [copied, setCopied] = useState<"ok" | "fail" | null>(null);

  useEffect(() => { writeDone(merchantId, done); }, [merchantId, done]);
  useEffect(() => { if (pos >= items.length && items.length) setPos(items.length - 1); }, [items.length, pos]);

  const doneSet = new Set(done);
  const current = items[pos] ?? null;
  const doneCount = items.filter((it) => doneSet.has(it.path)).length;
  const finished = items.length > 0 && doneCount === items.length;

  function nextFrom(i: number, marked: Set<string>): number {
    for (let j = i + 1; j < items.length; j++) if (!marked.has(items[j].path)) return j;
    for (let j = 0; j <= i && j < items.length; j++) if (!marked.has(items[j].path)) return j;
    return i;
  }

  async function copy(i: number, advance: boolean) {
    const it = items[i];
    if (!it) return;
    let ok = true;
    try {
      await navigator.clipboard.writeText(it.value);
    } catch {
      ok = false;
    }
    setCopied(ok ? "ok" : "fail");
    window.setTimeout(() => setCopied(null), 1800);
    if (!ok) return;
    const marked = new Set(doneSet).add(it.path);
    setDone([...marked]);
    setPos(advance ? nextFrom(i, marked) : i);
  }

  if (!items.length) {
    return <p className="empty">Belum ada nilai untuk disalin. Isi merchant lewat teks atau Jembatan Claude dulu.</p>;
  }

  return (
    <div className="fill">
      <div className="fill-main">
        <div className="fill-progress" aria-label="Kemajuan">
          <span><strong>{doneCount}</strong> dari {items.length} field disalin</span>
          <div className="meter"><div style={{ width: `${(100 * doneCount) / items.length}%` }} /></div>
        </div>
        {finished ? (
          <div className="fill-card done-card" role="status">
            <h2>Semua field sudah disalin</h2>
            <p className="muted">Periksa form Paykings sekali lagi sebelum dikirim.</p>
            <button type="button" onClick={() => { setDone([]); setPos(0); }}>Ulangi dari awal</button>
          </div>
        ) : current && (
          <div className="fill-card">
            <div className="muted small">{current.step} · field {pos + 1} dari {items.length}</div>
            <div className="fill-label">{current.label}{current.sensitive && <span className="tag-sensitive">sensitif</span>}</div>
            <div className="fill-value" aria-label="Nilai saat ini">{formatValue(current.value)}</div>
            <div className="fill-actions">
              <button type="button" className="primary big" onClick={() => void copy(pos, true)}>Salin &amp; lanjut</button>
              <button type="button" onClick={() => void copy(pos, false)}>Salin saja</button>
              <button type="button" disabled={pos === 0} onClick={() => setPos(pos - 1)}>Sebelumnya</button>
              <button type="button" onClick={() => setPos(nextFrom(pos, doneSet))}>Lewati</button>
              {copied && <span className={`copied ${copied}`} role="status">{copied === "ok" ? "Tersalin, tempel di Paykings" : "Gagal menyalin"}</span>}
            </div>
            <p className="muted small">Klik “Salin &amp; lanjut”, pindah ke form Paykings, tempel (Ctrl+V), lalu kembali ke sini.</p>
          </div>
        )}
        {empty.length > 0 && (
          <details className="fill-empty">
            <summary>{empty.length} field masih kosong (isi langsung di Paykings atau lengkapi di tab Formulir)</summary>
            <ul>{empty.map((e) => <li key={e.step + e.label}>{e.label} <span className="muted small">· {e.step}</span></li>)}</ul>
          </details>
        )}
      </div>
      <ol className="fill-list" aria-label="Urutan field">
        {items.map((it, i) => (
          <li key={it.path} className={`${i === pos ? "on" : ""} ${doneSet.has(it.path) ? "ok" : ""}`}>
            <button type="button" onClick={() => setPos(i)} aria-label={`Pilih ${it.label}`}>
              <span className="tick" aria-hidden="true">{doneSet.has(it.path) ? "✓" : ""}</span>
              <span className="fl">{it.label}</span>
            </button>
          </li>
        ))}
      </ol>
    </div>
  );
}
