import { useEffect, useState } from "react";
import { go } from "../App";
import { listMerchants, type Summary } from "../api";
import ErrorBanner from "../components/ErrorBanner";
import { errorMessage, formatTime, formatValue, recordStatusLabel } from "../status";

export default function MerchantList() {
  const [q, setQ] = useState("");
  const [rows, setRows] = useState<Summary[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let live = true;
    const timer = setTimeout(() => {
      listMerchants(q)
        .then((r) => { if (live) { setRows(r.merchants); setError(null); } })
        .catch((e) => { if (live) setError(errorMessage(e)); });
    }, 200);
    return () => { live = false; clearTimeout(timer); };
  }, [q]);

  return (
    <section>
      <div className="bar">
        <h1>Daftar merchant</h1>
        <input type="search" aria-label="Cari merchant" placeholder="Cari nama usaha atau ID" value={q}
               onChange={(e) => setQ(e.target.value)} />
        <button type="button" className="primary" onClick={() => go("#/baru")}>Merchant baru</button>
      </div>
      <ErrorBanner message={error} />
      {rows && rows.length === 0 && <p className="empty">{q.trim() ? "Tidak ada merchant yang cocok." : "Belum ada merchant. Klik “Merchant baru”."}</p>}
      {rows && rows.length > 0 && (
        <div className="table-wrap">
          <table>
            <thead>
              <tr><th>ID</th><th>Nama usaha</th><th>Tipe entitas</th><th>Status</th><th>Versi</th><th>Terakhir diubah</th></tr>
            </thead>
            <tbody>
              {rows.map((r) => (
                <tr key={r.merchant_id}>
                  <td><a href={`#/m/${r.merchant_id}`}>{r.merchant_id}</a></td>
                  <td>{formatValue(r.legal_name)}</td>
                  <td>{formatValue(r.entity_type)}</td>
                  <td><span className={`rec rec-${r.record_status.replace(" ", "-").toLowerCase()}`}>{recordStatusLabel(r.record_status)}</span></td>
                  <td>{r.version}</td>
                  <td>{formatTime(r.updated_at)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      {!rows && !error && <p className="empty">Memuat…</p>}
    </section>
  );
}
