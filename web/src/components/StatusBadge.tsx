import { statusClass, statusLabel } from "../status";

export default function StatusBadge({ status }: { status: string }) {
  return <span className={`badge ${statusClass(status)}`}>{statusLabel(status)}</span>;
}
