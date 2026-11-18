import { useState } from "react";
import { fetchPaykingsCsv } from "../api";
import { errorMessage } from "../status";

interface Props { merchantId?: string }

// Saves the Paykings 70-column CSV. Sensitive columns are blank unless the box is ticked (a CSV file is not encrypted).
export default function ExportButton({ merchantId }: Props) {
  const [sensitive, setSensitive] = useState(false);
  const [busy, setBusy] = useState(false);
  const [info, setInfo] = useState<string | null>(null);

  async function run() {
    setBusy(true);
    setInfo(null);
    try {
      const blob = await fetchPaykingsCsv(merchantId ?? null, sensitive);
      const name = `${merchantId ?? "all-merchants"}${sensitive ? "-with-sensitive" : ""}.csv`;
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = name;
      document.body.appendChild(a);
      a.click();
      a.remove();
      URL.revokeObjectURL(url);
      setInfo(`Tersimpan: ${name}`);
    } catch (e) {
      setInfo(errorMessage(e));
    } finally {
      setBusy(false);
    }
  }

  return (
    <span className="export">
      <button type="button" disabled={busy} onClick={() => void run()}>Unduh CSV Paykings</button>
      <label className="small">
        <input type="checkbox" checked={sensitive} onChange={(e) => setSensitive(e.target.checked)} />
        {" "}Sertakan data sensitif (file tidak terenkripsi)
      </label>
      {info && <span className="small" role="status">{info}</span>}
    </span>
  );
}
