import { useEffect, useState } from "react";
import * as api from "../api";
import { errorMessage } from "../status";
import ErrorBanner from "./ErrorBanner";

// "Cek & minta info" tab (M23-M25): checks before the Paykings form, the message asking the merchant for what is missing,
// and the work stage. Reloaded whenever the record version changes.

export default function ReviewTab({ merchantId, version, onCount }: {
  merchantId: string; version: number; onCount?: (errors: number) => void;
}) {
  const [data, setData] = useState<api.Review | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [copied, setCopied] = useState<"ok" | "fail" | null>(null);
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    let live = true;
    api.getReview(merchantId)
      .then((r) => {
        if (!live) return;
        if (!Array.isArray(r?.checks) || !Array.isArray(r?.missing)) { setError("Jawaban server tidak dikenali."); return; }
        setData(r);
        setError(null);
        onCount?.(r.checks.filter((c) => c.level === "error").length);
      })
      .catch((e) => { if (live) setError(errorMessage(e)); });
    return () => { live = false; };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [merchantId, version]);

  async function copy() {
    if (!data) return;
    try {
      await navigator.clipboard.writeText(data.message);
      setCopied("ok");
    } catch {
      setCopied("fail");
    }
    window.setTimeout(() => setCopied(null), 1800);
  }

  async function stage(s: api.Stage) {
    setSaving(true);
    try {
      await api.setStage(merchantId, s);
      setData((d) => (d ? { ...d, stage: s } : d));
    } catch (e) {
      setError(errorMessage(e));
    } finally {
      setSaving(false);
    }
  }

  if (!data) return error ? <ErrorBanner message={error} /> : <p className="empty">Memuat…</p>;
  const errors = data.checks.filter((c) => c.level === "error");
  const warns = data.checks.filter((c) => c.level !== "error");

  return (
    <div className="review">
      <ErrorBanner message={error} />
      <div className="review-col">
        <section className="fill-card">
          <h2>Tahap kerja</h2>
          <select aria-label="Tahap kerja" value={data.stage} disabled={saving} onChange={(e) => void stage(e.target.value as api.Stage)}>
            {api.STAGES.map((s) => <option key={s.key} value={s.key}>{s.label}</option>)}
          </select>
          <p className="muted small">Hanya untuk catatan Anda; tidak ikut ke CSV.</p>
        </section>
        <section className="fill-card">
          <h2>Pemeriksaan sebelum kirim</h2>
          {data.checks.length === 0 ? (
            <p className="ok-text" role="status">Tidak ada masalah yang ditemukan.</p>
          ) : (
            <ul className="checks">
              {[...errors, ...warns].map((c) => (
                <li key={c.code} className={c.level === "error" ? "chk-error" : "chk-warn"}>
                  <span className="chk-tag">{c.level === "error" ? "Perbaiki" : "Periksa"}</span>
                  <span>{c.message}{c.fields.length > 0 && <span className="muted small"> · {c.fields.join(", ")}</span>}</span>
                </li>
              ))}
            </ul>
          )}
          <p className="muted small">Pemeriksaan otomatis dari aturan umum, bukan keputusan Paykings.</p>
        </section>
      </div>
      <section className="fill-card review-col">
        <h2>Minta info yang kurang ke merchant</h2>
        {data.missing.length === 0 ? (
          <p className="ok-text">Semua field yang perlu ditanyakan sudah terisi.</p>
        ) : (
          <p className="muted">{data.missing.length} hal masih kosong. Salin pesan ini (bahasa Inggris) dan kirim ke merchant.</p>
        )}
        <textarea aria-label="Pesan untuk merchant" className="big" rows={16} readOnly value={data.message} />
        <div className="fill-actions">
          <button type="button" className="primary" onClick={() => void copy()}>Salin pesan</button>
          {data.missing.length > 0 && data.stage === "baru" && (
            <button type="button" disabled={saving} onClick={() => void stage("menunggu_info")}>Tandai “Menunggu info merchant”</button>
          )}
          {copied && <span className={`copied ${copied}`} role="status">{copied === "ok" ? "Pesan disalin" : "Gagal menyalin"}</span>}
        </div>
      </section>
    </div>
  );
}
