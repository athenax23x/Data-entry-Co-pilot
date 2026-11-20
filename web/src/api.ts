// The only place that talks to the server. The token lives in memory (module variable), never in storage.
export const TOKEN_PLACEHOLDER = "__MCN_TOKEN__";

export interface FieldObj {
  value: unknown;
  status: string;
  source_context: string | null;
  source_document: string | null;
  updated_at?: string;
}
export interface Candidate { value: unknown; source_context: string | null; source_document: string | null }
export interface Conflict {
  conflict_id: string;
  field_path: string;
  current_value: unknown;
  candidates: Candidate[];
  resolution: { state: string };
}
export interface Source { source_id: string; source_type: string; label: string | null; received_at: string }
export interface MerchantRecord {
  merchant_id: string;
  record_status: string;
  sources: Source[];
  conflicts: Conflict[];
  [key: string]: unknown;
}
export interface Summary {
  merchant_id: string; legal_name: string | null; entity_type: string | null;
  record_status: string; version: number; updated_at: string;
}
export interface RecordReply {
  merchant_id: string; version: number; record: MerchantRecord;
  message?: string; discarded?: string[];
}

export class ApiError extends Error {
  status: number;
  fields: string[];
  constructor(status: number, message: string, fields: string[] = []) {
    super(message);
    this.status = status;
    this.fields = fields;
  }
}

let token: string | null = null;

export function readToken(doc: Document = document): string | null {
  const value = doc.querySelector('meta[name="mcn-token"]')?.getAttribute("content") ?? "";
  return value && value !== TOKEN_PLACEHOLDER ? value : null;
}

// Guest mode (python -m merchant_notebook.api --guest): the server puts 1 here. Used only to show a banner.
export function isGuest(doc: Document = document): boolean {
  return doc.querySelector('meta[name="mcn-guest"]')?.getAttribute("content") === "1";
}

export function getToken(): string | null {
  if (token === null) token = readToken();
  return token;
}

export function setTokenForTests(value: string | null): void {
  token = value;
}

async function call<T>(method: string, path: string, body?: unknown): Promise<T> {
  const t = getToken();
  if (!t) throw new ApiError(0, "Token sesi tidak ditemukan. Buka halaman ini dari server (python -m merchant_notebook.api).");
  let res: Response;
  try {
    res = await fetch(path, {
      method,
      headers: { "X-MCN-Token": t, ...(body === undefined ? {} : { "Content-Type": "application/json" }) },
      body: body === undefined ? undefined : JSON.stringify(body),
    });
  } catch {
    throw new ApiError(0, "Tidak dapat terhubung ke server.");
  }
  let data: { detail?: unknown; fields?: unknown } | null = null;
  try {
    data = await res.json();
  } catch {
    data = null;
  }
  if (!res.ok) {
    const detail = typeof data?.detail === "string" ? data.detail : `Permintaan gagal (${res.status}).`;
    const fields = Array.isArray(data?.fields) ? (data!.fields as unknown[]).map(String) : [];
    throw new ApiError(res.status, detail, fields);
  }
  return data as T;
}

export const listMerchants = (q: string) =>
  call<{ merchants: Summary[] }>("GET", "/api/merchants" + (q.trim() ? `?q=${encodeURIComponent(q.trim())}` : ""));
export const createMerchant = (text: string) => call<RecordReply>("POST", "/api/merchants", { text });
export const getMerchant = (id: string) => call<RecordReply>("GET", `/api/merchants/${encodeURIComponent(id)}`);
export const updateField = (id: string, path: string, body: { expected_version: number; action: "set" | "confirm" | "missing"; value?: string }) =>
  call<RecordReply>("PATCH", `/api/merchants/${encodeURIComponent(id)}/fields/${encodeURIComponent(path)}`, body);
export const addContext = (id: string, expected_version: number, text: string) =>
  call<RecordReply>("POST", `/api/merchants/${encodeURIComponent(id)}/context`, { expected_version, text });
export const resolveConflict = (id: string, cid: string, expected_version: number, value: string) =>
  call<RecordReply>("POST", `/api/merchants/${encodeURIComponent(id)}/conflicts/${encodeURIComponent(cid)}/resolve`,
    { expected_version, value });

// ---- Claude bridge (M5). The texts go to the server and back; they are never kept anywhere but component state.
export interface BridgePrepared { masked_text: string; prompt: string; hidden: string[] }
export interface BridgeProposal {
  index: number; path: string; value: string | null; evidence: string; status: string;
  ambiguous: boolean; ok: boolean; reason: string | null; outcome: string | null;
}
export interface BridgeApplied extends RecordReply { changed: boolean; applied: { index: number; path: string; outcome: string }[] }

export const bridgePrepare = (text: string) => call<BridgePrepared>("POST", "/api/bridge/prepare", { text });
export const bridgePreview = (id: string, expected_version: number, answer: string, source_text: string) =>
  call<{ proposals: BridgeProposal[]; version: number }>("POST", `/api/merchants/${encodeURIComponent(id)}/bridge/preview`,
    { expected_version, answer, source_text });
export const bridgeApply = (id: string, expected_version: number, answer: string, source_text: string, accept: number[]) =>
  call<BridgeApplied>("POST", `/api/merchants/${encodeURIComponent(id)}/bridge/apply`,
    { expected_version, answer, source_text, accept });

// ---- Paykings CSV export (M10). Needs the session token header, so it is fetched here and saved as a file in the browser.
export async function fetchPaykingsCsv(merchantId: string | null, includeSensitive: boolean): Promise<Blob> {
  const t = getToken();
  if (!t) throw new ApiError(0, "Token sesi tidak ditemukan. Buka halaman ini dari server (python -m merchant_notebook.api).");
  const params = new URLSearchParams();
  if (merchantId) params.set("merchant_id", merchantId);
  if (includeSensitive) params.set("include_sensitive", "true");
  let res: Response;
  try {
    res = await fetch("/api/export/paykings.csv" + (params.size ? `?${params}` : ""), { headers: { "X-MCN-Token": t } });
  } catch {
    throw new ApiError(0, "Tidak dapat terhubung ke server.");
  }
  if (!res.ok) throw new ApiError(res.status, `Ekspor gagal (${res.status}).`);
  return res.blob();
}
