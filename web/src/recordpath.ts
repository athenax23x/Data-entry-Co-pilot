import type { FieldObj, MerchantRecord } from "./api";

/** 'personal_information.owners[0].ssn' -> ['personal_information','owners',0,'ssn'] */
export function parsePath(path: string): (string | number)[] {
  const out: (string | number)[] = [];
  for (const part of path.split(".")) {
    const m = /^(\w+)\[(\d+)\]$/.exec(part);
    if (m) out.push(m[1], Number(m[2]));
    else out.push(part);
  }
  return out;
}

export function getField(record: MerchantRecord, path: string): FieldObj | null {
  let node: unknown = record;
  for (const key of parsePath(path)) {
    if (node === null || typeof node !== "object") return null;
    node = (node as Record<string | number, unknown>)[key];
  }
  const f = node as FieldObj | undefined;
  return f && typeof f === "object" && "status" in f ? f : null;
}

/** A conflict's field_path ('/personal_information/owners/0/ssn') in the dotted form used by the form. */
export function pointerToPath(pointer: string): string {
  let out = "";
  for (const part of pointer.replace(/^\//, "").split("/")) {
    out += /^\d+$/.test(part) ? `[${part}]` : (out ? "." : "") + part;
  }
  return out;
}

export interface ExtraRow { label: string; field: FieldObj }

const isField = (v: unknown): v is FieldObj => !!v && typeof v === "object" && "status" in (v as object) && "value" in (v as object);

/** Fields that are in the record but not in the Paykings form: shown read-only under "Lainnya". */
export function extraRows(record: MerchantRecord): ExtraRow[] {
  const rows: ExtraRow[] = [];
  const add = (label: string, v: unknown) => { if (isField(v)) rows.push({ label, field: v }); };
  const bi = record.business_information as Record<string, unknown> | undefined;
  add("State of Formation", bi?.state_of_formation);
  const owners = ((record.personal_information as { owners?: Record<string, unknown>[] } | undefined)?.owners) ?? [];
  owners.forEach((o, i) => {
    if (i === 0) {
      add("Owner 1 SSN Last 4", o.ssn_last4);
      return;
    }
    for (const [k, v] of Object.entries(o)) add(`Owner ${i + 1} ${k}`, v);
  });
  const ps = record.products_and_services as { description?: unknown; items?: unknown[] } | undefined;
  add("Products and Services", ps?.description);
  (ps?.items ?? []).forEach((it, i) => add(`Product / Service ${i + 1}`, it));
  for (const [k, v] of Object.entries((record.custom_fields as Record<string, unknown> | undefined) ?? {})) add(`Custom: ${k}`, v);
  return rows;
}
