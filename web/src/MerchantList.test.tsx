import { cleanup, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { setTokenForTests } from "./api";
import { peekBridgeText } from "./handoff";
import MerchantList from "./screens/MerchantList";

const row = (id: string, status: string, extra: Record<string, unknown> = {}) => ({
  merchant_id: id, legal_name: `${id} LLC`, entity_type: "llc", record_status: status, version: 2,
  updated_at: "2026-11-20T10:00:00Z", archived: false, filled: 10, total: 40, open_conflicts: 0, ...extra,
});
const json = (status: number, body: unknown) => Promise.resolve(new Response(JSON.stringify(body), { status }));

describe("Daftar merchant", () => {
  beforeEach(() => { setTokenForTests("tok"); window.location.hash = ""; });
  afterEach(() => { cleanup(); vi.restoreAllMocks(); setTokenForTests(null); });

  it("shows progress and conflicts, and filters by status", async () => {
    vi.spyOn(globalThis, "fetch").mockImplementation(() => json(200, { merchants: [
      row("MCN-20261120-001", "Incomplete"), row("MCN-20261120-002", "Needs Review", { open_conflicts: 2 })] }));
    const u = userEvent.setup();
    render(<MerchantList />);
    expect(await screen.findByText("MCN-20261120-001 LLC")).toBeTruthy();
    expect(screen.getAllByText("10/40").length).toBe(2);
    await u.click(screen.getByRole("button", { name: /Perlu ditinjau/ }));
    expect(screen.queryByText("MCN-20261120-001 LLC")).toBeNull();
    expect(screen.getByText("MCN-20261120-002 LLC")).toBeTruthy();
  });

  it("quick paste for Claude creates an empty merchant and hands the text over in memory", async () => {
    const calls: { url: string; method: string; body?: string }[] = [];
    vi.spyOn(globalThis, "fetch").mockImplementation((url, init) => {
      const method = (init as RequestInit)?.method ?? "GET";
      calls.push({ url: String(url), method, body: (init as RequestInit)?.body as string | undefined });
      if (method === "POST") return json(201, { merchant_id: "MCN-20261120-003", version: 1, record: {} });
      return json(200, { merchants: [] });
    });
    const u = userEvent.setup();
    render(<MerchantList />);
    await u.type(screen.getByLabelText("Tempel cepat"), "Example Goods LLC; owner@example.com");
    await u.click(screen.getByRole("button", { name: /siapkan prompt Claude/ }));
    await waitFor(() => expect(window.location.hash).toBe("#/m/MCN-20261120-003"));
    const post = calls.find((c) => c.method === "POST")!;
    expect(JSON.parse(post.body!)).toEqual({ text: "" });
    expect(peekBridgeText("MCN-20261120-003")).toBe("Example Goods LLC; owner@example.com");
    expect(window.location.hash).not.toContain("Example");
  });

  it("archive view: delete asks first, then sends the version", async () => {
    const calls: { url: string; method: string }[] = [];
    vi.spyOn(globalThis, "fetch").mockImplementation((url, init) => {
      const method = (init as RequestInit)?.method ?? "GET";
      calls.push({ url: String(url), method });
      if (method === "DELETE") return json(200, { deleted: true });
      return json(200, { merchants: String(url).includes("archived=true") ? [row("MCN-20261118-002", "Incomplete", { archived: true })] : [] });
    });
    const u = userEvent.setup();
    render(<MerchantList />);
    await u.click(await screen.findByRole("button", { name: "Lihat arsip" }));
    await u.click(await screen.findByRole("button", { name: "Hapus MCN-20261118-002" }));
    expect(calls.some((c) => c.method === "DELETE")).toBe(false);
    await u.click(screen.getByRole("button", { name: "Ya, hapus MCN-20261118-002" }));
    await waitFor(() => expect(calls.find((c) => c.method === "DELETE")?.url).toBe("/api/merchants/MCN-20261118-002?expected_version=2"));
  });
});
