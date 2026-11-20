import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { ApiError, TOKEN_PLACEHOLDER, readToken, setTokenForTests, updateField } from "./api";

function reply(status: number, body: unknown) {
  return Promise.resolve(new Response(JSON.stringify(body), { status, headers: { "Content-Type": "application/json" } }));
}

describe("token", () => {
  it("is read from the meta tag; the unfilled placeholder counts as no token", () => {
    const doc = document.implementation.createHTMLDocument("t");
    expect(readToken(doc)).toBeNull();
    doc.head.innerHTML = `<meta name="mcn-token" content="${TOKEN_PLACEHOLDER}">`;
    expect(readToken(doc)).toBeNull();
    doc.head.innerHTML = '<meta name="mcn-token" content="abc123">';
    expect(readToken(doc)).toBe("abc123");
  });
});

describe("requests", () => {
  beforeEach(() => setTokenForTests("tok"));
  afterEach(() => { vi.restoreAllMocks(); setTokenForTests(null); });

  it("sends the token header and the version, and keeps the value out of the URL", async () => {
    const f = vi.spyOn(globalThis, "fetch").mockImplementation(() => reply(200, { version: 2 }));
    await updateField("MCN-20261118-001", "personal_information.owners[0].ssn", { expected_version: 1, action: "set", value: "123456789" });
    const [url, init] = f.mock.calls[0] as [string, RequestInit];
    expect(url).not.toContain("123456789");
    expect(url).toContain("/api/merchants/MCN-20261118-001/fields/");
    expect((init.headers as Record<string, string>)["X-MCN-Token"]).toBe("tok");
    expect(JSON.parse(init.body as string)).toEqual({ expected_version: 1, action: "set", value: "123456789" });
  });
  it("turns a 409 into an ApiError with status 409", async () => {
    vi.spyOn(globalThis, "fetch").mockImplementation(() => reply(409, { detail: "changed" }));
    await expect(updateField("MCN-20261118-001", "notes", { expected_version: 1, action: "missing" })).rejects.toMatchObject({ status: 409 });
  });
  it("keeps the server message as sent", async () => {
    vi.spyOn(globalThis, "fetch").mockImplementation(() => reply(400, { detail: "No such field." }));
    const err = await updateField("MCN-20261118-001", "x", { expected_version: 1, action: "missing" }).catch((e) => e);
    expect(err).toBeInstanceOf(ApiError);
    expect(err.message).toBe("No such field.");
  });
  it("says so when the server cannot be reached, and when there is no token", async () => {
    vi.spyOn(globalThis, "fetch").mockImplementation(() => Promise.reject(new TypeError("net")));
    await expect(updateField("MCN-20261118-001", "x", { expected_version: 1, action: "missing" })).rejects.toThrow("Tidak dapat terhubung ke server.");
    setTokenForTests(null);
    await expect(updateField("MCN-20261118-001", "x", { expected_version: 1, action: "missing" })).rejects.toThrow("Token sesi tidak ditemukan");
  });
  it("never touches localStorage or the console", async () => {
    const log = vi.spyOn(console, "log");
    const get = vi.spyOn(Storage.prototype, "getItem");
    const set = vi.spyOn(Storage.prototype, "setItem");
    vi.spyOn(globalThis, "fetch").mockImplementation(() => reply(200, {}));
    await updateField("MCN-20261118-001", "notes", { expected_version: 1, action: "set", value: "x" });
    expect(log).not.toHaveBeenCalled();
    expect(get).not.toHaveBeenCalled();
    expect(set).not.toHaveBeenCalled();
  });
});


describe("guest mode flag", () => {
  it("is on only when the page says 1", async () => {
    const { isGuest } = await import("./api");
    for (const [content, expected] of [["1", true], ["0", false], ["__MCN_GUEST__", false]] as const) {
      const doc = new DOMParser().parseFromString(`<head><meta name="mcn-guest" content="${content}"></head>`, "text/html");
      expect(isGuest(doc)).toBe(expected);
    }
    expect(isGuest(new DOMParser().parseFromString("<head></head>", "text/html"))).toBe(false);
  });
});
