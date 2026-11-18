import { useState } from "react";
import { go } from "../App";
import { createMerchant } from "../api";
import ErrorBanner from "../components/ErrorBanner";
import { errorMessage } from "../status";

export default function NewMerchant() {
  const [text, setText] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function create() {
    setBusy(true);
    setError(null);
    try {
      const r = await createMerchant(text);
      go(`#/m/${r.merchant_id}`);
    } catch (e) {
      setError(errorMessage(e));
      setBusy(false);
    }
  }

  return (
    <section>
      <div className="bar">
        <h1>Merchant baru</h1>
        <button type="button" onClick={() => go("#/")}>Kembali</button>
      </div>
      <p className="hint">Tempel teks mentah tentang merchant (email, catatan, hasil chat). Nilai yang jelas akan diisi otomatis; sisanya bisa diubah di workspace. Nomor kartu, kode keamanan, dan kata sandi dibuang dan tidak disimpan.</p>
      <ErrorBanner message={error} />
      <textarea className="big" aria-label="Teks mentah merchant" rows={14} value={text}
                onChange={(e) => setText(e.target.value)} placeholder="Tempel teks di sini…" />
      <div className="actions">
        <button type="button" className="primary" disabled={busy} onClick={create}>
          {busy ? "Membuat…" : text.trim() ? "Buat merchant" : "Buat merchant kosong"}
        </button>
      </div>
    </section>
  );
}
