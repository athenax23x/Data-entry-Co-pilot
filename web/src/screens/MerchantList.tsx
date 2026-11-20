import { useCallback, useEffect, useState } from "react";
import { go } from "../App";
import * as api from "../api";
import type { Summary } from "../api";
import ExportButton from "../components/ExportButton";
import ErrorBanner from "../components/ErrorBanner";
import { giveBridgeText } from "../handoff";
import { errorMessage, formatTime, formatValue, recordStatusLabel } from "../status";

type Filter = "all" | "Incomplete" | "Needs Review" | "Complete";
const FILTERS: { key: Filter; label: string }[] = [
  { key: "all", label: "Semua" },
  { key: "Incomplete", label: "Belum lengkap" },
  { key: "Needs Review", label: "Perlu ditinjau" },
  { key: "Complete", label: "Lengkap" },
];

export function progressText(r: Summary): string {
  if (r.filled == null || r.total == null) return "—";
  return `${r.filled}/${r.total}`;
}

export default function MerchantList() {
  const [q, setQ] = useState("");
  const [archived, setArchived] = useState(false);
  const [filter, setFilter] = useState<Filter>("all");
  const [rows, setRows] = useState<Summary[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [paste, setPaste] = useState("");
  const [confirmDelete, setConfirmDelete] = useState<string | null>(null);
  const [tick, setTick] = useState(0);
  const reload = useCallback(() => setTick((t) => t + 1), []);

  useEffect(() => {
    let live = true;
    const timer = setTimeout(() => {
      api.listMerchants(q, archived)
        .then((r) => { if (live) { setRows(r.merchants); setError(null); } })
        .catch((e) => { if (live) setError(errorMessage(e)); });
    }, 200);
    return () => { live = false; clearTimeout(timer); };
  }, [q, archived, tick]);

  async function act(work: () => Promise<unknown>, ok: string) {
    setBusy(true);
    setError(null);
    setNotice(null);
    try {
      await work();
      setNotice(ok);
      reload();
    } catch (e) {
      setError(errorMessage(e));
    } finally {
      setBusy(false);
      setConfirmDelete(null);
    }
  }

  async function quick(mode: "local" | "claude") {
    setBusy(true);
    setError(null);
    try {
      if (mode === "local") {
        const r = await api.createMerchant(paste);
        go(`#/m/${r.merchant_id}`);
      } else {
        const r = await api.createMerchant("");
        giveBridgeText(r.merchant_id, paste);
        go(`#/m/${r.merchant_id}`);
      }
    } catch (e) {
      setError(errorMessage(e));
      setBusy(false);
    }
  }

  const shown = (rows ?? []).filter((r) => filter === "all" || r.record_status === filter);
  const count = (f: Filter) => (rows ?? []).filter((r) => f === "all" || r.record_status === f).length;

  return (
    <section>
      <div className="bar">
        <h1>{archived ? "Arsip merchant" : "Daftar merchant"}</h1>
        <input type="search" aria-label="Cari merchant" placeholder="Cari nama usaha atau ID" value={q}
               onChange={(e) => setQ(e.target.value)} />
        <button type="button" className="primary" onClick={() => go("#/baru")}>Merchant baru</button>
        <button type="button" onClick={() => { setArchived(!archived); setFilter("all"); setRows(null); setNotice(null); }}>
          {archived ? "Kembali ke daftar" : "Lihat arsip"}
        </button>
        {!archived && <ExportButton />}
      </div>

      {!archived && (
        <div className="quick">
          <textarea aria-label="Tempel cepat" rows={3} value={paste} placeholder="Tempel cepat: tempel teks merchant di sini…"
                    onChange={(e) => setPaste(e.target.value)} />
          <div className="quick-actions">
            <button type="button" className="primary" disabled={busy || !paste.trim()} onClick={() => void quick("claude")}
                    title="Buat merchant, lalu buka Jembatan Claude dengan prompt yang sudah siap disalin">
              Buat &amp; siapkan prompt Claude
            </button>
            <button type="button" disabled={busy || !paste.trim()} onClick={() => void quick("local")}
                    title="Buat merchant dan isi otomatis di laptop ini, tanpa Claude">
              Buat &amp; isi otomatis
            </button>
          </div>
        </div>
      )}

      <ErrorBanner message={error} />
      {notice && <div className="banner ok" role="status">{notice}</div>}

      {!archived && rows && rows.length > 0 && (
        <div className="filters" role="group" aria-label="Filter status">
          {FILTERS.map((f) => (
            <button type="button" key={f.key} className={filter === f.key ? "on" : ""} aria-pressed={filter === f.key}
                    onClick={() => setFilter(f.key)}>
              {f.label} <span className="muted">({count(f.key)})</span>
            </button>
          ))}
        </div>
      )}

      {rows && shown.length === 0 && (
        <p className="empty">
          {archived ? "Arsip kosong." : q.trim() ? "Tidak ada merchant yang cocok." : rows.length ? "Tidak ada merchant dengan status ini." : "Belum ada merchant. Tempel teks di atas atau klik “Merchant baru”."}
        </p>
      )}
      {rows && shown.length > 0 && (
        <div className="table-wrap">
          <table>
            <thead>
              <tr><th>ID</th><th>Nama usaha</th><th>Tipe entitas</th><th>Status</th><th>Terisi</th><th>Konflik</th><th>Terakhir diubah</th><th>Aksi</th></tr>
            </thead>
            <tbody>
              {shown.map((r) => (
                <tr key={r.merchant_id}>
                  <td><a href={`#/m/${r.merchant_id}`}>{r.merchant_id}</a></td>
                  <td>{formatValue(r.legal_name)}</td>
                  <td>{formatValue(r.entity_type)}</td>
                  <td><span className={`rec rec-${r.record_status.replace(" ", "-").toLowerCase()}`}>{recordStatusLabel(r.record_status)}</span></td>
                  <td>
                    <span className="prog" title="Field formulir Paykings yang sudah terisi">
                      {progressText(r)}
                      {r.filled != null && r.total ? <span className="meter mini"><span style={{ width: `${(100 * r.filled) / r.total}%` }} /></span> : null}
                    </span>
                  </td>
                  <td>{r.open_conflicts ? <span className="rec rec-needs-review">{r.open_conflicts}</span> : <span className="muted">0</span>}</td>
                  <td>{formatTime(r.updated_at)}</td>
                  <td className="row-actions">
                    {!archived ? (
                      <>
                        <button type="button" disabled={busy} aria-label={`Duplikat ${r.merchant_id}`}
                                onClick={() => void act(() => api.duplicateMerchant(r.merchant_id), `${r.merchant_id} diduplikat.`)}>Duplikat</button>
                        <button type="button" disabled={busy} aria-label={`Arsipkan ${r.merchant_id}`}
                                onClick={() => void act(() => api.archiveMerchant(r.merchant_id, true), `${r.merchant_id} diarsipkan. Buka “Lihat arsip” untuk memulihkan.`)}>Arsipkan</button>
                      </>
                    ) : confirmDelete === r.merchant_id ? (
                      <>
                        <span className="danger-text">Hapus permanen?</span>
                        <button type="button" className="danger" disabled={busy} aria-label={`Ya, hapus ${r.merchant_id}`}
                                onClick={() => void act(() => api.deleteMerchant(r.merchant_id, r.version), `${r.merchant_id} dihapus.`)}>Ya, hapus</button>
                        <button type="button" onClick={() => setConfirmDelete(null)}>Batal</button>
                      </>
                    ) : (
                      <>
                        <button type="button" disabled={busy} aria-label={`Pulihkan ${r.merchant_id}`}
                                onClick={() => void act(() => api.archiveMerchant(r.merchant_id, false), `${r.merchant_id} dipulihkan.`)}>Pulihkan</button>
                        <button type="button" disabled={busy} aria-label={`Hapus ${r.merchant_id}`}
                                onClick={() => setConfirmDelete(r.merchant_id)}>Hapus…</button>
                      </>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      {archived && <p className="muted small">Merchant di arsip tidak ikut di daftar dan di CSV “semua merchant”. Hapus permanen tidak bisa dibatalkan dari aplikasi; backup otomatis dari jalankan.bat sebelumnya masih menyimpannya.</p>}
      {!rows && !error && <p className="empty">Memuat…</p>}
    </section>
  );
}
