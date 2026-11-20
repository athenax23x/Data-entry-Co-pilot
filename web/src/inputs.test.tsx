import { cleanup, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";
import FieldRow from "./components/FieldRow";
import { draftFor, isCompleteDate, maskDateInput, ruleFor, toUsDate } from "./inputs";

const f = (value: unknown) => ({ value, status: value === null ? "missing" : "verified", source_context: null, source_document: null });

describe("typed inputs", () => {
  afterEach(() => { cleanup(); vi.restoreAllMocks(); });

  it("dates: digits only, MM/DD/YYYY, real calendar dates", () => {
    expect(maskDateInput("451dfas")).toBe("45/1");
    expect(maskDateInput("03152019")).toBe("03/15/2019");
    expect(isCompleteDate("02/29/2024") && !isCompleteDate("02/30/2024") && !isCompleteDate("13/01/2020")).toBe(true);
    expect(toUsDate("2019-03-15")).toBe("03/15/2019");
  });

  it("phone, ZIP, EIN, routing, percent, amount take numbers only", () => {
    expect(ruleFor("phone")!.mask("call 555abc0100187")).toBe("(555) 010-0187");
    expect(ruleFor("phone")!.mask("+1 (555) 010-0187")).toBe("(555) 010-0187");
    expect(ruleFor("phone")!.ok("(155) 010-0187")).toBe(false);
    expect(ruleFor("zip")!.mask("78701x1234")).toBe("78701-1234");
    expect(ruleFor("ein")!.mask("12a3456789")).toBe("12-3456789");
    expect(ruleFor("routing")!.mask("0210-00021")).toBe("021000021");
    expect(ruleFor("percent")!.ok("101")).toBe(false);
    expect(ruleFor("amount")!.mask("$40,000.555")).toBe("40000.55");
    expect(draftFor("phone", "+1 (555) 010-0187")).toBe("(555) 010-0187");
    expect(ruleFor("text" as never)).toBeNull();
  });

  it("the form row refuses letters in a date and saves only a full date", async () => {
    const saved: string[] = [];
    const u = userEvent.setup();
    render(<FieldRow def={{ label: "Business Start Date", path: "business_information.business_start_date", kind: "date", sensitive: false }}
                     field={f("2019-03-15")} sources={[]} busy={false}
                     onSet={(v) => saved.push(v)} onConfirm={() => undefined} onClear={() => undefined} />);
    expect(screen.getByRole("button", { name: "Salin Business Start Date" }).textContent).toContain("03/15/2019");
    await u.click(screen.getByRole("button", { name: "Ubah" }));
    const box = screen.getByLabelText("Nilai Business Start Date") as HTMLInputElement;
    expect(box.value).toBe("03/15/2019");
    await u.clear(box);
    await u.type(box, "451dfas");
    expect(box.value).toBe("45/1");
    expect((screen.getByRole("button", { name: "Simpan" }) as HTMLButtonElement).disabled).toBe(true);
    await u.clear(box);
    await u.type(box, "06022004");
    await u.click(screen.getByRole("button", { name: "Simpan" }));
    expect(saved).toEqual(["06/02/2004"]);
  });

  it("the form row keeps letters out of a phone number", async () => {
    const u = userEvent.setup();
    render(<FieldRow def={{ label: "Business Phone", path: "contact_information.phone", kind: "phone", sensitive: false }}
                     field={f(null)} sources={[]} busy={false}
                     onSet={() => undefined} onConfirm={() => undefined} onClear={() => undefined} />);
    await u.click(screen.getByRole("button", { name: "Ubah" }));
    const box = screen.getByLabelText("Nilai Business Phone") as HTMLInputElement;
    await u.type(box, "abc555x0100187");
    expect(box.value).toBe("(555) 010-0187");
  });
});
