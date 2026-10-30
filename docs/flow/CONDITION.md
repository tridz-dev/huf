# Condition builder: rules <-> expression (UX-13)

A Condition step stores one string, `config.expression`. The side panel edits **rules** and writes that string; nothing else is stored, so a flow never needs the rules to run.

| Code | What |
|---|---|
| `frontend/src/lib/flow-condition/types.ts`, `operators.ts` | The rules model and the 16 operators |
| `compile.ts` | rules -> text (`compileCondition`), `canonicalModel` |
| `parse.ts` | text -> rules (`parseCondition`) |
| `infer.ts` | typed text -> number or text, per operator |
| `sentence.ts` | rules -> "Amount is more than 100 and Status is Paid" |
| `huf/ai/flow/support/condition/condition_compile.py` | The same compile in Python (tests; the engine does not need it) |
| `frontend/src/lib/flow-condition/condition_vectors.json` | Golden vectors read by both the vitest and the Python tests |
| `huf/ai/graph/expressions.py` | The evaluator: four helpers `number`, `lower`, `startswith`, `endswith` were added (the only calls it accepts) |

## Shapes (what round-trips)
`F` is a field (`input['a']['b']`, `n1['items'][0]['sku']`, `foreach['item']['x']`), `V` text, number or another field.

| Operator | Text |
|---|---|
| is / is not | `F == V` / `F != V` |
| is more than / less than / at least / at most | `F > V`, `F < V`, `F >= V`, `F <= V` |
| contains / does not contain | `V in F` / `not (V in F)` |
| starts with / ends with | `startswith(F, V)` / `endswith(F, V)` |
| is empty / is not empty | `F in [None, '', [], {}]` / `F not in [None, '', [], {}]` |
| is yes / is no | `F == True` / `F == False` |
| is one of / is none of | `F in [V1, V2]` / `F not in [V1, V2]` |

* "Compare as numbers" writes `number(F)` (and `number(V)` for other data): `"150"` from a form counts as 150, text that is no number never matches. It is on whenever the value typed looks like a number (not `007`, `1e3`, `1,000`).
* "Ignore capital letters" writes `lower(F)` and `lower('Text')`. Text only.
* Rules are joined with `and` (All of) or `or` (Any of). A group is `( ... )`, one level deep, written in brackets also when it holds one rule.
* Text values are written with `\\`, `\'`, `\n`, `\r`, `\t` and `\xNN` escapes, so a value can never change the meaning of the check.
* Missing data: `is not`, `does not contain`, `is none of`, `is empty` are Yes for missing data; every other operator is No.

## Never rewriting a hand-written check
`parseCondition` reads the text into rules and **compiles them again**; the result must be the same tokens as the original (spacing and quote style aside), else it answers `null`. So rules are only shown for text that means exactly what the rules mean. A check that does not pass (for example `input['vip'] and input['total'] >= 500`, or anything with `+`, `if`, nested groups, bare fields) opens in the "Write it yourself" box with "This was written by hand and can't be shown as rules" and stays byte for byte as it is. Switching between rules and text never writes anything; only editing a rule does.

An unfinished rule (no data chosen, or no value) is kept on screen but left out of the text. A step with no complete rule has no text and says "Add at least one rule". The text may be at most 500 characters (the schema limit): the builder warns when the rules do not fit.
