"""The nine Notebook commands, exactly as listed in the Commands table of instructions.md."""
from __future__ import annotations

import re
from datetime import datetime, timezone
from pathlib import Path

from . import csv_export, extract as X, record as R, store
from .fields import FIELD_SPECS, FieldError, normalizer_for, resolve_target

COMMANDS = ("NEW MERCHANT", "ADD CONTEXT", "UPDATE FIELD", "SHOW MERCHANT", "SHOW MISSING FIELDS",
            "SAVE MERCHANT", "LOAD MERCHANT", "EXPORT CSV", "CLEAR SESSION")
PRIVACY_NOTICE = ("Note: this assistant may run on a cloud-hosted AI model. Information you submit is sent to "
                  "that model provider for processing, even though merchant records are saved only to local "
                  "files when you request it.")
_CMD_RX = re.compile(r"^\s*(" + "|".join(r"\s+".join(c.split()) for c in sorted(COMMANDS, key=len, reverse=True))
                     + r")\b(.*)$", re.I | re.S)
_ID_FIRST = re.compile(r"^\s*(MCN-[0-9]{8}-[0-9]{3,})\b\s*(.*)$", re.S)


class CommandError(Exception):
    pass


def _show(v) -> str:
    return "—" if v is None else str(v)


class Session:
    def __init__(self, data_dir, confirm=lambda question: False, now=None):
        self.data_dir = Path(data_dir)
        self.confirm = confirm
        self.now = now or (lambda: datetime.now(timezone.utc))
        self.records: dict[str, dict] = {}
        self.active: str | None = None
        self.dirty: set[str] = set()
        self._notice_shown = False

    # ------------------------------------------------------------------ dispatch
    def execute(self, line: str) -> str:
        m = _CMD_RX.match(line)
        if not m:
            return ("Not a Notebook command. Commands: " + ", ".join(COMMANDS) + ".\n"
                    "(Quick Parser is the prompt in instructions.md; this app only runs the Notebook commands.)")
        name = " ".join(m.group(1).upper().split())
        rest = m.group(2)
        try:
            out = getattr(self, "cmd_" + name.lower().replace(" ", "_"))(rest)
        except (CommandError, R.RecordError, FieldError) as e:
            return f"Error: {e}"
        if name in ("NEW MERCHANT", "ADD CONTEXT", "UPDATE FIELD", "LOAD MERCHANT") and not self._notice_shown:
            self._notice_shown = True
            out = PRIVACY_NOTICE + "\n\n" + out
        return out

    # ------------------------------------------------------------------ helpers
    def _now(self) -> str:
        return R.iso(self.now())

    def _target(self, rest: str):
        """Optional leading merchant_id. Returns (record, remaining text)."""
        m = _ID_FIRST.match(rest)
        if m:
            mid, rest = m.group(1), m.group(2)
            if mid not in self.records:
                raise CommandError(f"{mid} is not in this session. Use LOAD MERCHANT {mid} first.")
            return self.records[mid], rest.strip()
        if not self.active:
            raise CommandError("No active merchant. Use NEW MERCHANT or LOAD MERCHANT first.")
        return self.records[self.active], rest.strip()

    def _new_id(self, now: str) -> str:
        day = now[:10].replace("-", "")
        used = set(self.records)
        if self.data_dir.is_dir():                      # file names only; contents are never read here
            used |= {p.stem for p in self.data_dir.glob("MCN-*.json")}
        n = 1
        while f"MCN-{day}-{n:03d}" in used:
            n += 1
        return f"MCN-{day}-{n:03d}"

    def _apply(self, rec: dict, text: str, sid: str, now: str):
        ex = X.extract(text)
        tally = {"filled": [], "unchanged": [], "conflict": [], "review": [], "ignored": []}
        for it in ex.items:
            if it.list_item:
                out = R.merge_list_item(rec, it.keys, it.value, it.context, sid, now)
            else:
                out = R.merge_value(rec, it.keys, it.value, it.status, it.context, sid, now, it.weak)
            tally[out].append(R.pointer(it.keys))
        return ex, tally

    def _summary(self, rec, ex, tally) -> str:
        lines = []
        for label, key in (("Filled", "filled"), ("Unchanged", "unchanged"),
                           ("Needs review (unclear)", "review"), ("CONFLICT (verified/earlier value kept)", "conflict"),
                           ("Ignored (unclear, existing value kept)", "ignored")):
            if tally[key]:
                lines.append(f"  {label}: " + ", ".join(sorted(set(tally[key]))))
        if not any(tally.values()):
            lines.append("  Nothing could be extracted from that text.")
        if ex.discarded:
            lines.append("  Discarded and NOT stored: " + ", ".join(ex.discarded) + ".")
        lines.append(f"  Record status: {rec['record_status']}")
        return "\n".join(lines)

    # ------------------------------------------------------------------ commands
    def cmd_new_merchant(self, rest: str) -> str:
        now = self._now()
        rec = R.new_record(self._new_id(now), now)
        sid = R.add_source(rec, "new_merchant", now)
        ex, tally = self._apply(rec, rest.strip(), sid, now)
        R.touch(rec, now)
        self.records[rec["merchant_id"]] = rec
        self.active = rec["merchant_id"]
        self.dirty.add(rec["merchant_id"])
        return f"Created {rec['merchant_id']} (active). Not saved.\n" + self._summary(rec, ex, tally)

    def cmd_add_context(self, rest: str) -> str:
        rec, text = self._target(rest)
        if not text:
            raise CommandError("ADD CONTEXT needs some text.")
        now = self._now()
        ex = X.extract(text)
        cur_name = rec["business_information"]["legal_business_name"]["value"]
        cur_ein = rec["ein"]["value"]
        new_name = next((i.value for i in ex.items if i.keys[-1] == "legal_business_name" and i.value), None)
        new_ein = next((i.value for i in ex.items if i.keys == ("ein",) and i.value), None)
        if cur_name and cur_ein and new_name and new_ein and new_name != cur_name and new_ein != cur_ein:
            raise CommandError("This looks like a different merchant (different business name and EIN). "
                               "Nothing was merged. Use NEW MERCHANT for it.")
        sid = R.add_source(rec, "add_context", now)
        ex, tally = self._apply(rec, text, sid, now)
        R.touch(rec, now)
        self.dirty.add(rec["merchant_id"])
        return f"Updated {rec['merchant_id']}. Not saved.\n" + self._summary(rec, ex, tally)

    def cmd_update_field(self, rest: str) -> str:
        rec, body = self._target(rest)
        field_txt, eq, value_txt = body.partition("=")
        if not eq:
            raise CommandError("Use: UPDATE FIELD [merchant_id] <field> = <value>")
        value_txt = value_txt.strip()
        if not value_txt:
            raise CommandError("No value given. Use a value, 'confirm' or 'missing'.")
        redacted = X.redact(value_txt)[1]
        if redacted:
            raise CommandError("That value looks like sensitive data (" + ", ".join(redacted) + "). It was not "
                               "stored. (For an SSN, give only the last 4 digits: UPDATE FIELD ssn_last4 = 1234.)")
        keys = resolve_target(field_txt)
        now = self._now()
        if keys[0] == "custom_fields":
            R.ensure_custom(rec, keys)
        if keys[:2] == ("personal_information", "owners"):
            R.ensure_owner(rec, keys[2])
        if keys[:2] == ("products_and_services", "items"):
            items = rec["products_and_services"]["items"]
            idx = len(items) if keys[2] == "+" else keys[2]
            if idx > len(items) or (idx == len(items) and keys[2] != "+"):
                raise R.RecordError(f"There are {len(items)} item(s); item {idx} does not exist.")
            if idx == len(items):
                items.append(R.empty_field())
            keys = ("products_and_services", "items", idx)
        label = R.pointer(keys)
        ctx = f"UPDATE FIELD {field_txt.strip()} = {value_txt}"[: X.CTX_MAX]
        low = value_txt.lower()
        if low == "confirm":
            sid = R.add_source(rec, "update_field", now)
            old = R.user_confirm(rec, keys, ctx, sid, now)
            msg = f"{label}: confirmed {_show(old[0])} (was {old[1]}) -> verified"
        elif low == "missing":
            if R.get_field(rec, keys)["value"] is None and R.get_field(rec, keys)["status"] == "missing":
                raise CommandError(f"{label} is already missing.")
            R.add_source(rec, "update_field", now)
            old = R.user_clear(rec, keys, now)
            msg = f"{label}: cleared (was {_show(old[0])}, {old[1]}) -> missing; previous value kept in history"
        else:
            spec = R.spec_key(keys)
            norm = normalizer_for(spec)(value_txt)
            if norm is None:
                raise CommandError(f"'{value_txt}' is not a valid value for {spec or label}; nothing was changed.")
            sid = R.add_source(rec, "update_field", now)
            old = R.user_set(rec, keys, norm, ctx, sid, now)
            msg = f"{label}: {_show(old[0])} ({old[1]}) -> {norm} (verified)"
        R.touch(rec, now)
        self.dirty.add(rec["merchant_id"])
        return f"{msg}\nRecord status: {rec['record_status']}. Not saved."

    def cmd_show_merchant(self, rest: str) -> str:
        rec, _ = self._target(rest)
        rows = [("path", "value", "status", "source_context", "source_document")]

        def add(path, f):
            rows.append((path, _show(f["value"]), f["status"], _show(f["source_context"]),
                         _show(f["source_document"])))

        add("business_entity_type", rec["business_entity_type"])
        for i, o in enumerate(rec["personal_information"]["owners"]):
            rows.append((f"owners[{i}] ({o['owner_id']}{', primary' if o['is_primary_owner'] else ''})",
                         "", "", "", ""))
            for k in ("first_name", "last_name", "date_of_birth", "ssn_last4", "title", "ownership_percentage"):
                add(f"  owners[{i}].{k}", o[k])
        for sec in ("business_information", "business_address", "contact_information"):
            for k, f in rec[sec].items():
                add(f"{sec}.{k}", f)
        add("ein", rec["ein"])
        for k, f in rec["processing_information"].items():
            add(f"processing_information.{k}", f)
        add("products_and_services.description", rec["products_and_services"]["description"])
        for i, f in enumerate(rec["products_and_services"]["items"]):
            add(f"products_and_services.items[{i}]", f)
        for k, f in rec.get("custom_fields", {}).items():
            add(f"custom_fields.{k}", f)
        widths = [min(max(len(r[c]) for r in rows), 48) for c in range(5)]
        table = "\n".join("  ".join(r[c][:widths[c]].ljust(widths[c]) for c in range(5)).rstrip() for r in rows)
        out = [f"{rec['merchant_id']}  record_status: {rec['record_status']}  "
               f"{'(unsaved changes)' if rec['merchant_id'] in self.dirty else '(no unsaved changes)'}", table]
        open_c = [c for c in rec["conflicts"] if c["resolution"]["state"] == "open"]
        if open_c:
            out.append("\nOpen conflicts:")
            for c in open_c:
                out.append(f"  {c['conflict_id']} {c['field_path']}: kept {_show(c['current_value'])} "
                           f"({c['current_status']}); competing: "
                           + "; ".join(f"{_show(x['value'])} [{x['source_document']}]" for x in c["candidates"]))
        return "\n".join(out)

    def cmd_show_missing_fields(self, rest: str) -> str:
        rec, _ = self._target(rest)
        lines = []
        for label, f in R.needed_fields(rec):
            if f["status"] in ("missing", "conflict", "needs_review"):
                hint = {"missing": "provide a value", "conflict": "resolve with UPDATE FIELD",
                        "needs_review": "check and confirm or correct"}[f["status"]]
                lines.append(f"  {label}: {f['status']} — {hint}")
        legal = rec["business_information"]["legal_business_name"]
        if rec["business_entity_type"]["value"] == R.SOLE and legal["value"] is None:
            lines.append("  note: legal_business_name is missing (the DBA counts toward the business-name need "
                         "for a sole proprietorship).")
        if not lines:
            return f"{rec['merchant_id']}: no missing fields."
        return f"{rec['merchant_id']} (record status {rec['record_status']}):\n" + "\n".join(lines)

    def cmd_save_merchant(self, rest: str) -> str:
        rec, _ = self._target(rest)
        try:
            res = store.save_record(rec, self.data_dir,
                                    lambda p: self.confirm(f"{p} already exists. Overwrite?"))
        except store.StoreError as e:
            return f"NOT saved: {e}"
        if not res.saved:
            return f"NOT saved: {res.reason} ({res.path})."
        self.dirty.discard(rec["merchant_id"])
        return f"Saved {rec['merchant_id']} to {res.path} ({res.size} bytes; read back and verified)."

    def cmd_load_merchant(self, rest: str) -> str:
        target = rest.strip()
        if not target:
            raise CommandError("Use: LOAD MERCHANT <merchant_id or file path>")
        try:
            rec, path = store.load_record(target, self.data_dir)
        except store.StoreError as e:
            return f"NOT loaded: {e}"
        mid = rec["merchant_id"]
        if mid in self.records:
            extra = " It has unsaved changes." if mid in self.dirty else ""
            if not self.confirm(f"{mid} is already in this session.{extra} Replace it with the file?"):
                return f"NOT loaded: {mid} was kept as it is in the session."
        self.records[mid] = rec
        self.active = mid
        self.dirty.discard(mid)
        return f"Loaded {mid} from {path} (active). Record status: {rec['record_status']}."

    def cmd_export_csv(self, rest: str) -> str:
        arg = rest.strip()
        if arg.upper() == "ALL":
            recs = list(self.records.values())
            if not recs:
                raise CommandError("There are no records in this session.")
        else:
            recs = [self._target(arg)[0]]
        now = self.now()
        path = self.data_dir / "exports" / f"merchants_{now.strftime('%Y%m%d-%H%M%S')}.csv"
        try:
            n = store.write_text_atomic(path, csv_export.render_csv(recs))
        except store.StoreError as e:
            return f"NOT exported: {e}"
        return f"Exported {len(recs)} record(s) to {path} ({n} bytes)."

    def cmd_clear_session(self, rest: str) -> str:
        unsaved = sorted(self.dirty & set(self.records))
        if unsaved and not self.confirm("Unsaved records will be lost: " + ", ".join(unsaved) + ". Clear anyway?"):
            return "Session not cleared."
        n = len(self.records)
        self.records.clear()
        self.dirty.clear()
        self.active = None
        return f"Session cleared ({n} record(s) removed from memory). No files were deleted."
