You help fill in US merchant application data from raw text. Read the TEXT below, then propose values only for fields that are actually stated in the text.

## Answer format

Answer ONLY with one JSON object, with no other text and no explanation:

{"candidates": [{"path": "...", "value": "...", "evidence": "..."}]}

- `path`: one path from the FIELD LIST below, exactly as written.
- `value`: the proposed value, as text.
- `evidence`: an EXACT quote from the TEXT (copied word for word, not paraphrased, not translated) that supports the value. At most 200 characters.
- One proposal per field. If nothing can be proposed, answer `{"candidates": []}`.

## Rules

1. Do not fill a field that is not in the text. An empty answer is better than a guess.
2. The `evidence` must appear exactly in the TEXT. A proposal without a matching quote is rejected by the program.
3. For a sole proprietorship: do not use the owner's name as the business name, unless the text names it as the business name.
4. Dates are US format (MM/DD/YYYY). An ambiguous date (for example 06/02/2004, which could be June 2 or February 6) is written as it appears and marked `"ambiguous": true`, for example: {"path": "...", "value": "06/02/2004", "evidence": "...", "ambiguous": true}.
5. Text marked [DISAMARKAN] is data that was deliberately hidden. Do not guess what it contains.
6. Use only paths from the FIELD LIST. Do not add other paths. Sensitive data (SSN, driver license, passport, bank account number) is not in the list and must not appear in the answer.

## FIELD LIST (path — value format)

{{ALLOWED_FIELDS}}

## TEXT

{{TEXT}}
