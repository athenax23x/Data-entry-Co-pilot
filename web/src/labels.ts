import { STEPS } from "./layout.generated";

const LABELS = new Map(STEPS.flatMap((s) => s.fields.map((f) => [f.path, f.label] as const)));

/** The Paykings column name of a field path, or the path itself when it is not a form field. */
export const fieldLabel = (path: string): string => LABELS.get(path) ?? path;
