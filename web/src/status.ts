import { ApiError } from "./api";

export const STATUS_LABEL: Record<string, string> = {
  verified: "Terverifikasi",
  inferred: "Dugaan",
  missing: "Kosong",
  conflict: "Konflik",
  needs_review: "Perlu ditinjau",
};

export const RECORD_STATUS_LABEL: Record<string, string> = {
  Complete: "Lengkap",
  "Needs Review": "Perlu ditinjau",
  Incomplete: "Belum lengkap",
};

export const SOURCE_LABEL: Record<string, string> = {
  new_merchant: "Merchant baru",
  add_context: "Tambah konteks",
  update_field: "Diubah manual",
};

export const STALE_MESSAGE = "Data sudah berubah. Muat ulang.";

export function statusLabel(status: string): string {
  return STATUS_LABEL[status] ?? status;
}

/** CSS class for a field status: one colour each (see styles.css). Unknown values get a neutral class. */
export function statusClass(status: string): string {
  return status in STATUS_LABEL ? `st-${status.replace("_", "-")}` : "st-unknown";
}

export function recordStatusLabel(status: string): string {
  return RECORD_STATUS_LABEL[status] ?? status;
}

export function isStale(err: unknown): boolean {
  return err instanceof ApiError && err.status === 409;
}

/** What the person sees for an error. 409 gets the fixed reload text; every other server message is shown as sent. */
export function errorMessage(err: unknown): string {
  if (isStale(err)) return STALE_MESSAGE;
  if (err instanceof ApiError) {
    return err.fields.length ? `${err.message} (${err.fields.join(", ")})` : err.message;
  }
  return "Terjadi kesalahan yang tidak dikenal.";
}

export function formatValue(value: unknown): string {
  return value === null || value === undefined || value === "" ? "—" : String(value);
}

export function formatTime(iso: string, locale = "id-ID"): string {
  const d = new Date(iso);
  return Number.isNaN(d.getTime()) ? iso : d.toLocaleString(locale, { dateStyle: "medium", timeStyle: "short" });
}
