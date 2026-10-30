import { describe, expect, it } from 'vitest';
import vectors from './condition_vectors.json';
import { canonicalModel, compileCondition, pyString, referenceExpression } from './compile';
import { parseCondition } from './parse';
import { describeCondition } from './sentence';
import { OPERATORS } from './operators';
import type { ConditionModel, Operand, OperatorId, Rule, ScalarOperand } from './types';

const model = (m: unknown) => m as ConditionModel;

describe('golden vectors (the same file the Python tests read)', () => {
  for (const v of vectors.vectors) {
    it(`compiles: ${v.name}`, () => {
      expect(compileCondition(model(v.model))).toBe(v.expression);
    });
    it(`reads back: ${v.name}`, () => {
      expect(parseCondition(v.expression)).toEqual(canonicalModel(model(v.model)));
    });
  }
  for (const v of vectors.compile_only) {
    it(`compiles (compile only): ${v.name}`, () => {
      expect(compileCondition(model(v.model))).toBe(v.expression);
    });
  }
  for (const source of vectors.hand_written_not_rules) {
    it(`does not turn a hand-written check into rules: ${source}`, () => {
      expect(parseCondition(source)).toBeNull();
    });
  }
});

describe('parseCondition', () => {
  it('an empty text is an empty set of rules', () => {
    expect(parseCondition('')).toEqual({ match: 'all', items: [] });
    expect(parseCondition('   ')).toEqual({ match: 'all', items: [] });
  });
  it('reads other spacing, double quotes and extra brackets around a whole check', () => {
    expect(parseCondition('input["status"]=="Paid"')).toEqual({ match: 'all', items: [{ type: 'rule', field: 'input.status', op: 'is', value: { kind: 'text', text: 'Paid' } }] });
    expect(parseCondition("  input['a']   >  5 ")?.items).toHaveLength(1);
  });
  it('keeps a hand-written plain number comparison as it is (no number() added)', () => {
    const m = parseCondition("input['amount'] > 100") as ConditionModel;
    expect(m.items[0]).toEqual({ type: 'rule', field: 'input.amount', op: 'gt', value: { kind: 'number', text: '100' } });
    expect(compileCondition(m)).toBe("input['amount'] > 100");
  });
  it('is not fooled by a text value that looks like code', () => {
    const m = parseCondition(`input['a'] == '\\' or True or \\''`) as ConditionModel;
    expect(m.items).toHaveLength(1);
    expect((m.items[0] as Rule).value).toEqual({ kind: 'text', text: "' or True or '" });
  });
  it('rejects broken or hostile text without throwing', () => {
    for (const s of ["input['a'] ==", "input['a'", "((", "'unterminated", "input['a'] == 'x' and", "x.__class__", "input['a'] == 007", "input['a'] == 1e3", "__import__('os')", "input['a'][b] == 1", "lambda: 1", "input['a'] == 'x'; 1"]) {
      expect(parseCondition(s), s).toBeNull();
    }
  });
});

describe('pyString / referenceExpression', () => {
  it('escapes what would break a literal', () => {
    expect(pyString("it's")).toBe("'it\\'s'");
    expect(pyString('a\\b')).toBe("'a\\\\b'");
    expect(pyString('a\nb')).toBe("'a\\nb'");
    expect(pyString('\u0000')).toBe("'\\x00'");
    expect(pyString('日本 😀')).toBe("'日本 😀'");
  });
  it('writes a path the way the evaluator reads it', () => {
    expect(referenceExpression('input.customer.name')).toBe("input['customer']['name']");
    expect(referenceExpression('n1.items[0].sku')).toBe("n1['items'][0]['sku']");
    expect(referenceExpression("input['a']")).toBeNull();
    expect(referenceExpression("input.a'] or True or input['b")).toBeNull();
  });
});

// ---- property-style round trip: a seeded random generator, so a failure is reproducible ----

function rng(seed: number) {
  let s = seed >>> 0;
  return () => {
    s = (Math.imul(s, 1664525) + 1013904223) >>> 0;
    return s / 4294967296;
  };
}

const NASTY = ["Paid", "it's", 'say "hi"', 'back\\slash', "\\", "'", "a\nb", "tab\t", "' or True or '", "日本語", "😀", "", " lead", "UPPER lower", "x\u0001y", "100", "0", "-5", "2.50", "007", "1e3", "{x}", "%s", "a and b", "a == b", "not (x)", "]", "[", "input['a']"];
const PATHS = ['input.amount', 'input.customer.name', 'trigger.x', 'n_http.items[0].sku', 'foreach.item.price', 'foreach.index', 'n1.a.b[2].c', 'input'];
const NUMS = ['0', '1', '100', '-2', '2.5', '0.5', '-0.5', '12345678901234567890'];

function generate(r: () => number): ConditionModel {
  const pick = <T,>(xs: T[]): T => xs[Math.floor(r() * xs.length)];
  const scalar = (): ScalarOperand => (r() < 0.4 ? { kind: 'number', text: pick(NUMS) } : { kind: 'text', text: pick(NASTY) });
  const operand = (op: OperatorId): Operand | undefined => {
    const info = OPERATORS.find((o) => o.id === op)!;
    if (info.value === 'none') return r() < 0.2 ? scalar() : undefined;
    if (info.value === 'many') return { kind: 'list', items: Array.from({ length: Math.floor(r() * 4) }, scalar) };
    const x = r();
    return x < 0.15 ? { kind: 'ref', ref: pick(PATHS) } : scalar();
  };
  const rule = (): Rule => {
    const op = pick(OPERATORS).id;
    return { type: 'rule', field: r() < 0.05 ? '' : pick(PATHS), op, value: operand(op), numeric: r() < 0.5, ignoreCase: r() < 0.5, id: 'x', raw: 'typed' };
  };
  const count = Math.floor(r() * 4);
  return {
    match: r() < 0.5 ? 'all' : 'any',
    items: Array.from({ length: count }, () => (r() < 0.25 ? { type: 'group' as const, match: r() < 0.5 ? ('all' as const) : ('any' as const), items: Array.from({ length: Math.floor(r() * 3) }, rule) } : rule())),
  };
}

describe('round trip (property style)', () => {
  it('model -> text -> model gives the canonical model, and text -> model -> text gives the same text', () => {
    const r = rng(20261030);
    let compiled = 0;
    for (let i = 0; i < 4000; i++) {
      const m = generate(r);
      const text = compileCondition(m);
      if (!text) {
        expect(canonicalModel(m).items).toHaveLength(0);
        continue;
      }
      compiled++;
      const back = parseCondition(text);
      expect(back, text).toEqual(canonicalModel(m));
      expect(compileCondition(back as ConditionModel), text).toBe(text);
    }
    expect(compiled).toBeGreaterThan(2000);
  });

  it('any text the parser accepts compiles back to the same tokens (never rewrites)', () => {
    const r = rng(7);
    const pool = ["input['a']", "lower(input['a'])", "number(input['a'])", "'x'", '"x"', '5', '-5', 'None', 'True', '[1, 2]', "[None, '', [], {}]", "n1['b'][0]", '(', ')', ' and ', ' or ', 'not ', ' in ', ' not in ', ' == ', ' != ', ' > ', ' < ', 'startswith(', 'endswith(', ',', ' '];
    let accepted = 0;
    for (let i = 0; i < 20000; i++) {
      const text = Array.from({ length: 1 + Math.floor(r() * 7) }, () => pool[Math.floor(r() * pool.length)]).join('');
      const m = parseCondition(text);
      if (m && m.items.length) {
        accepted++;
        const again = compileCondition(m);
        expect(parseCondition(again)).toEqual(m);
      }
    }
    expect(accepted).toBeGreaterThan(50);
  });

  it('a value can never change the structure of the text', () => {
    const r = rng(99);
    for (let i = 0; i < 500; i++) {
      const raw = Array.from({ length: Math.floor(r() * 12) }, () => "'\\\" \n\t)(]or and==".charAt(Math.floor(r() * 18))).join('') || 'x';
      const m: ConditionModel = { match: 'all', items: [{ type: 'rule', field: 'input.a', op: 'is', value: { kind: 'text', text: raw } }] };
      const back = parseCondition(compileCondition(m));
      expect(back?.items).toHaveLength(1);
      expect((back?.items[0] as Rule).value).toEqual({ kind: 'text', text: raw });
    }
  });
});

describe('sentence', () => {
  const label = (ref: string) => ({ 'input.amount': 'Amount', 'input.status': 'Status', 'input.limit': 'Limit' }[ref] ?? ref);
  it('reads like a sentence', () => {
    const m = parseCondition("number(input['amount']) > 100 and input['status'] == 'Paid'") as ConditionModel;
    expect(describeCondition(m, label)).toBe('Amount is more than 100 and Status is Paid');
  });
  it('says any / groups / empty / lists / other fields', () => {
    expect(describeCondition(parseCondition("input['status'] in ['Paid', 'Shipped'] or input['amount'] <= 5") as ConditionModel, label)).toBe('Status is one of Paid or Shipped or Amount is at most 5');
    expect(describeCondition(parseCondition("input['amount'] > 1 and (input['status'] == 'a' or input['status'] == 'b')") as ConditionModel, label)).toBe('Amount is more than 1 and (Status is a or Status is b)');
    expect(describeCondition(parseCondition("number(input['amount']) > number(input['limit'])") as ConditionModel, label)).toBe('Amount is more than Limit');
    expect(describeCondition(parseCondition("input['status'] in [None, '', [], {}]") as ConditionModel, label)).toBe('Status is empty');
    expect(describeCondition({ match: 'all', items: [] }, label)).toBeNull();
  });
});
