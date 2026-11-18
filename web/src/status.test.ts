import { describe, expect, it } from "vitest";
import { ApiError } from "./api";
import { STALE_MESSAGE, errorMessage, formatValue, isStale, statusClass, statusLabel } from "./status";

describe("status format", () => {
  it("has a label and a different class for every status", () => {
    const all = ["verified", "inferred", "missing", "conflict", "needs_review"];
    expect(all.map(statusLabel)).toEqual(["Terverifikasi", "Dugaan", "Kosong", "Konflik", "Perlu ditinjau"]);
    expect(new Set(all.map(statusClass)).size).toBe(5);
    expect(statusClass("needs_review")).toBe("st-needs-review");
  });
  it("does not break on an unknown status", () => {
    expect(statusLabel("weird")).toBe("weird");
    expect(statusClass("weird")).toBe("st-unknown");
  });
  it("shows an empty value as a dash and everything else in full", () => {
    expect(formatValue(null)).toBe("—");
    expect(formatValue("")).toBe("—");
    expect(formatValue(0)).toBe("0");
    expect(formatValue("123456789")).toBe("123456789");
  });
});

describe("error mapping", () => {
  it("maps 409 to the reload message, whatever the server wrote", () => {
    const e = new ApiError(409, "changed since it was read (now version 3)");
    expect(isStale(e)).toBe(true);
    expect(errorMessage(e)).toBe(STALE_MESSAGE);
    expect(STALE_MESSAGE).toBe("Data sudah berubah. Muat ulang.");
  });
  it("shows other server messages as they came", () => {
    expect(errorMessage(new ApiError(400, "The value is not valid."))).toBe("The value is not valid.");
    expect(isStale(new ApiError(400, "x"))).toBe(false);
  });
  it("adds the field names of a 422", () => {
    expect(errorMessage(new ApiError(422, "The request is not valid.", ["value", "expected_version"])))
      .toBe("The request is not valid. (value, expected_version)");
  });
  it("has a safe text for anything else", () => {
    expect(errorMessage(new Error("boom 123456789"))).toBe("Terjadi kesalahan yang tidak dikenal.");
  });
});
