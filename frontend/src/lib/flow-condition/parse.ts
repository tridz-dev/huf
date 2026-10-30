/**
 * Condition expression text -> rules, for the shapes `compile.ts` writes (and the same shapes typed by hand with other
 * spacing, quotes or redundant brackets). Anything else gives `null`: the builder then does not show it and the
 * text is kept exactly as it is.
 *
 * The one safety rule that keeps this honest: after reading the text into rules, the rules are compiled again and the
 * result must be the same sequence of tokens as the original text (spacing and quote style aside). If not, `null`.
 * So rules are only ever shown for text that means exactly what those rules mean; editing them can never change what
 * a hand-written check does without the person having asked for it.
 *
 * What is read (the grammar that round-trips):
 *   rule  := F == V | F != V | F > V | F < V | F >= V | F <= V           (V: text, number, or another field)
 *          | V in F | not (V in F) | startswith(F, V) | endswith(F, V)
 *          | F in [V, ...] | F not in [V, ...]                          (V: text or number)
 *          | F in [None, '', [], {}] | F not in [None, '', [], {}]      (is empty / is not empty)
 *          | F == True | F == False                                      (is yes / is no)
 *   F     := field | lower(field) | number(field)         field := input['a'][0]['b'], trigger[...], node_id[...], foreach['item'][...]
 *   items := rule (and rule)* | rule (or rule)*             one level of ( ... ) groups with and / or inside
 */
import { compileCondition, isNumberText, REF_RE } from './compile';
import type { ConditionModel, Group, Operand, OperatorId, Rule, ScalarOperand } from './types';

// ---- tokens ----

type Tok = { t: 'str'; v: string } | { t: 'num'; v: string } | { t: 'name'; v: string } | { t: 'p'; v: string };

const PUNCT = ['==', '!=', '>=', '<=', '>', '<', '(', ')', '[', ']', '{', '}', ',', '-'];

function tokenize(src: string): Tok[] | null {
  const out: Tok[] = [];
  let i = 0;
  while (i < src.length) {
    const ch = src[i];
    if (/\s/.test(ch)) {
      i++;
      continue;
    }
    if (ch === "'" || ch === '"') {
      let j = i + 1;
      let v = '';
      for (;;) {
        if (j >= src.length) return null;
        const c = src[j];
        if (c === ch) break;
        if (c === '\n') return null;
        if (c !== '\\') {
          v += c;
          j++;
          continue;
        }
        const e = src[j + 1];
        if (e === undefined) return null;
        const simple: Record<string, string> = { '\\': '\\', "'": "'", '"': '"', n: '\n', r: '\r', t: '\t' };
        if (e in simple) {
          v += simple[e];
          j += 2;
        } else if (e === 'x' && /^[0-9a-fA-F]{2}$/.test(src.slice(j + 2, j + 4))) {
          v += String.fromCharCode(parseInt(src.slice(j + 2, j + 4), 16));
          j += 4;
        } else if (e === 'u' && /^[0-9a-fA-F]{4}$/.test(src.slice(j + 2, j + 6))) {
          v += String.fromCharCode(parseInt(src.slice(j + 2, j + 6), 16));
          j += 6;
        } else return null;
      }
      out.push({ t: 'str', v });
      i = j + 1;
      continue;
    }
    const num = /^\d+(?:\.\d+)?/.exec(src.slice(i));
    if (num) {
      // `5abc` or `5.` is not a number we read.
      if (/^[A-Za-z_.]/.test(src.slice(i + num[0].length, i + num[0].length + 1))) return null;
      out.push({ t: 'num', v: num[0] });
      i += num[0].length;
      continue;
    }
    const name = /^[A-Za-z_][A-Za-z0-9_]*/.exec(src.slice(i));
    if (name) {
      out.push({ t: 'name', v: name[0] });
      i += name[0].length;
      continue;
    }
    const p = PUNCT.find((x) => src.startsWith(x, i));
    if (!p) return null;
    out.push({ t: 'p', v: p });
    i += p.length;
  }
  return out;
}

// ---- syntax tree ----

type Node =
  | { k: 'str'; v: string }
  | { k: 'num'; v: string }
  | { k: 'const'; v: 'True' | 'False' | 'None' }
  | { k: 'ref'; path: string }
  | { k: 'call'; fn: string; args: Node[] }
  | { k: 'list'; items: Node[] }
  | { k: 'dict' }
  | { k: 'cmp'; op: string; left: Node; right: Node }
  | { k: 'not'; operand: Node }
  | { k: 'bool'; op: 'and' | 'or'; values: Node[] }
  | { k: 'paren'; inner: Node };

const CALLS = new Set(['lower', 'number', 'startswith', 'endswith']);
const CMP = new Set(['==', '!=', '>', '<', '>=', '<=']);

class Parser {
  private pos = 0;
  constructor(private toks: Tok[]) {}
  private peek = () => this.toks[this.pos];
  private isP(v: string) {
    const t = this.peek();
    return !!t && t.t === 'p' && t.v === v;
  }
  private isName(v: string) {
    const t = this.peek();
    return !!t && t.t === 'name' && t.v === v;
  }
  private fail(): never {
    throw new SyntaxError('not rules');
  }
  parseAll(): Node {
    const n = this.or();
    if (this.pos !== this.toks.length) this.fail();
    return n;
  }
  private or(): Node {
    const values = [this.and()];
    while (this.isName('or')) {
      this.pos++;
      values.push(this.and());
    }
    return values.length > 1 ? { k: 'bool', op: 'or', values } : values[0];
  }
  private and(): Node {
    const values = [this.not()];
    while (this.isName('and')) {
      this.pos++;
      values.push(this.not());
    }
    return values.length > 1 ? { k: 'bool', op: 'and', values } : values[0];
  }
  private not(): Node {
    if (this.isName('not')) {
      this.pos++;
      return { k: 'not', operand: this.not() };
    }
    return this.cmp();
  }
  private cmp(): Node {
    const left = this.atom();
    let op: string | null = null;
    const t = this.peek();
    if (t?.t === 'p' && CMP.has(t.v)) {
      op = t.v;
      this.pos++;
    } else if (this.isName('in')) {
      op = 'in';
      this.pos++;
    } else if (this.isName('not') && this.toks[this.pos + 1]?.t === 'name' && (this.toks[this.pos + 1] as Tok).v === 'in') {
      op = 'not in';
      this.pos += 2;
    }
    if (!op) return left;
    const right = this.atom();
    const next = this.peek();
    // A chain (a < b < c) or a second comparison is not a rule.
    if (next && ((next.t === 'p' && CMP.has(next.v)) || (next.t === 'name' && (next.v === 'in' || next.v === 'not')))) this.fail();
    return { k: 'cmp', op, left, right };
  }
  private atom(): Node {
    const t = this.peek();
    if (!t) this.fail();
    if (t.t === 'str') {
      this.pos++;
      return { k: 'str', v: t.v };
    }
    if (t.t === 'num') {
      this.pos++;
      return { k: 'num', v: t.v };
    }
    if (t.t === 'p' && t.v === '-') {
      const n = this.toks[this.pos + 1];
      if (n?.t !== 'num') this.fail();
      this.pos += 2;
      return { k: 'num', v: `-${n.v}` };
    }
    if (t.t === 'p' && t.v === '(') {
      this.pos++;
      const inner = this.or();
      if (!this.isP(')')) this.fail();
      this.pos++;
      return { k: 'paren', inner };
    }
    if (t.t === 'p' && t.v === '[') {
      this.pos++;
      const items: Node[] = [];
      if (!this.isP(']')) {
        for (;;) {
          items.push(this.atom());
          if (this.isP(',')) {
            this.pos++;
            continue;
          }
          break;
        }
      }
      if (!this.isP(']')) this.fail();
      this.pos++;
      return { k: 'list', items };
    }
    if (t.t === 'p' && t.v === '{') {
      this.pos++;
      if (!this.isP('}')) this.fail();
      this.pos++;
      return { k: 'dict' };
    }
    if (t.t === 'name') {
      if (t.v === 'True' || t.v === 'False' || t.v === 'None') {
        this.pos++;
        return { k: 'const', v: t.v };
      }
      this.pos++;
      if (this.isP('(')) {
        if (!CALLS.has(t.v)) this.fail();
        this.pos++;
        const args: Node[] = [];
        for (;;) {
          args.push(this.or());
          if (this.isP(',')) {
            this.pos++;
            continue;
          }
          break;
        }
        if (!this.isP(')')) this.fail();
        this.pos++;
        return { k: 'call', fn: t.v, args };
      }
      return this.reference(t.v);
    }
    return this.fail();
  }
  /** `root['a'][0]['b']` -> a reference path. */
  private reference(root: string): Node {
    let path = root;
    while (this.isP('[')) {
      const a = this.toks[this.pos + 1];
      const b = this.toks[this.pos + 2];
      if (b?.t !== 'p' || b.v !== ']') this.fail();
      if (a?.t === 'str' && /^[A-Za-z_][A-Za-z0-9_]*$/.test(a.v)) path += `.${a.v}`;
      else if (a?.t === 'num' && /^\d+$/.test(a.v)) path += `[${a.v}]`;
      else this.fail();
      this.pos += 3;
    }
    return { k: 'ref', path };
  }
}

// ---- tree -> rules ----

type Side = { path: string; wrap: 'none' | 'lower' | 'number' };

function side(n: Node): Side | null {
  if (n.k === 'ref') return isRef(n.path) ? { path: n.path, wrap: 'none' } : null;
  if (n.k === 'call' && n.args.length === 1 && n.args[0].k === 'ref' && isRef(n.args[0].path)) {
    if (n.fn === 'lower') return { path: n.args[0].path, wrap: 'lower' };
    if (n.fn === 'number') return { path: n.args[0].path, wrap: 'number' };
  }
  return null;
}

/** `foreach['item']` reads as `foreach.item`; a reference must match the contract grammar. */
function isRef(path: string): boolean {
  return REF_RE.test(path);
}

function scalar(n: Node): ScalarOperand | null {
  // "Ignore capital letters" writes a typed text as lower('Text').
  if (n.k === 'call' && n.fn === 'lower' && n.args.length === 1 && n.args[0].k === 'str') return { kind: 'text', text: n.args[0].v };
  if (n.k === 'str') return { kind: 'text', text: n.v };
  if (n.k === 'num' && isNumberText(n.v)) return { kind: 'number', text: n.v };
  return null;
}

function operand(n: Node): Operand | null {
  const s = scalar(n);
  if (s) return s;
  const r = side(n);
  return r ? { kind: 'ref', ref: r.path } : null;
}

const SYMBOL_OP: Record<string, OperatorId> = { '==': 'is', '!=': 'is_not', '>': 'gt', '<': 'lt', '>=': 'gte', '<=': 'lte' };

const isEmptyList = (n: Node) =>
  n.k === 'list' && n.items.length === 4 && n.items[0].k === 'const' && n.items[0].v === 'None' && n.items[1].k === 'str' && n.items[1].v === '' &&
  n.items[2].k === 'list' && n.items[2].items.length === 0 && n.items[3].k === 'dict';

function withFlags(base: Rule, f: Side): Rule {
  const rule = { ...base };
  if (f.wrap === 'number') rule.numeric = true;
  if (f.wrap === 'lower') rule.ignoreCase = true;
  return rule;
}

function toRule(n: Node): Rule | null {
  if (n.k === 'not') {
    const inner = n.operand;
    if (inner.k !== 'paren' || inner.inner.k !== 'cmp' || inner.inner.op !== 'in') return null;
    const f = side(inner.inner.right);
    const v = operand(inner.inner.left);
    return f && v && v.kind !== 'list' ? withFlags({ type: 'rule', field: f.path, op: 'not_contains', value: v }, f) : null;
  }
  if (n.k === 'call' && (n.fn === 'startswith' || n.fn === 'endswith') && n.args.length === 2) {
    const f = side(n.args[0]);
    const v = operand(n.args[1]);
    return f && v ? withFlags({ type: 'rule', field: f.path, op: n.fn === 'startswith' ? 'starts_with' : 'ends_with', value: v }, f) : null;
  }
  if (n.k !== 'cmp') return null;
  if (n.op === 'in' || n.op === 'not in') {
    if (n.right.k === 'list') {
      const f = side(n.left);
      if (!f) return null;
      if (isEmptyList(n.right)) return f.wrap === 'none' ? { type: 'rule', field: f.path, op: n.op === 'in' ? 'is_empty' : 'is_not_empty' } : null;
      const items = n.right.items.map(scalar);
      if (!items.length || items.some((i) => !i)) return null;
      return withFlags({ type: 'rule', field: f.path, op: n.op === 'in' ? 'one_of' : 'none_of', value: { kind: 'list', items: items as ScalarOperand[] } }, f);
    }
    if (n.op === 'in') {
      const f = side(n.right);
      const v = operand(n.left);
      return f && v ? withFlags({ type: 'rule', field: f.path, op: 'contains', value: v }, f) : null;
    }
    return null;
  }
  const op = SYMBOL_OP[n.op];
  const f = side(n.left);
  if (!op || !f) return null;
  if (n.op === '==' && n.right.k === 'const' && (n.right.v === 'True' || n.right.v === 'False')) {
    return f.wrap === 'none' ? { type: 'rule', field: f.path, op: n.right.v === 'True' ? 'is_yes' : 'is_no' } : null;
  }
  const v = operand(n.right);
  return v ? withFlags({ type: 'rule', field: f.path, op, value: v }, f) : null;
}

function toItems(n: Node): Rule[] | null {
  const nodes = n.k === 'bool' ? n.values : [n];
  const rules = nodes.map(toRule);
  return rules.every(Boolean) ? (rules as Rule[]) : null;
}

function toModel(root: Node): ConditionModel | null {
  const nodes = root.k === 'bool' ? root.values : [root];
  const match = root.k === 'bool' && root.op === 'or' ? 'any' : 'all';
  const items: Array<Rule | Group> = [];
  for (const n of nodes) {
    if (n.k === 'paren') {
      const inner = toItems(n.inner);
      if (!inner) return null;
      items.push({ type: 'group', match: n.inner.k === 'bool' && n.inner.op === 'or' ? 'any' : 'all', items: inner });
    } else {
      const r = toRule(n);
      if (!r) return null;
      items.push(r);
    }
  }
  return { match, items };
}

const sameTokens = (a: Tok[], b: Tok[]) => a.length === b.length && a.every((t, i) => t.t === b[i].t && t.v === b[i].v);

/**
 * The rules an expression means, an empty model for an empty text, or `null` when the text is not in the shapes above
 * (it was written by hand). Never changes the text: it only reads it.
 */
export function parseCondition(expression: string): ConditionModel | null {
  if (typeof expression !== 'string') return null;
  if (!expression.trim()) return { match: 'all', items: [] };
  const original = tokenize(expression);
  if (!original) return null;
  let model: ConditionModel | null;
  try {
    model = toModel(new Parser(original).parseAll());
  } catch {
    return null;
  }
  if (!model || !model.items.length) return null;
  const again = tokenize(compileCondition(model));
  return again && sameTokens(original, again) ? model : null;
}
