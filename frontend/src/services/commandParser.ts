export type CommandDomain = 'flow' | 'agent' | 'users' | 'knowledge' | 'runs' | 'cost' | 'realm';

export interface CommandQualifier {
  key: string;
  value: string;
}

export interface ParsedCommand {
  raw: string;
  routingMode: 'domain' | 'explicit-agent';
  domain: CommandDomain;
  verb: string;
  objectPhrase: string;
  qualifiers: CommandQualifier[];
}

const SUPPORTED_DOMAINS: CommandDomain[] = ['flow', 'agent', 'users', 'knowledge', 'runs', 'cost', 'realm'];
const QUALIFIER_KEYS = new Set(['for', 'in', 'as', 'since', 'by', 'with', 'from', 'to']);
const VERB_ALIASES: Record<string, string> = {
  make: 'create',
  new: 'create',
  del: 'delete',
  rm: 'remove',
  ls: 'list',
};

function normalizeVerb(verb: string): string {
  const lowerVerb = verb.toLowerCase();
  return VERB_ALIASES[lowerVerb] ?? lowerVerb;
}

function parseParts(tokens: string[]): { objectPhrase: string; qualifiers: CommandQualifier[] } {
  const qualifiers: CommandQualifier[] = [];
  const objectTokens: string[] = [];

  let i = 0;
  while (i < tokens.length) {
    const token = tokens[i].toLowerCase();

    if (QUALIFIER_KEYS.has(token)) {
      const key = token;
      const valueTokens: string[] = [];
      i += 1;

      while (i < tokens.length && !QUALIFIER_KEYS.has(tokens[i].toLowerCase())) {
        valueTokens.push(tokens[i]);
        i += 1;
      }

      qualifiers.push({
        key,
        value: valueTokens.join(' ').trim(),
      });
      continue;
    }

    objectTokens.push(tokens[i]);
    i += 1;
  }

  return {
    objectPhrase: objectTokens.join(' ').trim(),
    qualifiers,
  };
}

/**
 * Parse slash commands in Hub Simple home.
 * Supports:
 * - /flow create approval for todo
 * - /agent:users add Sarah as builder in realm ops
 */
export function parseSlashCommand(rawInput: string): ParsedCommand {
  const raw = rawInput.trim();

  if (!raw.startsWith('/')) {
    throw new Error('Command must start with /.');
  }

  const withoutSlash = raw.slice(1).trim();
  const tokens = withoutSlash.split(/\s+/).filter(Boolean);

  if (tokens.length < 2) {
    throw new Error('Command must include a domain and verb. Example: /flow create approval for todo');
  }

  const commandHead = tokens[0].toLowerCase();
  const remainder = tokens.slice(1);

  let routingMode: ParsedCommand['routingMode'] = 'domain';
  let domainToken = commandHead;

  if (commandHead.startsWith('agent:')) {
    routingMode = 'explicit-agent';
    domainToken = commandHead.replace('agent:', '');
  }

  if (!SUPPORTED_DOMAINS.includes(domainToken as CommandDomain)) {
    throw new Error(`Unknown domain "${domainToken}". Try one of: ${SUPPORTED_DOMAINS.join(', ')}`);
  }

  const verb = normalizeVerb(remainder[0]);
  const { objectPhrase, qualifiers } = parseParts(remainder.slice(1));

  return {
    raw,
    routingMode,
    domain: domainToken as CommandDomain,
    verb,
    objectPhrase,
    qualifiers,
  };
}
