import { cleanup, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { setTokenForTests } from "./api";
import Workspace from "./screens/Workspace";
import { STEPS } from "./layout.generated";

const f = (value: unknown, status = "verified") => ({ value, status, source_context: "ctx", source_document: "SRC-001" });

function record(version = 1, phone: unknown = "+1 (555) 010-0187") {
  const sections: Record<string, Record<string, unknown>> = {};
  for (const step of STEPS) for (const fd of step.fields) {
    if (fd.path.includes("owners[0]")) continue;
    const [a, b] = fd.path.split(".");
    if (b) (sections[a] ??= {})[b] = f(null, "missing");
    else sections[a] = f(null, "missing") as never;
  }
  (sections.contact_information as Record<string, unknown>).phone = f(phone);
  const owner: Record<string, unknown> = {};
  for (const fd of STEPS[6].fields) owner[fd.path.split(".").pop()!] = f(null, "missing");
  owner.ssn = f("123456789");
  return {
    merchant_id: "MCN-20261118-001", record_status: "Incomplete", sources: [{ source_id: "SRC-001", source_type: "new_merchant", label: null, received_at: "x" }],
    conflicts: [], updated_at: "2026-11-18T10:00:00Z", ...sections, personal_information: { owners: [owner] }, version,
  };
}

const phoneRow = (c: HTMLElement) => within(c.querySelector('[data-path="contact_information.phone"]') as HTMLElement);
const json = (status: number, body: unknown) => Promise.resolve(new Response(JSON.stringify(body), { status }));

describe("Workspace", () => {
  beforeEach(() => setTokenForTests("tok"));
  afterEach(() => { cleanup(); vi.restoreAllMocks(); setTokenForTests(null); });

  it("shows values in full, with the status and the source", async () => {
    vi.spyOn(globalThis, "fetch").mockImplementation(() => json(200, { merchant_id: "MCN-20261118-001", version: 1, record: record() }));
    render(<Workspace id="MCN-20261118-001" />);
    expect(await screen.findByText("123456789")).toBeTruthy();
    expect(screen.getAllByText("Terverifikasi").length).toBeGreaterThan(0);
    expect(screen.getAllByText(/Merchant baru · SRC-001 · ctx/).length).toBeGreaterThan(0);
  });

  it("sends the loaded version; on 409 it shows the reload message and loads the record again", async () => {
    let reads = 0;
    const calls: { method: string; body?: string }[] = [];
    vi.spyOn(globalThis, "fetch").mockImplementation((_url, init) => {
      const method = (init as RequestInit).method ?? "GET";
      calls.push({ method, body: (init as RequestInit).body as string | undefined });
      if (method === "GET") { reads += 1; return json(200, { merchant_id: "MCN-20261118-001", version: reads === 1 ? 1 : 5, record: record(reads === 1 ? 1 : 5) }); }
      return json(409, { detail: "MCN-20261118-001 changed since it was read (now version 5)." });
    });
    const { container } = render(<Workspace id="MCN-20261118-001" />);
    await screen.findByText("123456789");
    const user = userEvent.setup();
    await user.click(phoneRow(container).getByRole("button", { name: "Kosongkan" }));
    expect(await screen.findByText("Data sudah berubah. Muat ulang.")).toBeTruthy();
    await waitFor(() => expect(reads).toBe(2));
    expect(screen.getByText("Versi 5")).toBeTruthy();
    const write = calls.find((c) => c.method === "PATCH")!;
    expect(JSON.parse(write.body!).expected_version).toBe(1);
  });

  it("shows another server error exactly as sent", async () => {
    vi.spyOn(globalThis, "fetch").mockImplementation((_u, init) =>
      (init as RequestInit).method === "GET"
        ? json(200, { merchant_id: "MCN-20261118-001", version: 1, record: record() })
        : json(400, { detail: "The value is not a valid value for contact_information.phone; nothing was changed." }));
    const { container } = render(<Workspace id="MCN-20261118-001" />);
    await screen.findByText("123456789");
    const user = userEvent.setup();
    await user.click(phoneRow(container).getByRole("button", { name: "Ubah" }));
    await user.type(screen.getByLabelText("Nilai Business Phone"), "abc");
    await user.click(screen.getByRole("button", { name: "Simpan" }));
    expect(await screen.findByText("The value is not a valid value for contact_information.phone; nothing was changed.")).toBeTruthy();
  });
});

describe("click to copy", () => {
  afterEach(cleanup);
  it("copies a field value with one click and says so", async () => {
    const writeText = vi.fn(async () => undefined);
    const user = userEvent.setup();                     // setup() installs its own clipboard, so ours goes after it
    Object.defineProperty(navigator, "clipboard", { value: { writeText }, configurable: true });
    const { default: FieldRow } = await import("./components/FieldRow");
    render(<FieldRow def={{ label: "Business Phone", path: "contact_information.phone" }} sources={[]} busy={false} readOnly
                     field={f("+1 (555) 010-0187")} onSet={() => {}} onConfirm={() => {}} onClear={() => {}} />);
    await user.click(screen.getByRole("button", { name: "Salin Business Phone" }));
    expect(writeText).toHaveBeenCalledWith("+1 (555) 010-0187");
    expect(await screen.findByText("Tersalin")).toBeTruthy();
  });

  it("has nothing to copy when the value is empty, and reports a refused copy", async () => {
    const user = userEvent.setup();
    const { default: FieldRow } = await import("./components/FieldRow");
    const noop = () => {};
    const { unmount } = render(<FieldRow def={{ label: "Business Email", path: "contact_information.email" }} sources={[]}
                                         busy={false} readOnly field={f(null, "missing")} onSet={noop} onConfirm={noop} onClear={noop} />);
    expect(screen.queryByRole("button", { name: "Salin Business Email" })).toBeNull();
    unmount();
    Object.defineProperty(navigator, "clipboard", { value: { writeText: vi.fn(async () => { throw new Error("denied"); }) }, configurable: true });
    render(<FieldRow def={{ label: "Business Email", path: "contact_information.email" }} sources={[]} busy={false} readOnly
                     field={f("a@example.com")} onSet={noop} onConfirm={noop} onClear={noop} />);
    await user.click(screen.getByRole("button", { name: "Salin Business Email" }));
    expect(await screen.findByText("Gagal menyalin")).toBeTruthy();
  });
});
