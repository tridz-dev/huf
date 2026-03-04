import { useEffect, useState } from 'react';
import { ShieldCheck, Lock } from 'lucide-react';
import { getHufRoles, type HufRole } from '@/services/permissionsApi';
import { Badge } from '@/components/ui/badge';

// ---------------------------------------------------------------------------
// Capability category groupings for display
// ---------------------------------------------------------------------------

const CATEGORY_ORDER = [
  { key: 'agent', label: 'Agents' },
  { key: 'chat', label: 'Chat' },
  { key: 'knowledge', label: 'Knowledge' },
  { key: 'tools', label: 'Tools' },
  { key: 'flows', label: 'Flows' },
  { key: 'system', label: 'System' },
  { key: 'users', label: 'Users' },
  { key: 'roles', label: 'Roles' },
];

function groupCapabilities(caps: string[]): Record<string, string[]> {
  const groups: Record<string, string[]> = {};
  for (const cap of caps) {
    const prefix = cap.split('.')[0];
    if (!groups[prefix]) groups[prefix] = [];
    groups[prefix].push(cap);
  }
  return groups;
}

// ---------------------------------------------------------------------------
// Role card
// ---------------------------------------------------------------------------

function RoleCard({ role }: { role: HufRole }) {
  const groups = groupCapabilities(role.capabilities);

  return (
    <div className="border rounded-lg p-4 space-y-3">
      {/* Header */}
      <div className="flex items-center gap-2">
        <span className="font-semibold text-base">{role.role_name}</span>
        {role.is_system_role === 1 && (
          <span className="inline-flex items-center gap-1 text-xs text-muted-foreground">
            <Lock className="h-3 w-3" />
            System
          </span>
        )}
      </div>

      {role.description && (
        <p className="text-sm text-muted-foreground">{role.description}</p>
      )}

      {/* Capabilities grouped by category */}
      <div className="space-y-2">
        {CATEGORY_ORDER.filter((cat) => groups[cat.key]?.length).map((cat) => (
          <div key={cat.key}>
            <div className="text-xs font-medium text-muted-foreground mb-1">{cat.label}</div>
            <div className="flex flex-wrap gap-1">
              {groups[cat.key].map((cap) => (
                <Badge key={cap} variant="secondary" className="text-xs font-mono">
                  {cap}
                </Badge>
              ))}
            </div>
          </div>
        ))}
      </div>

      {role.capabilities.length === 0 && (
        <p className="text-xs text-muted-foreground italic">No capabilities assigned.</p>
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Page
// ---------------------------------------------------------------------------

export function RolesPage() {
  const [roles, setRoles] = useState<HufRole[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    getHufRoles()
      .then(setRoles)
      .finally(() => setLoading(false));
  }, []);

  return (
    <div className="p-6 max-w-5xl mx-auto">
      <div className="mb-6">
        <h1 className="text-2xl font-semibold flex items-center gap-2">
          <ShieldCheck className="h-6 w-6" />
          Roles
        </h1>
        <p className="text-sm text-muted-foreground mt-1">
          View capability sets granted to each Huf role. System roles cannot be deleted.
        </p>
      </div>

      {loading ? (
        <div className="text-sm text-muted-foreground py-12 text-center">Loading…</div>
      ) : (
        <div className="grid gap-4 sm:grid-cols-2">
          {roles.map((role) => (
            <RoleCard key={role.role_name} role={role} />
          ))}
        </div>
      )}
    </div>
  );
}
