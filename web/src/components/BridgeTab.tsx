import { useState } from "react";
import * as api from "../api";
import { fieldLabel } from "../labels";
import { COPY_WARNING, errorMessage, isStale, outcomeLabel, statusLabel } from "../status";
import ErrorBanner from "./ErrorBanner";

interface Props {
  merchantId: string;
  version: number;
  /** Sends the chosen proposals; resolves true when they were stored (the workspace updates its record). */
  onApply: (answer: string, sourceText: string, accept: number[]) => Promise<boolean>;
  onStale: () => void;
}

export default function BridgeTab({ merchantId, version, onApply, onStale }: Props) {
  const [source, setSource] = useState("");
  const [prepared, setPrepared] = useState<api.BridgePrepared | null>(null);
  const [answer, setAnswer] = useState("");
  const [proposals, setProposals] = useState<api.BridgeProposal[] | null>(null);
  const [chosen, setChosen] = useState<Set<number>>(new Set());
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [info, setInfo] = useState<string | null>(null);

  async function guard<T>(work: () => Promise<T>): Promise<T | null> {
    setBusy(true);
    setError(null);
    setInfo(null);
    try {
      return await work();
    } catch (e) {
      setError(errorMessage(e));
      if (isStale(e)) onStale();
      return null;
    } finally {
      setBusy(false);
    }
  }

  const prepare = async () => {
    const r = await guard(() => api.bridgePrepare(source));
    if (r) { setPrepared(r); setProposals(null); }
  };

  async function copy() {
    if (!prepared) return;
    try {
      await navigator.clipboard.writeText(prepared.prompt);
      setInfo("Prompt disalin. Tempel di chat Claude.");
    } catch {
      setError("Tidak bisa menyalin otomatis. Pilih teks prompt di atas, lalu salin dengan Ctrl+C.");
    }
  }

  const check = async () => {
    const r = await guard(() => api.bridgePreview(merchantId, version, answer, source));
    if (r) {
      setProposals(r.proposals);
      setChosen(new Set(r.proposals.filter((p) => p.ok).map((p) => p.index)));
    }
  };

  async function apply() {
    setBusy(true);
    setError(null);
    const ok = await onApply(answer, source, [...chosen].sort((a, b) => a - b));
    setBusy(false);
    if (ok) {
      setInfo("Usulan terpilih diterapkan.");
      setProposals(null);
      setAnswer("");
    }
  }

  const toggle = (i: number) =>
    setChosen((prev) => { const n = new Set(prev); if (n.has(i)) n.delete(i); else n.add(i); return n; });

  return (
    <div className="bridge">
      <ErrorBanner message={error} />
      {info && <div className="banner ok" role="status">{info}</div>}

      <section className="panel" aria-label="Siapkan teks">
        <h2>1. Siapkan</h2>
        <p className="hint">Tempel teks sumber. Data sensitif (kartu, SSN, rekening, SIM, paspor, kata sandi) disamarkan atau dibuang sebelum disalin. Aplikasi ini tidak mengirim apa pun ke Claude: Anda yang menyalin dan menempelkannya.</p>
        <textarea aria-label="Teks sumber" rows={8} value={source} onChange={(e) => setSource(e.target.value)} placeholder="Tempel teks sumber di sini…" />
        <div className="actions">
          <button type="button" className="primary" disabled={busy || !source.trim()} onClick={() => void prepare()}>Siapkan</button>
        </div>
        {prepared && (
          <>
            <p className="hint">
              {prepared.hidden.length ? `Disamarkan atau dibuang: ${prepared.hidden.join(", ")}.` : "Tidak ada data sensitif yang terdeteksi."}
            </p>
            <div className="banner warn" role="note">{COPY_WARNING}</div>
            <textarea aria-label="Prompt untuk Claude" rows={10} readOnly value={prepared.prompt} />
            <div className="actions">
              <button type="button" className="primary" onClick={() => void copy()}>Salin</button>
            </div>
          </>
        )}
      </section>

      <section className="panel" aria-label="Tempel jawaban">
        <h2>2. Tempel jawaban Claude</h2>
        <textarea aria-label="Jawaban JSON dari Claude" rows={8} value={answer} onChange={(e) => setAnswer(e.target.value)} placeholder='{"candidates": [...]}' />
        <div className="actions">
          <button type="button" className="primary" disabled={busy || !answer.trim() || !source.trim()} onClick={() => void check()}>Periksa</button>
        </div>
      </section>

      {proposals && (
        <section className="panel" aria-label="Usulan">
          <h2>3. Usulan ({proposals.length})</h2>
          {proposals.length === 0 && <p className="muted">Claude tidak mengusulkan apa pun.</p>}
          {proposals.length > 0 && (
            <div className="table-wrap">
              <table>
                <thead><tr><th>Pilih</th><th>Path</th><th>Nilai</th><th>Bukti</th><th>Pemeriksaan</th></tr></thead>
                <tbody>
                  {proposals.map((p) => (
                    <tr key={p.index} className={p.ok ? "" : "rejected"}>
                      <td><input type="checkbox" aria-label={`Pilih usulan ${p.index + 1}`} disabled={!p.ok} checked={chosen.has(p.index)} onChange={() => toggle(p.index)} /></td>
                      <td>{fieldLabel(p.path)}<div className="muted small">{p.path}</div></td>
                      <td>{p.value ?? "—"}</td>
                      <td className="wrap">{p.evidence || "—"}</td>
                      <td className="wrap">
                        {p.ok
                          ? <>OK · {outcomeLabel(p.outcome)}{p.status === "needs_review" && <> · <strong>{statusLabel("needs_review")}</strong>{p.ambiguous ? " (tanggal ambigu)" : ""}</>}</>
                          : <span className="bad">Ditolak: {p.reason}</span>}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
          <div className="actions">
            <button type="button" className="primary" disabled={busy || chosen.size === 0} onClick={() => void apply()}>Terapkan ({chosen.size})</button>
          </div>
        </section>
      )}
    </div>
  );
}
