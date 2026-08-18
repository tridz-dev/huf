import { Fragment, useEffect, useMemo, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { ShieldCheck, Lock, Code2, ChevronRight, ChevronDown, Plus } from 'lucide-react';
import { getHufRoles, type HufRole } from '@/services/permissionsApi';
import {
  Table,
  TableHeader,
  TableBody,
  TableHead,
  TableRow,
  TableCell,
} from '@/components/ui/table';
import { Button } from '@/components/ui/button';
import { cn } from '@/lib/utils';

// ---------------------------------------------------------------------------
// Capability groups + level-word resolution
// ---------------------------------------------------------------------------
//
// The backend (`huf/permissions.py`) exposes capabilities as a flat
// `{capability: label}` catalogue with no built-in notion of "group" or
// "level" — that's a purely frontend read of the capability *names*
// themselves (e.g. "agent.create" implies a fuller level than "agent.use").
// This mapping is a frontend-only interpretation, not sourced from the
// backend, and should be revisited if new capability keys are added.

interface Level {
  /** Word shown in the cell, or null for "no access" (renders as em dash). */
  word: string | null;
  /** 'full' -> black text (higher/fuller level), 'partial' -> grey text. */
  tone: 'full' | 'partial';
}

const NONE: Level = { word: null, tone: 'partial' };

interface GroupDef {
  key: string;
  label: string;
  /** Capability key prefixes (e.g. "agent.") that belong to this group. */
  prefixes: string[];
  level: (caps: Set<string>) => Level;
}

/** Shared shape for the common "manage > create > use" capability families. */
function manageCreateUse(prefix: string) {
  return (caps: Set<string>): Level => {
    if (caps.has(`${prefix}.manage`)) return { word: 'Manage', tone: 'full' };
    if (caps.has(`${prefix}.create`)) return { word: 'Create', tone: 'partial' };
    if (caps.has(`${prefix}.use`)) return { word: 'Use', tone: 'partial' };
    return NONE;
  };
}

const GROUPS: GroupDef[] = [
  {
    key: 'agent',
    label: 'Agents',
    prefixes: ['agent.'],
    level: (caps) => {
      // agent.create / .edit / .delete are all "manage"-grade actions —
      // any one of them implies the role can fully manage agents.
      if (caps.has('agent.create') || caps.has('agent.edit') || caps.has('agent.delete')) {
        return { word: 'Manage', tone: 'full' };
      }
      if (caps.has('agent.view_all')) return { word: 'All', tone: 'partial' };
      if (caps.has('agent.use')) return { word: 'Use', tone: 'partial' };
      return NONE;
    },
  },
  {
    key: 'chat',
    label: 'Chat',
    prefixes: ['chat.'],
    level: (caps) => {
      if (caps.has('chat.view_all')) return { word: 'All', tone: 'full' };
      if (caps.has('chat.view_own')) return { word: 'Own', tone: 'partial' };
      if (caps.has('chat.use')) return { word: 'Use', tone: 'partial' };
      return NONE;
    },
  },
  {
    key: 'knowledge',
    label: 'Knowledge',
    prefixes: ['knowledge.'],
    level: manageCreateUse('knowledge'),
  },
  {
    key: 'tools',
    label: 'Tools',
    prefixes: ['tools.'],
    level: manageCreateUse('tools'),
  },
  {
    key: 'flows',
    label: 'Flows',
    prefixes: ['flows.'],
    level: manageCreateUse('flows'),
  },
  {
    key: 'data',
    label: 'Data records',
    prefixes: ['data.'],
    level: (caps) => {
      // data.tables.manage is schema-level admin — the fullest level.
      if (caps.has('data.tables.manage')) return { word: 'Manage', tone: 'full' };
      if (caps.has('data.records.edit_all')) return { word: 'Edit all', tone: 'full' };
      if (caps.has('data.records.edit_own')) return { word: 'Edit own', tone: 'partial' };
      if (caps.has('data.records.view_all')) return { word: 'All', tone: 'partial' };
      if (caps.has('data.records.view_own')) return { word: 'Own', tone: 'partial' };
      if (caps.has('data.records.create')) return { word: 'Create', tone: 'partial' };
      return NONE;
    },
  },
  {
    key: 'users_roles',
    label: 'Users & roles',
    prefixes: ['users.', 'roles.'],
    level: (caps) => {
      if (caps.has('users.manage') || caps.has('roles.manage')) {
        return { word: 'Manage', tone: 'full' };
      }
      if (caps.has('users.invite')) return { word: 'Invite', tone: 'partial' };
      return NONE;
    },
  },
  {
    key: 'system',
    label: 'System settings',
    prefixes: ['system.'],
    level: (caps) => {
      const keys = [
        'system.providers.manage',
        'system.models.manage',
        'system.mcp.manage',
        'system.integrations.manage',
        'system.settings.manage',
      ];
      const matched = keys.filter((k) => caps.has(k));
      if (matched.length === 0) return NONE;
      // Black text only once the role manages *every* system-settings
      // capability; a subset is still "Manage" (the only word that fits)
      // but rendered grey to signal it's partial.
      return { word: 'Manage', tone: matched.length === keys.length ? 'full' : 'partial' };
    },
  },
];

function capsForGroup(caps: string[], group: GroupDef): string[] {
  return caps.filter((c) => group.prefixes.some((p) => c.startsWith(p)));
}

// ---------------------------------------------------------------------------
// Page
// ---------------------------------------------------------------------------

interface RolesPageProps {
  /**
   * True when rendered inside MembersPage's own PageFrame (the People/Roles
   * switcher already owns the page's single head bar there) — skip this
   * page's own title/scroll wrapper so /members never shows two titles.
   */
  embedded?: boolean;
}

export default function RolesPage({ embedded = false }: RolesPageProps) {
  const navigate = useNavigate();
  const [roles, setRoles] = useState<HufRole[]>([]);
  const [loading, setLoading] = useState(true);
  const [expanded, setExpanded] = useState<Record<string, boolean>>({});

  useEffect(() => {
    getHufRoles()
      .then(setRoles)
      .finally(() => setLoading(false));
  }, []);

  const roleCapSets = useMemo(
    () => roles.map((role) => new Set(role.capabilities)),
    [roles],
  );

  function toggleExpanded(groupKey: string) {
    setExpanded((prev) => ({ ...prev, [groupKey]: !prev[groupKey] }));
  }

  const createRoleButton = (
    <Button size="sm" onClick={() => navigate('/roles/new')} className="shrink-0">
      <Plus className="h-4 w-4 mr-1.5" />
      Create role
    </Button>
  );

  const matrix = loading ? (
    <div className="text-sm text-steel-soft py-12 text-center">Loading…</div>
  ) : roles.length === 0 ? (
    <div className="text-sm text-steel-soft py-12 text-center">No roles found.</div>
  ) : (
    <div className="border border-line rounded-lg overflow-hidden">
      <Table>
        <TableHeader>
          <TableRow className="hover:bg-transparent">
            <TableHead className="w-[220px]">Capability</TableHead>
            {roles.map((role) => (
              <TableHead key={role.role_name} className="normal-case">
                <button
                  type="button"
                  onClick={() => navigate(`/roles/${encodeURIComponent(role.role_name)}`)}
                  className="inline-flex items-center gap-1 font-sans text-[12px] font-medium text-ink normal-case tracking-normal hover:text-signal-ink transition-colors"
                >
                  {role.role_name}
                  {role.is_system_role === 1 && (
                    <Lock className="h-3 w-3 text-steel-soft shrink-0" />
                  )}
                </button>
              </TableHead>
            ))}
          </TableRow>
        </TableHeader>
        <TableBody>
          {GROUPS.map((group) => {
            const rowKeysPerRole = roles.map((role) => capsForGroup(role.capabilities, group));
            const totalKeys = new Set(rowKeysPerRole.flat()).size;
            const isExpanded = !!expanded[group.key];

            return (
              <Fragment key={group.key}>
                <TableRow className="h-[34px]">
                  <TableCell className="py-0 align-middle">
                    <button
                      type="button"
                      onClick={() => toggleExpanded(group.key)}
                      className="inline-flex items-center gap-1 text-[13px] text-ink hover:text-signal-ink transition-colors"
                    >
                      {isExpanded ? (
                        <ChevronDown className="h-3 w-3 text-steel-soft shrink-0" />
                      ) : (
                        <ChevronRight className="h-3 w-3 text-steel-soft shrink-0" />
                      )}
                      {group.label}
                    </button>
                  </TableCell>
                  {roles.map((role, i) => {
                    const level = group.level(roleCapSets[i]);
                    return (
                      <TableCell key={role.role_name} className="py-0 align-middle text-[13px]">
                        {level.word ? (
                          <span className={cn(level.tone === 'full' ? 'text-ink' : 'text-steel')}>
                            {level.word}
                          </span>
                        ) : (
                          <span className="text-steel-soft/60">—</span>
                        )}
                      </TableCell>
                    );
                  })}
                </TableRow>

                {isExpanded && (
                  <TableRow className="bg-paper-deep hover:bg-paper-deep">
                    <TableCell colSpan={roles.length + 1} className="py-2.5">
                      <div className="flex items-start justify-between gap-4">
                        <div className="flex items-start gap-1.5 flex-1 min-w-0">
                          <Code2 className="h-3 w-3 text-steel-soft mt-0.5 shrink-0" />
                          <div className="flex flex-wrap gap-x-4 gap-y-1.5">
                            {roles.map((role, i) => {
                              const keys = rowKeysPerRole[i];
                              if (keys.length === 0) return null;
                              return (
                                <div key={role.role_name} className="min-w-0">
                                  <div className="font-mono text-[10px] uppercase tracking-widest text-steel-soft mb-0.5">
                                    {role.role_name}
                                  </div>
                                  <div className="font-mono text-[11px] text-steel space-x-1.5">
                                    {keys.map((key) => (
                                      <span key={key}>{key}</span>
                                    ))}
                                  </div>
                                </div>
                              );
                            })}
                            {totalKeys === 0 && (
                              <span className="text-[12px] text-steel-soft italic">
                                No permission keys assigned in this group.
                              </span>
                            )}
                          </div>
                        </div>
                        <span className="font-mono text-[11px] text-steel-soft shrink-0 whitespace-nowrap">
                          {totalKeys} {totalKeys === 1 ? 'key' : 'keys'}
                        </span>
                      </div>
                    </TableCell>
                  </TableRow>
                )}
              </Fragment>
            );
          })}
        </TableBody>
      </Table>
    </div>
  );

  if (embedded) {
    return (
      <div className="space-y-4">
        <div className="flex justify-end">{createRoleButton}</div>
        {matrix}
      </div>
    );
  }

  return (
    <div className="h-full overflow-auto">
      <div className="p-6 max-w-6xl mx-auto">
        <div className="mb-6 flex items-start justify-between gap-4">
          <div>
            <h1 className="font-display text-title text-ink flex items-center gap-2">
              <ShieldCheck className="h-6 w-6" />
              Roles
            </h1>
            <p className="text-sm text-steel-soft mt-1">
              Compare capability levels across Huf roles. System roles cannot be edited or deleted.
            </p>
          </div>
          {createRoleButton}
        </div>

        {matrix}
      </div>
    </div>
  );
}
