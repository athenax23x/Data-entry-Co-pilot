import { cleanup, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import FillMode, { fillQueue, resetFillProgressForTests } from "./components/FillMode";
import type { MerchantRecord } from "./api";

const f = (value: unknown) => ({ value, status: value === null ? "missing" : "inferred", source_context: null, source_document: null });
const rec = {
  merchant_id: "MCN-20261120-001", record_status: "Incomplete", sources: [], conflicts: [],
  business_information: { legal_business_name: f("Example Goods LLC"), business_start_date: f(null), business_description: f("Car wash") },
  contact_information: { phone: f("+1 (555) 010-0187") },
} as unknown as MerchantRecord;

describe("Mode isi form", () => {
  let clip: string[];
  beforeEach(() => {
    clip = [];
    resetFillProgressForTests();
    Object.defineProperty(navigator, "clipboard", { value: { writeText: vi.fn(async (t: string) => { clip.push(t); }) }, configurable: true });
  });
  afterEach(() => cleanup());

  it("queues the filled fields in Paykings order and lists the empty ones", () => {
    const q = fillQueue(rec);
    expect(q.items.map((i) => i.value)).toEqual(["Example Goods LLC", "Car wash", "+1 (555) 010-0187"]);
    expect(q.empty.map((e) => e.label)).toContain("Business Start Date");
  });

  it("copies the current value and moves to the next, then reports when all are done", async () => {
    const u = userEvent.setup();
    Object.defineProperty(navigator, "clipboard", { value: { writeText: vi.fn(async (t: string) => { clip.push(t); }) }, configurable: true });
    render(<FillMode merchantId="MCN-20261120-001" record={rec} />);
    for (let i = 0; i < 3; i++) await u.click(screen.getByRole("button", { name: /Salin & lanjut/ }));
    expect(clip).toEqual(["Example Goods LLC", "Car wash", "+1 (555) 010-0187"]);
    expect(screen.getByText("Semua field sudah disalin")).toBeTruthy();
    cleanup();
    render(<FillMode merchantId="MCN-20261120-001" record={rec} />);                 // remembered while the page is open
    expect(screen.getByText("Semua field sudah disalin")).toBeTruthy();
  });

  it("skip leaves a field unmarked", async () => {
    const u = userEvent.setup();
    Object.defineProperty(navigator, "clipboard", { value: { writeText: vi.fn(async (t: string) => { clip.push(t); }) }, configurable: true });
    render(<FillMode merchantId="MCN-20261120-001" record={rec} />);
    await u.click(screen.getByRole("button", { name: "Lewati" }));
    expect(screen.getByLabelText("Nilai saat ini").textContent).toBe("Car wash");
    expect(clip).toEqual([]);
  });
});
