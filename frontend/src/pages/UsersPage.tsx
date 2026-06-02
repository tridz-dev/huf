import { useEffect, useMemo, useState } from 'react';
import { UserPlus, ChevronDown } from 'lucide-react';
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
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Badge } from '@/components/ui/badge';
import { FilterBar } from '@/components/dashboard';
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

// ---------------------------------------------------------------------------
// Role badge colour map
// ---------------------------------------------------------------------------

const ROLE_COLOURS: Record<string, string> = {
  'Huf Admin': 'bg-red-100 text-red-800',
  'Huf Manager': 'bg-blue-100 text-blue-800',
  'Huf User': 'bg-green-100 text-green-800',
  'Huf Viewer': 'bg-gray-100 text-gray-700',
};

function roleBadgeClass(role: string): string {
  return ROLE_COLOURS[role] ?? 'bg-purple-100 text-purple-800';
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
      { label: 'All Status', value: 'all' },
      { label: 'Active', value: 'active' },
      { label: 'Disabled', value: 'disabled' },
    ],
    [],
  );

  const load = async () => {
    setLoading(true);
    try {
      const [u, r] = await Promise.all([getUsers(), getHufRoles()]);
      setUsers(u);
      setRoles(r);
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
    <div className="flex flex-col h-full overflow-hidden p-6 gap-6">
      <div className="flex-none flex items-start justify-between">
        <div>
          <h1 className="text-2xl font-semibold tracking-tight">Users</h1>
          <p className="text-sm text-muted-foreground mt-1">Manage who has access to Huf and what they can do.</p>
        </div>
        <Button onClick={() => setShowInvite(true)}>
          <UserPlus className="h-4 w-4 mr-2" />
          Invite user
        </Button>
      </div>

      <div className="flex-none">
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
      </div>

      <div className="flex-1 overflow-auto">
        {loading ? (
          <div className="text-sm text-muted-foreground py-12 text-center">Loading…</div>
        ) : filteredUsers.length === 0 ? (
          <div className="text-sm text-muted-foreground py-12 text-center">No users found.</div>
        ) : (
          <div className="overflow-x-auto rounded-md border">
            <Table className="w-full min-w-[32rem] table-fixed text-sm">
              <TableHeader className="bg-muted/50">
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
                  <TableRow key={u.user} className="hover:bg-muted/20">
                    <TableCell className="min-w-0 px-3 py-2 sm:px-4 sm:py-3">
                      <div
                        className="font-medium truncate"
                        title={[u.full_name, u.email].filter(Boolean).join(' — ')}
                      >
                        {u.full_name || u.email}
                      </div>
                      <div className="text-xs text-muted-foreground truncate">{u.email}</div>
                    </TableCell>
                    <TableCell className="min-w-0 px-3 py-2 sm:px-4 sm:py-3 text-right">
                      <DropdownMenu>
                        <DropdownMenuTrigger asChild>
                          <button className="ml-auto flex items-center gap-1 hover:opacity-80">
                            <Badge className={roleBadgeClass(u.huf_role)}>{u.huf_role}</Badge>
                            <ChevronDown className="h-3 w-3 shrink-0 text-muted-foreground" />
                          </button>
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
                      <Badge variant={u.enabled ? 'default' : 'secondary'}>
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
      </div>

      <InviteDialog
        open={showInvite}
        roles={roles}
        onClose={() => setShowInvite(false)}
        onInvited={(u) => setUsers((prev) => [u, ...prev])}
      />
    </div>
  );
}
