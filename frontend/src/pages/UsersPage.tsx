import { useEffect, useMemo, useState } from 'react';
import { UserPlus, ChevronDown, Users } from 'lucide-react';
import { toast } from 'sonner';
import {
  getUsers,
  getHufRoles,
  inviteUser,
  updateUserRole,
  setUserEnabled,
  type HufUser,
  type HufRole,
} from '@/services/permissionsApi';
import { settleAll } from '@/lib/settleAll';
import { getFrappeErrorMessage } from '@/lib/frappe-error';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Badge } from '@/components/ui/badge';
import { PageFrame } from '@/layouts/PageFrame';
import { FilterBar, EmptyState } from '@/components/dashboard';
import { Switch } from '@/components/ui/switch';
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table';
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogFooter,
} from '@/components/ui/dialog';
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu';
import { useSaveShortcut } from '@/hooks/useSaveShortcut';

// ---------------------------------------------------------------------------
// Role badge colour map
// ---------------------------------------------------------------------------

const ROLE_COLOURS: Record<string, string> = {
  'Huf Admin': 'border-destructive/30 text-destructive bg-transparent',
  'Huf Manager': 'border-signal/30 text-signal bg-transparent',
  'Huf User': 'border-good/30 text-good bg-transparent',
  'Huf Viewer': 'border-steel text-steel-soft bg-paper-deep',
};

function roleBadgeClass(role: string): string {
  return ROLE_COLOURS[role] ?? 'border-line text-steel bg-transparent';
}

// ---------------------------------------------------------------------------
// Status helpers
// ---------------------------------------------------------------------------

type UserStatusFilter = 'all' | 'active' | 'disabled';

// ---------------------------------------------------------------------------
// Invite user dialog
// ---------------------------------------------------------------------------

interface InviteDialogProps {
  open: boolean;
  roles: HufRole[];
  onClose: () => void;
  onInvited: (user: HufUser) => void;
}

function InviteDialog({ open, roles, onClose, onInvited }: InviteDialogProps) {
  const [email, setEmail] = useState('');
  const [fullName, setFullName] = useState('');
  const [selectedRole, setSelectedRole] = useState('');
  const [busy, setBusy] = useState(false);

  const reset = () => {
    setEmail('');
    setFullName('');
    setSelectedRole('');
  };

  const handleSubmit = async () => {
    if (!email || !selectedRole) {
      toast.error('Email and role are required.');
      return;
    }
    setBusy(true);
    try {
      const created = await inviteUser(email.trim(), fullName.trim(), selectedRole);
      if (created) {
        onInvited(created as unknown as HufUser);
        toast.success(`${email} has been invited.`);
        reset();
        onClose();
      }
    } finally {
      setBusy(false);
    }
  };

  useSaveShortcut({
    onSave: handleSubmit,
    enabled: open,
    isSubmitting: busy,
    allowInDialog: true,
  });

  return (
    <Dialog open={open} onOpenChange={(v) => !v && onClose()}>
      <DialogContent className="sm:max-w-md">
        <DialogHeader>
          <DialogTitle>Invite user</DialogTitle>
        </DialogHeader>
        <div className="space-y-3 py-2">
          <div>
            <label className="text-sm font-medium mb-1 block">Email *</label>
            <Input
              placeholder="jane@example.com"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
            />
          </div>
          <div>
            <label className="text-sm font-medium mb-1 block">Full name</label>
            <Input
              placeholder="Jane Doe"
              value={fullName}
              onChange={(e) => setFullName(e.target.value)}
            />
          </div>
          <div>
            <label className="text-sm font-medium mb-1 block">Role *</label>
            <DropdownMenu>
              <DropdownMenuTrigger asChild>
                <Button variant="outline" className="w-full justify-between">
                  {selectedRole || 'Select a role'}
                  <ChevronDown className="h-4 w-4 opacity-50" />
                </Button>
              </DropdownMenuTrigger>
              <DropdownMenuContent className="w-full">
                {roles.map((r) => (
                  <DropdownMenuItem key={r.role_name} onSelect={() => setSelectedRole(r.role_name)}>
                    {r.role_name}
                  </DropdownMenuItem>
                ))}
              </DropdownMenuContent>
            </DropdownMenu>
          </div>
        </div>
        <DialogFooter>
          <Button variant="ghost" onClick={onClose}>
            Cancel
          </Button>
          <Button onClick={handleSubmit} disabled={busy}>
            {busy ? 'Inviting…' : 'Send invite'}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

// ---------------------------------------------------------------------------
// Main page
// ---------------------------------------------------------------------------

export default function UsersPage() {
  const [users, setUsers] = useState<HufUser[]>([]);
  const [roles, setRoles] = useState<HufRole[]>([]);
  const [loading, setLoading] = useState(true);
  const [showInvite, setShowInvite] = useState(false);
  const [search, setSearch] = useState('');
  const [statusFilter, setStatusFilter] = useState<UserStatusFilter>('all');

  const statusOptions = useMemo(
    () => [
      { label: 'All status', value: 'all' },
      { label: 'Active', value: 'active' },
      { label: 'Disabled', value: 'disabled' },
    ],
    [],
  );

  const load = async () => {
    setLoading(true);
    try {
      const errorLabels = ['users', 'roles'];
      const [u, r] = await settleAll([getUsers(), getHufRoles()], (index, error) => {
        toast.error(`Failed to load ${errorLabels[index]}: ${getFrappeErrorMessage(error)}`);
      });
      if (u) setUsers(u);
      if (r) setRoles(r);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    load();
  }, []);

  const handleRoleChange = async (user: string, newRole: string) => {
    const updated = await updateUserRole(user, newRole);
    if (updated) {
      setUsers((prev) => prev.map((u) => (u.user === user ? { ...u, huf_role: newRole } : u)));
      toast.success('Role updated.');
    }
  };

  const handleToggleEnabled = async (user: HufUser) => {
    const next = !user.enabled;
    const updated = await setUserEnabled(user.user, next);
    if (updated) {
      setUsers((prev) =>
        prev.map((u) => (u.user === user.user ? { ...u, enabled: next ? 1 : 0 } : u)),
      );
      toast.success(next ? 'User enabled.' : 'User disabled.');
    }
  };

  const filteredUsers = useMemo(() => {
    return users.filter((u) => {
      const matchesSearch =
        !search ||
        u.full_name?.toLowerCase().includes(search.toLowerCase()) ||
        u.email?.toLowerCase().includes(search.toLowerCase());

      let matchesStatus = true;
      if (statusFilter === 'active') {
        matchesStatus = !!u.enabled;
      } else if (statusFilter === 'disabled') {
        matchesStatus = !u.enabled;
      }

      return matchesSearch && matchesStatus;
    });
  }, [users, search, statusFilter]);

  return (
    <PageFrame
      subtitle="Manage who has access to Huf and what they can do."
      actions={
        <Button onClick={() => setShowInvite(true)}>
          <UserPlus className="h-4 w-4 mr-2" />
          Invite user
        </Button>
      }
      filters={
        <FilterBar
          searchPlaceholder="Search users..."
          searchValue={search}
          onSearchChange={setSearch}
          filters={[
            {
              label: 'Status',
              value: statusFilter,
              options: statusOptions,
              onChange: (value) => setStatusFilter(value as UserStatusFilter),
            },
          ]}
        />
      }
    >
      {loading ? (
        <div className="text-sm font-body text-steel-soft py-12 text-center">Loading…</div>
      ) : filteredUsers.length === 0 ? (
        <EmptyState
          icon={Users}
          title="No users"
          description="Invite a user to give them access to Huf."
          action={{ label: 'Invite user', onClick: () => setShowInvite(true) }}
        />
      ) : (
        <div className="overflow-x-auto border border-line bg-panel">
          <Table className="w-full min-w-[32rem] table-fixed text-sm">
            <TableHeader className="bg-paper-deep/50">
              <TableRow>
                <TableHead className="text-left px-3 py-2 font-medium sm:px-4 sm:py-3 w-[35%] sm:w-[32%]">
                  User
                </TableHead>
                <TableHead className="text-right px-3 py-2 font-medium sm:px-4 sm:py-3 w-[25%] sm:w-[26%]">
                  Role
                </TableHead>
                <TableHead className="text-right px-3 py-2 font-medium sm:px-4 sm:py-3 w-[20%] sm:w-[21%]">
                  Status
                </TableHead>
                <TableHead className="text-right px-3 py-2 font-medium sm:px-4 sm:py-3 w-[20%] sm:w-[21%]">
                  Actions
                </TableHead>
              </TableRow>
            </TableHeader>
            <TableBody className="divide-y">
              {filteredUsers.map((u) => (
                <TableRow key={u.user} className="hover:bg-paper-deep/20">
                  <TableCell className="min-w-0 px-3 py-2 sm:px-4 sm:py-3">
                    <div
                      className="font-medium truncate"
                      title={[u.full_name, u.email].filter(Boolean).join(' — ')}
                    >
                      {u.full_name || u.email}
                    </div>
                    <div className="text-xs text-steel-soft truncate">{u.email}</div>
                  </TableCell>
                  <TableCell className="min-w-0 px-3 py-2 sm:px-4 sm:py-3 text-right">
                    <DropdownMenu>
                      <DropdownMenuTrigger asChild>
                        <Button
                          variant="ghost"
                          className="ml-auto flex h-auto items-center gap-1 p-0 hover:bg-transparent hover:opacity-80"
                        >
                          <Badge className={roleBadgeClass(u.huf_role)}>{u.huf_role}</Badge>
                          <ChevronDown className="h-3 w-3 shrink-0 text-steel-soft" />
                        </Button>
                      </DropdownMenuTrigger>
                      <DropdownMenuContent>
                        {roles.map((r) => (
                          <DropdownMenuItem
                            key={r.role_name}
                            onSelect={() => handleRoleChange(u.user, r.role_name)}
                          >
                            {r.role_name}
                          </DropdownMenuItem>
                        ))}
                      </DropdownMenuContent>
                    </DropdownMenu>
                  </TableCell>
                  <TableCell className="min-w-0 px-3 py-2 sm:px-4 sm:py-3 text-right">
                    <Badge variant={u.enabled ? 'success' : 'secondary'}>
                      {u.enabled ? 'Active' : 'Disabled'}
                    </Badge>
                  </TableCell>
                  <TableCell className="px-3 py-2 sm:px-4 sm:py-3 text-right">
                    <Switch
                      checked={!!u.enabled}
                      onCheckedChange={() => handleToggleEnabled(u)}
                      aria-label={u.enabled ? 'Disable user' : 'Enable user'}
                    />
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </div>
      )}

      <InviteDialog
        open={showInvite}
        roles={roles}
        onClose={() => setShowInvite(false)}
        onInvited={(u) => setUsers((prev) => [u, ...prev])}
      />
    </PageFrame>
  );
}
