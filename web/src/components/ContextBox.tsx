import { useState } from "react";

export default function ContextBox({ busy, onAdd }: { busy: boolean; onAdd: (text: string) => Promise<boolean> }) {
  const [text, setText] = useState("");
  async function submit() {
    if (await onAdd(text)) setText("");
  }
  return (
    <section className="panel" aria-label="Tambah konteks">
      <h2>Tambah konteks</h2>
      <p className="hint">Tempel teks tambahan. Nilai yang berbeda dari yang sudah ada dicatat sebagai konflik, bukan menimpa.</p>
      <textarea aria-label="Teks konteks" rows={5} value={text} onChange={(e) => setText(e.target.value)} placeholder="Tempel teks di sini…" />
      <div className="actions">
        <button type="button" className="primary" disabled={busy || !text.trim()} onClick={submit}>Tambahkan</button>
      </div>
    </section>
  );
}
