import { Fragment, type ReactNode } from 'react';
import { parseWhatsAppFormat, type FormatNode } from './whatsappFormat';
import type { PreviewVariables } from './previewModel';

const VAR_RE = /\{\{\s*([A-Za-z0-9_]+)\s*\}\}/g;
const OPEN = '';
const CLOSE = '';
const SENTINEL_RE = /(\d+)/g;

function lookup(samples: PreviewVariables | undefined, key: string): string | undefined {
  const value = Array.isArray(samples)
    ? /^\d+$/.test(key)
      ? (samples as readonly string[])[Number(key) - 1]
      : undefined
    : (samples as Record<string, string> | undefined)?.[key];
  return value?.trim() ? value : undefined;
}

function Chip({ name }: { name: string }) {
  return (
    <span className="rounded-sm bg-signal/15 px-1 font-mono text-[0.85em] text-signal-ink">{`{{${name}}}`}</span>
  );
}

function renderNodes(nodes: FormatNode[], vars: string[], samples: PreviewVariables | undefined): ReactNode {
  return nodes.map((n, i) => {
    if (n.kind === 'text' || n.kind === 'mono') {
      const content = splitVars(n.value, vars, samples);
      return n.kind === 'mono' ? (
        <code key={i} className="font-mono text-[0.9em]">{content}</code>
      ) : (
        <Fragment key={i}>{content}</Fragment>
      );
    }
    const children = renderNodes(n.children, vars, samples);
    if (n.kind === 'bold') return <strong key={i}>{children}</strong>;
    if (n.kind === 'italic') return <em key={i}>{children}</em>;
    return <s key={i}>{children}</s>;
  });
}

function splitVars(text: string, vars: string[], samples: PreviewVariables | undefined): ReactNode[] {
  const parts: ReactNode[] = [];
  let last = 0;
  for (const m of text.matchAll(SENTINEL_RE)) {
    parts.push(text.slice(last, m.index));
    const name = vars[Number(m[1])];
    const value = lookup(samples, name);
    parts.push(value !== undefined ? value : <Chip key={m.index} name={name} />);
    last = m.index + m[0].length;
  }
  parts.push(text.slice(last));
  return parts;
}

/** WhatsApp-formatted text as React nodes. Never HTML; newlines kept; URLs stay plain text. */
export function FormattedText({ text, samples, className }: { text: string; samples?: PreviewVariables; className?: string }) {
  const vars: string[] = [];
  const masked = text.replace(/[]/g, '').replace(VAR_RE, (_, name: string) => {
    vars.push(name);
    return `${OPEN}${vars.length - 1}${CLOSE}`;
  });
  return (
    <p dir="auto" className={className}>
      {renderNodes(parseWhatsAppFormat(masked), vars, samples)}
    </p>
  );
}
