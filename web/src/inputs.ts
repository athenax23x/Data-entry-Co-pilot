// Typed inputs (M29). Dates and number-only fields accept digits only and are formatted while typing, so a value
// like "451dfas" cannot be entered. The server checks every value again (normalize.py); this only helps typing.
import type { FieldKind } from "./layout.generated";

const digits = (s: string, max: number) => s.replace(/\D/g, "").slice(0, max);

/** Keeps the digits (at most 8) and puts the slashes in: "0315" -> "03/15", "03152019" -> "03/15/2019". */
export function maskDateInput(raw: string): string {
  const d = digits(raw, 8);
  if (d.length <= 2) return d;
  if (d.length <= 4) return `${d.slice(0, 2)}/${d.slice(2)}`;
  return `${d.slice(0, 2)}/${d.slice(2, 4)}/${d.slice(4)}`;
}

/** True for a full, real calendar date MM/DD/YYYY between 1900 and 2200. */
export function isCompleteDate(s: string): boolean {
  const m = /^(\d{2})\/(\d{2})\/(\d{4})$/.exec(s);
  if (!m) return false;
  const [mm, dd, yy] = [Number(m[1]), Number(m[2]), Number(m[3])];
  if (yy < 1900 || yy > 2200 || mm < 1 || mm > 12 || dd < 1) return false;
  return dd <= new Date(yy, mm, 0).getDate();
}

/** A stored date (YYYY-MM-DD or MM/DD/YYYY) as MM/DD/YYYY, the format of a US driver license. */
export function toUsDate(value: unknown): string {
  const s = value === null || value === undefined ? "" : String(value);
  const iso = /^(\d{4})-(\d{2})-(\d{2})$/.exec(s);
  return iso ? `${iso[2]}/${iso[3]}/${iso[1]}` : s;
}

function maskPhone(raw: string): string {
  let d = raw.replace(/\D/g, "");
  if (d.length === 11 && d[0] === "1") d = d.slice(1);           // a pasted +1 country code
  d = d.slice(0, 10);
  if (d.length <= 3) return d;
  if (d.length <= 6) return `(${d.slice(0, 3)}) ${d.slice(3)}`;
  return `(${d.slice(0, 3)}) ${d.slice(3, 6)}-${d.slice(6)}`;
}

function maskDecimal(raw: string, maxInt: number): string {
  const clean = raw.replace(/[^\d.]/g, "");
  const [int, ...rest] = clean.split(".");
  const dec = rest.join("").slice(0, 2);
  return int.slice(0, maxInt) + (clean.includes(".") ? `.${dec}` : "");
}

export interface InputRule { mask: (raw: string) => string; ok: (s: string) => boolean; placeholder: string; hint: string }

const RULES: Partial<Record<FieldKind, InputRule>> = {
  date: { mask: maskDateInput, ok: isCompleteDate, placeholder: "MM/DD/YYYY", hint: "Format MM/DD/YYYY, tanggal harus ada di kalender" },
  phone: { mask: maskPhone, ok: (s) => /^\([2-9]\d{2}\) \d{3}-\d{4}$/.test(s), placeholder: "(555) 010-0187", hint: "10 angka nomor telepon AS" },
  zip: {
    mask: (r) => { const d = digits(r, 9); return d.length > 5 ? `${d.slice(0, 5)}-${d.slice(5)}` : d; },
    ok: (s) => /^\d{5}(-\d{4})?$/.test(s), placeholder: "12345", hint: "5 angka (atau 9 angka ZIP+4)",
  },
  ein: {
    mask: (r) => { const d = digits(r, 9); return d.length > 2 ? `${d.slice(0, 2)}-${d.slice(2)}` : d; },
    ok: (s) => /^\d{2}-\d{7}$/.test(s), placeholder: "12-3456789", hint: "9 angka EIN",
  },
  routing: { mask: (r) => digits(r, 9), ok: (s) => /^\d{9}$/.test(s), placeholder: "9 angka", hint: "9 angka routing number" },
  ssn: { mask: (r) => digits(r, 9), ok: (s) => /^\d{9}$/.test(s), placeholder: "9 angka", hint: "9 angka SSN" },
  account: { mask: (r) => digits(r, 17), ok: (s) => /^\d{4,17}$/.test(s), placeholder: "4–17 angka", hint: "4 sampai 17 angka" },
  percent: { mask: (r) => maskDecimal(r, 3), ok: (s) => /^\d+(\.\d+)?$/.test(s) && Number(s) <= 100, placeholder: "0–100", hint: "Angka 0 sampai 100" },
  amount: { mask: (r) => maskDecimal(r, 12), ok: (s) => /^\d+(\.\d{1,2})?$/.test(s), placeholder: "USD, mis. 25000", hint: "Angka dalam dolar" },
};

export const ruleFor = (kind: FieldKind | undefined): InputRule | null => (kind ? RULES[kind] ?? null : null);

/** The value as it is put into the edit box: dates as MM/DD/YYYY, phone numbers as (555) 010-0187. */
export function draftFor(kind: FieldKind | undefined, value: unknown): string {
  const s = value === null || value === undefined ? "" : String(value);
  const rule = ruleFor(kind);
  if (kind === "date") return toUsDate(s);
  return rule ? rule.mask(kind === "phone" ? s.replace(/^\+1\s*/, "") : s) : s;
}
