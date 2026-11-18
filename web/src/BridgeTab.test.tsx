import { cleanup, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { ApiError, setTokenForTests, type BridgeProposal } from "./api";
import BridgeTab from "./components/BridgeTab";
import { COPY_WARNING } from "./status";

const json = (status: number, body: unknown) => Promise.resolve(new Response(JSON.stringify(body), { status }));
const prop = (over: Partial<BridgeProposal>): BridgeProposal => ({
  index: 0, path: "contact_information.phone", value: "+1 (555) 010-0187", evidence: "Phone 555-010-0187", status: "inferred",
  ambiguous: false, ok: true, reason: null, outcome: "filled", ...over,
});

function setup(onApply = vi.fn(async () => true), onStale = vi.fn()) {
  const view = render(<BridgeTab merchantId="MCN-20261118-001" version={3} onApply={onApply} onStale={onStale} />);
  return { ...view, onApply, onStale, user: userEvent.setup() };
}

describe("BridgeTab", () => {
  beforeEach(() => setTokenForTests("tok"));
  afterEach(() => { cleanup(); vi.restoreAllMocks(); setTokenForTests(null); });

  it("prepares the prompt, warns, and copies it with the clipboard (nothing is stored)", async () => {
    const calls: string[] = [];
    vi.spyOn(globalThis, "fetch").mockImplementation((url) => {
      calls.push(String(url));
      return json(200, { masked_text: "Example [DISAMARKAN]", prompt: "PROMPT with Example [DISAMARKAN]", hidden: ["bank account number"] });
    });
    const writeText = vi.fn(async () => undefined);
    const set = vi.spyOn(Storage.prototype, "setItem");
    const { user } = setup();
    Object.defineProperty(navigator, "clipboard", { value: { writeText }, configurable: true });
    await user.type(screen.getByLabelText("Teks sumber"), "Example text");
    await user.click(screen.getByRole("button", { name: "Siapkan" }));
    expect(await screen.findByText(COPY_WARNING)).toBeTruthy();
    expect(COPY_WARNING).toBe("Teks ini akan dikirim ke Claude. Pastikan tidak ada data yang tidak Anda setujui.");
    expect(screen.getByText(/Disamarkan atau dibuang: bank account number/)).toBeTruthy();
    await user.click(screen.getByRole("button", { name: "Salin" }));
    expect(writeText).toHaveBeenCalledWith("PROMPT with Example [DISAMARKAN]");
    expect(await screen.findByText(/Prompt disalin/)).toBeTruthy();
    expect(calls).toEqual(["/api/bridge/prepare"]);
    expect(set).not.toHaveBeenCalled();
  });

  it("shows proposals with the check result; rejected ones cannot be chosen; Terapkan sends only the chosen", async () => {
    const proposals = [prop({}), prop({ index: 1, path: "business_information.legal_business_name", value: null, evidence: "", ok: false, reason: "Bukti tidak ditemukan di teks sumber.", outcome: null }),
      prop({ index: 2, path: "personal_information.owners[0].date_of_birth", value: "06/02/2004", status: "needs_review", ambiguous: true, outcome: "review" })];
    vi.spyOn(globalThis, "fetch").mockImplementation(() => json(200, { version: 3, proposals }));
    const { user, onApply } = setup();
    await user.type(screen.getByLabelText("Teks sumber"), "src");
    await user.type(screen.getByLabelText("Jawaban JSON dari Claude"), "{{}");
    await user.click(screen.getByRole("button", { name: "Periksa" }));
    expect(await screen.findByText(/Ditolak: Bukti tidak ditemukan di teks sumber\./)).toBeTruthy();
    expect(screen.getByText(/tanggal ambigu/)).toBeTruthy();
    const boxes = screen.getAllByRole("checkbox") as HTMLInputElement[];
    expect(boxes.map((b) => [b.checked, b.disabled])).toEqual([[true, false], [false, true], [true, false]]);
    await user.click(boxes[2]);
    await user.click(screen.getByRole("button", { name: "Terapkan (1)" }));
    expect(onApply).toHaveBeenCalledWith("{}", "src", [0]);
    await waitFor(() => expect(screen.queryByRole("table")).toBeNull());
  });

  it("on 409 shows the reload message and asks the workspace to reload", async () => {
    vi.spyOn(globalThis, "fetch").mockImplementation(() => json(409, { detail: "changed (now version 9)" }));
    const { user, onStale } = setup();
    await user.type(screen.getByLabelText("Teks sumber"), "src");
    await user.type(screen.getByLabelText("Jawaban JSON dari Claude"), "x");
    await user.click(screen.getByRole("button", { name: "Periksa" }));
    expect(await screen.findByText("Data sudah berubah. Muat ulang.")).toBeTruthy();
    expect(onStale).toHaveBeenCalled();
  });

  it("shows the general answer error as the server sent it", async () => {
    vi.spyOn(globalThis, "fetch").mockImplementation(() => json(400, { detail: "Jawaban tidak bisa dibaca. Tempel jawaban JSON dari Claude apa adanya (maks. 50 KB)." }));
    const { user } = setup();
    await user.type(screen.getByLabelText("Teks sumber"), "src");
    await user.type(screen.getByLabelText("Jawaban JSON dari Claude"), "oops");
    await user.click(screen.getByRole("button", { name: "Periksa" }));
    expect(await screen.findByText(/Jawaban tidak bisa dibaca/)).toBeTruthy();
    expect(new ApiError(400, "x").status).toBe(400);
  });

  it("tells the person when copying is not possible", async () => {
    vi.spyOn(globalThis, "fetch").mockImplementation(() => json(200, { masked_text: "m", prompt: "p", hidden: [] }));
    const { user } = setup();
    Object.defineProperty(navigator, "clipboard", { value: { writeText: vi.fn(async () => { throw new Error("denied"); }) }, configurable: true });
    await user.type(screen.getByLabelText("Teks sumber"), "src");
    await user.click(screen.getByRole("button", { name: "Siapkan" }));
    await user.click(await screen.findByRole("button", { name: "Salin" }));
    expect(await screen.findByText(/Tidak bisa menyalin otomatis/)).toBeTruthy();
  });
});
