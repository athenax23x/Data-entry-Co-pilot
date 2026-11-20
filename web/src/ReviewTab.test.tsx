import { cleanup, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { setTokenForTests } from "./api";
import ReviewTab from "./components/ReviewTab";

const json = (status: number, body: unknown) => Promise.resolve(new Response(JSON.stringify(body), { status }));
const review = {
  merchant_id: "MCN-20261120-001", stage: "baru", app_status: "no_info", message: "Hi Pat,\n\nBusiness address:\n- Business ZIP code",
  missing: [{ section: "Business address", label: "Business ZIP", ask: "Business ZIP code" }],
  checks: [
    { level: "warn", code: "ownership_low", message: "Ownership % pemilik di bawah 25%.", fields: ["Ownership %"] },
    { level: "error", code: "card_mix", message: "Card Swipe % + Card Keyed % + Card Internet % berjumlah 90%, seharusnya 100%.", fields: [] },
  ],
};

describe("Periksa", () => {
  beforeEach(() => setTokenForTests("tok"));
  afterEach(() => { cleanup(); vi.restoreAllMocks(); setTokenForTests(null); });

  it("lists errors first, reports the error count, copies the message, and sets the stage", async () => {
    const calls: { url: string; method: string; body?: string }[] = [];
    vi.spyOn(globalThis, "fetch").mockImplementation((url, init) => {
      const method = (init as RequestInit)?.method ?? "GET";
      calls.push({ url: String(url), method, body: (init as RequestInit)?.body as string | undefined });
      return method === "POST" ? json(200, { stage: "menunggu_info" }) : json(200, review);
    });
    const counts: number[] = [];
    const u = userEvent.setup();
    const writes: string[] = [];
    Object.defineProperty(navigator, "clipboard", { value: { writeText: vi.fn(async (t: string) => { writes.push(t); }) }, configurable: true });
    render(<ReviewTab merchantId="MCN-20261120-001" version={3} onCount={(n) => counts.push(n)} />);
    const items = await screen.findAllByRole("listitem");
    expect(items[0].textContent).toContain("Perbaiki");
    expect(counts).toEqual([1]);
    await u.click(screen.getByRole("button", { name: "Salin pesan" }));
    expect(writes).toEqual([review.message]);
    await u.click(screen.getByRole("button", { name: /Menunggu info merchant/ }));
    await waitFor(() => expect(calls.find((c) => c.method === "POST")?.body).toBe(JSON.stringify({ stage: "menunggu_info" })));
    expect((screen.getByLabelText("Tahap kerja") as HTMLSelectElement).value).toBe("menunggu_info");
    await u.selectOptions(screen.getByLabelText("Status aplikasi"), "signed_waiting_underwriting");
    await waitFor(() => expect(calls.some((c) => c.url.endsWith("/application-status")
      && c.body === JSON.stringify({ app_status: "signed_waiting_underwriting" }))).toBe(true));
  });
});
