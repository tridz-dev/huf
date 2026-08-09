import { useEffect, useMemo, useState } from 'react';
import { UserPlus, ChevronDown, Users, MoreVertical, Power } from 'lucide-react';
import { toast } from 'sonner';
import { cn } from '@/lib/utils';
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
import { Avatar, AvatarFallback } from '@/components/ui/avatar';
import { PageFrame } from '@/layouts/PageFrame';
import { FilterBar, EmptyState } from '@/components/dashboard';
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
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from '@/components/ui/alert-dialog';
import { useSaveShortcut } from '@/hooks/useSaveShortcut';

// ---------------------------------------------------------------------------
// Avatar colour helper
// ---------------------------------------------------------------------------

// Role names are identity, not alarm — every role renders in the same
// neutral pill (Badge's default/secondary variant). Only the avatar
// initials get a deterministic colour, derived from the person's name.
const AVATAR_COLOURS = [
  'bg-blue-100 text-blue-700',
  'bg-purple-100 text-purple-700',
  'bg-amber-100 text-amber-700',
  'bg-emerald-100 text-emerald-700',
  'bg-rose-100 text-rose-700',
  'bg-cyan-100 text-cyan-700',
  'bg-indigo-100 text-indigo-700',
  'bg-orange-100 text-orange-700',
];

function avatarColourClass(seed: string): string {
  let hash = 0;
  for (let i = 0; i < seed.length; i++) {
    hash = (hash * 31 + seed.charCodeAt(i)) | 0;
  }
  return AVATAR_COLOURS[Math.abs(hash) % AVATAR_COLOURS.length];
}

function initialsFor(name: string): string {
  const trimmed = name.trim();
  if (!trimmed) return '?';
  const parts = trimmed.split(/\s+/);
  if (parts.length === 1) return parts[0].slice(0, 2).toUpperCase();
  return (parts[0][0] + parts[parts.length - 1][0]).toUpperCase();
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

  const selectedRoleDescription = roles.find((r) => r.role_name === selectedRole)?.description;

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
      <DialogContent className="sm:max-w-[320px]">
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
            {selectedRoleDescription && (
              <p className="mt-1 text-[11px] text-steel-soft">{selectedRoleDescription}</p>
            )}
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

interface UsersPageProps {
  /**
   * True when rendered inside MembersPage's own PageFrame (the People/Roles
   * switcher already owns the page's single head bar there) — skip this
   * page's own PageFrame so /members never shows two head bars / two
   * titles, and render the search/status/invite toolbar as a plain row
   * instead.
   */
  embedded?: boolean;
}

export default function UsersPage({ embedded = false }: UsersPageProps) {
  const [users, setUsers] = useState<HufUser[]>([]);
  const [roles, setRoles] = useState<HufRole[]>([]);
  const [loading, setLoading] = useState(true);
  const [showInvite, setShowInvite] = useState(false);
  const [search, setSearch] = useState('');
  const [statusFilter, setStatusFilter] = useState<UserStatusFilter>('all');
  const [pendingToggleUser, setPendingToggleUser] = useState<HufUser | null>(null);
  const [togglingEnabled, setTogglingEnabled] = useState(false);

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

  const confirmToggleEnabled = async () => {
    if (!pendingToggleUser) return;
    setTogglingEnabled(true);
    try {
      await handleToggleEnabled(pendingToggleUser);
      setPendingToggleUser(null);
    } finally {
      setTogglingEnabled(false);
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

  const inviteAction = (
    <Button onClick={() => setShowInvite(true)}>
      <UserPlus className="h-4 w-4 mr-2" />
      Invite user
    </Button>
  );

  const toolbar = (
    <FilterBar
      searchPlaceholder="Search people"
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
      actions={embedded ? inviteAction : undefined}
    />
  );

  const body = (
    <>
      {loading ? (
        <div className="text-sm font-body text-steel-soft py-12 text-center">Loading…</div>
      ) : filteredUsers.length === 0 ? (
        search || statusFilter !== 'all' ? (
          <EmptyState
            variant="no-results"
            icon={Users}
            title="No users found"
            filterTerm={search}
            secondaryAction={{
              label: 'Clear filters',
              onClick: () => {
                setSearch('');
                setStatusFilter('all');
              },
            }}
          />
        ) : (
          <EmptyState
            variant="create"
            icon={Users}
            title="No users"
            description="Invite a user to give them access to Huf."
            action={{ label: 'Invite user', onClick: () => setShowInvite(true) }}
          />
        )
      ) : (
        <div className="overflow-x-auto border border-line bg-panel">
          <Table className="w-full min-w-[32rem] table-fixed text-sm">
            <TableHeader className="bg-paper-deep/50">
              <TableRow>
                <TableHead className="text-left px-3 py-2 font-mono text-[10px] uppercase tracking-widest text-steel-soft sm:px-4 sm:py-3 w-[35%] sm:w-[32%]">
                  User
                </TableHead>
                <TableHead className="text-right px-3 py-2 font-mono text-[10px] uppercase tracking-widest text-steel-soft sm:px-4 sm:py-3 w-[25%] sm:w-[26%]">
                  Role
                </TableHead>
                <TableHead className="text-right px-3 py-2 font-mono text-[10px] uppercase tracking-widest text-steel-soft sm:px-4 sm:py-3 w-[20%] sm:w-[21%]">
                  Status
                </TableHead>
                <TableHead className="text-right px-3 py-2 font-mono text-[10px] uppercase tracking-widest text-steel-soft sm:px-4 sm:py-3 w-[20%] sm:w-[21%]" aria-label="Actions">
                  <span className="sr-only">Actions</span>
                </TableHead>
              </TableRow>
            </TableHeader>
            <TableBody className="divide-y">
              {filteredUsers.map((u) => (
                <TableRow key={u.user} className="hover:bg-paper-deep/20">
                  <TableCell className="min-w-0 px-3 py-2 sm:px-4 sm:py-3">
                    <div className="flex items-center gap-2 min-w-0">
                      <Avatar className="h-[26px] w-[26px] shrink-0">
                        <AvatarFallback
                          className={avatarColourClass(u.full_name || u.email || u.user)}
                        >
                          <span className="text-[10px] font-medium">
                            {initialsFor(u.full_name || u.email || u.user)}
                          </span>
                        </AvatarFallback>
                      </Avatar>
                      <div className="min-w-0">
                        <div
                          className="font-medium truncate"
                          title={[u.full_name, u.email].filter(Boolean).join(' — ')}
                        >
                          {u.full_name || u.email}
                        </div>
                        <div className="text-xs text-steel-soft truncate">{u.email}</div>
                      </div>
                    </div>
                  </TableCell>
                  <TableCell className="min-w-0 px-3 py-2 sm:px-4 sm:py-3 text-right">
                    <DropdownMenu>
                      <DropdownMenuTrigger asChild>
                        <Button
                          variant="ghost"
                          className="ml-auto flex h-auto items-center gap-1 p-0 hover:bg-transparent hover:opacity-80"
                        >
                          <Badge variant="secondary">{u.huf_role}</Badge>
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
                    <span className="inline-flex items-center justify-end gap-1.5">
                      <span
                        className={cn(
                          'h-1.5 w-1.5 rounded-full flex-shrink-0',
                          u.enabled ? 'bg-good' : 'bg-steel-soft',
                        )}
                        aria-hidden
                      />
                      <span
                        className={cn(
                          'text-[13px]',
                          u.enabled ? 'text-ink' : 'text-steel',
                        )}
                      >
                        {u.enabled ? 'Active' : 'Disabled'}
                      </span>
                    </span>
                  </TableCell>
                  <TableCell className="px-3 py-2 sm:px-4 sm:py-3 text-right">
                    <DropdownMenu>
                      <DropdownMenuTrigger asChild>
                        <Button
                          variant="ghost"
                          size="icon"
                          className="ml-auto h-7 w-7 text-steel-soft hover:text-ink"
                          title="User actions"
                          aria-label="User actions"
                        >
                          <MoreVertical className="h-3.5 w-3.5" />
                        </Button>
                      </DropdownMenuTrigger>
                      <DropdownMenuContent align="end">
                        <DropdownMenuItem onSelect={() => setPendingToggleUser(u)}>
                          <Power className="h-3.5 w-3.5" />
                          {u.enabled ? 'Disable user' : 'Enable user'}
                        </DropdownMenuItem>
                      </DropdownMenuContent>
                    </DropdownMenu>
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

      <AlertDialog
        open={!!pendingToggleUser}
        onOpenChange={(next) => {
          if (!togglingEnabled && !next) setPendingToggleUser(null);
        }}
      >
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>
              {pendingToggleUser?.enabled ? 'Disable' : 'Enable'}{' '}
              {pendingToggleUser?.full_name || pendingToggleUser?.email}?
            </AlertDialogTitle>
            <AlertDialogDescription>
              {pendingToggleUser?.enabled
                ? 'This user will lose access to Huf immediately. They can be re-enabled at any time.'
                : 'This user will regain access to Huf with their existing role.'}
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel disabled={togglingEnabled}>Cancel</AlertDialogCancel>
            <AlertDialogAction onClick={confirmToggleEnabled} disabled={togglingEnabled}>
              {togglingEnabled
                ? 'Saving…'
                : pendingToggleUser?.enabled
                  ? 'Disable user'
                  : 'Enable user'}
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </>
  );

  if (embedded) {
    return (
      <div className="flex flex-col gap-4">
        {toolbar}
        {body}
      </div>
    );
  }

  return (
    <PageFrame actions={inviteAction} filters={toolbar}>
      {body}
    </PageFrame>
  );
}
