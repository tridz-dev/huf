import { type ReactNode, useEffect, useRef, useState } from 'react';
import { X } from 'lucide-react';
import { FieldHint } from '../../FieldHint';
import { Input } from '../../../ui/input';
import { Label } from '../../../ui/label';
import { type CheckedUser, checkFlowUsers, type FlowUser, searchFlowUsers } from '@/services/flow/formOptionsApi';
import { cn } from '@/lib/utils';

/**
 * The people who may decide an approval. Each one is picked from the people who exist: typing only searches, so a name
 * nobody has ("Administrtor") can never be added. A name saved earlier that nobody has now shows in red with what to do.
 */
export function ApproverUsersField({
  value, onChange, testId, Err, disabled,
}: {
  value: string[];
  onChange: (next: string[] | undefined) => void;
  testId: string;
  Err: ReactNode;
  disabled?: boolean;
}) {
  const [query, setQuery] = useState('');
  const [found, setFound] = useState<FlowUser[]>([]);
  const [open, setOpen] = useState(false);
  const [busy, setBusy] = useState(false);
  const [active, setActive] = useState(0);
  const [known, setKnown] = useState<Record<string, CheckedUser>>({});
  const seq = useRef(0);

  // Who the saved names are (and which of them nobody has).
  const key = value.join('\n');
  useEffect(() => {
    const todo = value.filter((v) => !(v in known));
    // Looking people up is for editors; a read-only viewer just sees the saved names.
    if (todo.length === 0 || disabled) return;
    let live = true;
    checkFlowUsers(todo)
      .then((rows) => live && setKnown((k) => ({ ...k, ...Object.fromEntries(rows.map((r, i) => [todo[i], r])) })))
      .catch(() => undefined);
    return () => { live = false; };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [key]);

  // Search as the person types (a short pause first).
  useEffect(() => {
    if (!open) return;
    const mine = ++seq.current;
    setBusy(true);
    const t = setTimeout(() => {
      searchFlowUsers(query)
        .then((rows) => mine === seq.current && (setFound(rows.filter((r) => !value.includes(r.name))), setActive(0)))
        .catch(() => mine === seq.current && setFound([]))
        .finally(() => mine === seq.current && setBusy(false));
    }, 180);
    return () => clearTimeout(t);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [query, open, key]);

  const add = (user: FlowUser) => {
    setKnown((k) => ({ ...k, [user.name]: { name: user.name, found: true, full_name: user.full_name } }));
    onChange([...value, user.name]);
    setQuery('');
    setActive(0);
  };
  const remove = (name: string) => onChange(value.filter((v) => v !== name).length ? value.filter((v) => v !== name) : undefined);
  const typed = query.trim();
  const nobody = open && !busy && typed !== '' && found.length === 0;
  const unknown = value.filter((v) => known[v] && !known[v].found);

  return (
    <div data-testid={testId}>
      <Label htmlFor="approver-users" size="sm">Who can approve</Label>
      {value.length > 0 && (
        <ul className="mb-1.5 flex flex-wrap gap-1.5" data-testid={`${testId}-chips`}>
          {value.map((name) => {
            const row = known[name];
            const bad = row && !row.found;
            return (
              <li key={name} className={cn('flex max-w-full items-center gap-1 rounded-full border px-2 py-0.5 text-xs', bad ? 'border-destructive/50 bg-destructive/10 text-destructive' : 'border-border bg-muted')} data-testid={`${testId}-chip-${name}`}>
                <span className="truncate">{bad ? name : row?.full_name && row.full_name !== name ? `${row.full_name} (${name})` : name}</span>
                {!disabled && (
                  <button type="button" aria-label={`Remove ${name}`} className="rounded-full p-0.5 hover:bg-foreground/10" data-testid={`${testId}-remove-${name}`} onClick={() => remove(name)}>
                    <X className="h-3 w-3" />
                  </button>
                )}
              </li>
            );
          })}
        </ul>
      )}
      {!disabled && (
        <div className="relative">
          <Input
            id="approver-users"
            data-testid={`${testId}-search`}
            role="combobox"
            aria-expanded={open}
            aria-controls={`${testId}-list`}
            aria-autocomplete="list"
            autoComplete="off"
            value={query}
            placeholder="Search people by name or email"
            onFocus={() => setOpen(true)}
            onBlur={() => setTimeout(() => setOpen(false), 150)}
            onChange={(e) => { setQuery(e.target.value); setOpen(true); }}
            onKeyDown={(e) => {
              if (e.key === 'ArrowDown') { e.preventDefault(); setActive((a) => Math.min(a + 1, found.length - 1)); }
              else if (e.key === 'ArrowUp') { e.preventDefault(); setActive((a) => Math.max(a - 1, 0)); }
              else if (e.key === 'Enter') { e.preventDefault(); if (found[active]) add(found[active]); }
              else if (e.key === 'Escape') setOpen(false);
            }}
          />
          {open && (found.length > 0 || nobody || busy) && (
            <ul id={`${testId}-list`} role="listbox" className="absolute z-20 mt-1 max-h-56 w-full overflow-auto rounded-md border border-border bg-popover p-1 text-sm shadow-md" data-testid={`${testId}-list`}>
              {found.map((u, i) => (
                <li key={u.name} role="option" aria-selected={i === active} className={cn('cursor-pointer rounded px-2 py-1.5', i === active && 'bg-accent')} data-testid={`${testId}-option-${u.name}`} onMouseDown={(e) => { e.preventDefault(); add(u); }}>
                  <div className="truncate">{u.full_name}</div>
                  {(u.email ?? u.name) !== u.full_name && <div className="truncate text-meta text-muted-foreground">{u.email ?? u.name}</div>}
                  {u.has_approver_role === false && <div className="text-meta text-muted-foreground" data-testid={`${testId}-norole-${u.name}`}>Has no approver role yet</div>}
                </li>
              ))}
              {busy && found.length === 0 && <li className="px-2 py-1.5 text-muted-foreground">Looking...</li>}
              {nobody && <li className="px-2 py-1.5 text-muted-foreground" data-testid={`${testId}-nobody`}>No one is called "{typed}". Check the spelling, or search by email.</li>}
            </ul>
          )}
        </div>
      )}
      {unknown.length > 0 && (
        <p role="alert" className="mt-1 text-meta text-destructive" data-testid={`${testId}-unknown`}>
          {unknown.length === 1 ? `No one is called "${unknown[0]}".` : `No one is called ${unknown.map((u) => `"${u}"`).join(' or ')}.`} Remove {unknown.length === 1 ? 'it' : 'them'} and pick the person from the list, or the approval request goes nowhere.
        </p>
      )}
      <FieldHint testId="flow-hint-approver-users">Only the people you pick can approve or reject. The first answer counts.</FieldHint>
      {Err}
    </div>
  );
}
