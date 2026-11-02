import { describe, expect, it } from 'vitest';
import { jsonFromRows, problemWithRows, rowsFromJsonText, rowsFromStored } from './skillSources';

describe('skill sources', () => {
  it('always lists the official source and merges what is stored', () => {
    const rows = rowsFromStored(JSON.stringify({ mine: { repo_url: 'https://github.com/a/b', path: 'x' } }));
    expect(rows.map((r) => r.name)).toEqual(['huf-skills', 'mine']);
    expect(rows[1]).toEqual({ name: 'mine', repo_url: 'https://github.com/a/b', path: 'x', ref: '' });
  });

  it('survives stored text that is not JSON', () => {
    expect(rowsFromStored('not json').map((r) => r.name)).toEqual(['huf-skills']);
    expect(rowsFromStored(null)).toHaveLength(1);
  });

  it('round-trips rows through JSON and drops empty optional fields', () => {
    const json = jsonFromRows([{ name: 'a', repo_url: ' https://x.y/z ', path: '', ref: 'dev' }]);
    expect(JSON.parse(json)).toEqual({ a: { repo_url: 'https://x.y/z', ref: 'dev' } });
  });

  it('says in words what is wrong with the rows', () => {
    expect(problemWithRows([{ name: '', repo_url: 'https://a.b', path: '', ref: '' }])).toBe('Source 1 needs a name.');
    expect(problemWithRows([{ name: 'a', repo_url: 'git@x', path: '', ref: '' }])).toContain('https://');
    expect(
      problemWithRows([
        { name: 'a', repo_url: 'https://a.b', path: '', ref: '' },
        { name: 'a', repo_url: 'https://c.d', path: '', ref: '' },
      ]),
    ).toContain('Two sources are called "a"');
    expect(problemWithRows([{ name: 'a', repo_url: 'https://a.b', path: '', ref: '' }])).toBeNull();
  });

  it('reports invalid hand-written JSON as a sentence', () => {
    const bad = rowsFromJsonText('{ nope');
    expect('error' in bad && bad.error).toContain('not valid JSON');
    expect('error' in rowsFromJsonText('[]')).toBe(true);
    const ok = rowsFromJsonText('{"a":{"repo_url":"https://a.b"}}');
    expect('rows' in ok && ok.rows[0].name).toBe('a');
  });
});
