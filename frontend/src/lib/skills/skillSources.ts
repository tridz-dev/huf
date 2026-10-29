/** Skill sources: where skills can be imported from. Stored as a JSON object keyed by name; edited as a list. */

export interface SkillSourceRow {
  name: string;
  repo_url: string;
  path: string;
  ref: string;
}

export const DEFAULT_SKILL_SOURCES: Record<string, { repo_url: string; path?: string; ref?: string }> = {
  'huf-skills': { repo_url: 'https://github.com/tridz-dev/huf-skills', path: 'skills', ref: 'main' },
};

export const SKILL_SOURCES_EXAMPLE = JSON.stringify(
  { 'my-skills': { repo_url: 'https://github.com/your-team/your-skills', path: 'skills', ref: 'main' } },
  null,
  2,
);

/** The stored text (or nothing) as rows. The built-in source is always listed. */
export function rowsFromStored(value: string | null | undefined): SkillSourceRow[] {
  let parsed: Record<string, { repo_url?: string; path?: string; ref?: string }> = {};
  try {
    const raw = value ? JSON.parse(value) : {};
    if (raw && typeof raw === 'object' && !Array.isArray(raw)) parsed = raw;
  } catch {
    parsed = {};
  }
  const merged = { ...DEFAULT_SKILL_SOURCES, ...parsed };
  return Object.entries(merged).map(([name, v]) => ({
    name,
    repo_url: v?.repo_url ?? '',
    path: v?.path ?? '',
    ref: v?.ref ?? '',
  }));
}

export function jsonFromRows(rows: SkillSourceRow[]): string {
  const out: Record<string, { repo_url: string; path?: string; ref?: string }> = {};
  for (const row of rows) {
    const name = row.name.trim();
    if (!name) continue;
    out[name] = {
      repo_url: row.repo_url.trim(),
      ...(row.path.trim() ? { path: row.path.trim() } : {}),
      ...(row.ref.trim() ? { ref: row.ref.trim() } : {}),
    };
  }
  return JSON.stringify(out, null, 2);
}

/** A plain sentence for the first problem found, or null. */
export function problemWithRows(rows: SkillSourceRow[]): string | null {
  const seen = new Set<string>();
  for (const [index, row] of rows.entries()) {
    const where = row.name.trim() ? `"${row.name.trim()}"` : `Source ${index + 1}`;
    if (!row.name.trim()) return `Source ${index + 1} needs a name.`;
    if (seen.has(row.name.trim())) return `Two sources are called "${row.name.trim()}". Give each its own name.`;
    seen.add(row.name.trim());
    if (!/^https?:\/\/\S+$/i.test(row.repo_url.trim())) return `${where} needs a repository link that starts with https://.`;
  }
  return null;
}

/** Rows from JSON text typed by hand; a plain sentence describes what is wrong. */
export function rowsFromJsonText(text: string): { rows: SkillSourceRow[] } | { error: string } {
  let parsed: unknown;
  try {
    parsed = JSON.parse(text);
  } catch (error) {
    return { error: `This is not valid JSON yet: ${(error as Error).message}` };
  }
  if (typeof parsed !== 'object' || parsed === null || Array.isArray(parsed)) {
    return { error: 'It must be an object with one entry per source, like the example.' };
  }
  const rows: SkillSourceRow[] = [];
  for (const [name, v] of Object.entries(parsed as Record<string, unknown>)) {
    if (typeof v !== 'object' || v === null) return { error: `"${name}" must have a repo_url.` };
    const entry = v as Record<string, unknown>;
    rows.push({
      name,
      repo_url: typeof entry.repo_url === 'string' ? entry.repo_url : '',
      path: typeof entry.path === 'string' ? entry.path : '',
      ref: typeof entry.ref === 'string' ? entry.ref : '',
    });
  }
  return { rows };
}
