import { Fragment, useCallback, useEffect, useState } from "react";
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
  const [stageFilter, setStageFilter] = useState<api.Stage | "all">("all");
  const [appFilter, setAppFilter] = useState<api.AppStatus | "all">("all");
  const [addFor, setAddFor] = useState<string | null>(null);
  const [addText, setAddText] = useState("");
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

  async function addInfo(r: Summary, mode: "local" | "claude") {
    if (mode === "claude") {
      giveBridgeText(r.merchant_id, addText);
      go(`#/m/${r.merchant_id}`);
      return;
    }
    await act(() => api.addContext(r.merchant_id, r.version, addText), `Info ditambahkan ke ${r.merchant_id}.`);
    setAddFor(null);
    setAddText("");
  }

  async function changeApp(r: Summary, app_status: api.AppStatus) {
    setRows((old) => old && old.map((x) => (x.merchant_id === r.merchant_id ? { ...x, app_status } : x)));
    try {
      await api.setAppStatus(r.merchant_id, app_status);
    } catch (e) {
      setError(errorMessage(e));
      reload();
    }
  }

  async function changeStage(r: Summary, stage: api.Stage) {
    setRows((old) => old && old.map((x) => (x.merchant_id === r.merchant_id ? { ...x, stage } : x)));
    try {
      await api.setStage(r.merchant_id, stage);
    } catch (e) {
      setError(errorMessage(e));
      reload();
    }
  }

  const shown = (rows ?? []).filter((r) => (filter === "all" || r.record_status === filter)
    && (stageFilter === "all" || (r.stage ?? "baru") === stageFilter)
    && (appFilter === "all" || (r.app_status ?? "no_info") === appFilter));
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
          <select aria-label="Filter tahap kerja" className="stage-select" value={stageFilter}
                  onChange={(e) => setStageFilter(e.target.value as api.Stage | "all")}>
            <option value="all">Semua tahap</option>
            {api.STAGES.map((s) => <option key={s.key} value={s.key}>{s.label}</option>)}
          </select>
          <select aria-label="Filter status aplikasi" className="stage-select" value={appFilter}
                  onChange={(e) => setAppFilter(e.target.value as api.AppStatus | "all")}>
            <option value="all">Semua status aplikasi</option>
            {api.APP_STATUSES.map((s) => <option key={s.key} value={s.key}>{s.label} ({(rows ?? []).filter((r) => (r.app_status ?? "no_info") === s.key).length})</option>)}
          </select>
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
              <tr><th>ID</th><th>Nama usaha</th><th>Aplikasi</th><th>Tahap</th><th>Terisi</th><th>Cek</th><th>Aksi</th></tr>
            </thead>
            <tbody>
              {shown.map((r) => (
                <Fragment key={r.merchant_id}>
                <tr>
                  <td><a href={`#/m/${r.merchant_id}`}>{r.merchant_id}</a></td>
                  <td className="name-cell">
                    <div>{formatValue(r.legal_name)}</div>
                    <div className="sub">
                      <span className={`rec rec-${r.record_status.replace(" ", "-").toLowerCase()}`}>{recordStatusLabel(r.record_status)}</span>
                      <span className="muted small"> · {formatTime(r.updated_at)}</span>
                    </div>
                  </td>
                  <td>
                    <select aria-label={`Status aplikasi ${r.merchant_id}`} className={`stage-select app-${r.app_status ?? "no_info"}`}
                            value={r.app_status ?? "no_info"} disabled={archived}
                            onChange={(e) => void changeApp(r, e.target.value as api.AppStatus)}>
                      {api.APP_STATUSES.map((s) => <option key={s.key} value={s.key}>{s.label}</option>)}
                    </select>
                  </td>
                  <td>
                    <select aria-label={`Tahap ${r.merchant_id}`} className="stage-select" value={r.stage ?? "baru"} disabled={archived}
                            onChange={(e) => void changeStage(r, e.target.value as api.Stage)}>
                      {api.STAGES.map((s) => <option key={s.key} value={s.key}>{s.label}</option>)}
                    </select>
                  </td>
                  <td>
                    <span className="prog" title="Field formulir Paykings yang sudah terisi">
                      {progressText(r)}
                      {r.filled != null && r.total ? <span className="meter mini"><span style={{ width: `${(100 * r.filled) / r.total}%` }} /></span> : null}
                    </span>
                  </td>
                  <td title="Hasil tab Cek & minta info: perlu diperbaiki / perlu diperiksa">
                    {r.errors ? <span className="chk-count err">{r.errors} perbaiki</span> : null}
                    {r.warnings ? <span className="chk-count warn">{r.warnings} periksa</span> : null}
                    {!r.errors && !r.warnings && r.errors != null ? <span className="muted">OK</span> : null}
                  </td>
                  <td className="row-actions">
                    {!archived ? (
                      <>
                        <button type="button" disabled={busy} aria-label={`Tambah info ${r.merchant_id}`}
                                onClick={() => { setAddFor(addFor === r.merchant_id ? null : r.merchant_id); setAddText(""); }}>Tambah info</button>
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
                {addFor === r.merchant_id && !archived && (
                  <tr className="addinfo">
                    <td colSpan={7}>
                      <textarea aria-label={`Info tambahan ${r.merchant_id}`} rows={3} value={addText} autoFocus
                                placeholder="Tempel balasan atau info baru dari merchant…" onChange={(e) => setAddText(e.target.value)} />
                      <div className="fill-actions">
                        <button type="button" className="primary" disabled={busy || !addText.trim()} onClick={() => void addInfo(r, "claude")}>
                          Siapkan prompt Claude
                        </button>
                        <button type="button" disabled={busy || !addText.trim()} onClick={() => void addInfo(r, "local")}>Isi otomatis</button>
                        <button type="button" onClick={() => setAddFor(null)}>Batal</button>
                        <span className="muted small">Hanya mengisi yang kosong; nilai yang berbeda menjadi konflik, tidak menimpa.</span>
                      </div>
                    </td>
                  </tr>
                )}
                </Fragment>
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
