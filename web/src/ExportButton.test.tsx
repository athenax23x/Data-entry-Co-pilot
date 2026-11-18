import { cleanup, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";
import { setTokenForTests } from "./api";
import ExportButton from "./components/ExportButton";

afterEach(() => { cleanup(); vi.restoreAllMocks(); setTokenForTests(null); });

describe("ExportButton", () => {
  it("downloads the CSV for one merchant without sensitive data unless the box is ticked", async () => {
    setTokenForTests("t");
    const urls: string[] = [];
    const fetchMock = vi.fn(async (u: string) => { urls.push(u); return new Response("a,b\r\n", { status: 200 }); });
    vi.stubGlobal("fetch", fetchMock);
    URL.createObjectURL = vi.fn(() => "blob:x");
    URL.revokeObjectURL = vi.fn();
    const user = userEvent.setup();
    render(<ExportButton merchantId="MCN-20261118-001" />);
    await user.click(screen.getByRole("button", { name: "Unduh CSV Paykings" }));
    expect(urls[0]).toBe("/api/export/paykings.csv?merchant_id=MCN-20261118-001");
    expect(await screen.findByText("Tersimpan: MCN-20261118-001.csv")).toBeTruthy();
    await user.click(screen.getByRole("checkbox"));
    await user.click(screen.getByRole("button", { name: "Unduh CSV Paykings" }));
    expect(urls[1]).toBe("/api/export/paykings.csv?merchant_id=MCN-20261118-001&include_sensitive=true");
  });

  it("says so when the export fails", async () => {
    setTokenForTests("t");
    vi.stubGlobal("fetch", vi.fn(async () => new Response("", { status: 500 })));
    const user = userEvent.setup();
    render(<ExportButton />);
    await user.click(screen.getByRole("button", { name: "Unduh CSV Paykings" }));
    expect(await screen.findByText(/Ekspor gagal \(500\)/)).toBeTruthy();
  });
});
