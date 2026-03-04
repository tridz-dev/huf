import { useEffect, useState } from 'react';
import { UserPlus, Shield, ToggleLeft, ToggleRight, ChevronDown } from 'lucide-react';
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

export function UsersPage() {
  const [users, setUsers] = useState<HufUser[]>([]);
  const [roles, setRoles] = useState<HufRole[]>([]);
  const [loading, setLoading] = useState(true);
  const [showInvite, setShowInvite] = useState(false);

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

  return (
    <div className="p-6 max-w-5xl mx-auto">
      {/* Header */}
      <div className="flex items-center justify-between mb-6">
        <div>
          <h1 className="text-2xl font-semibold flex items-center gap-2">
            <Shield className="h-6 w-6" />
            Users
          </h1>
          <p className="text-sm text-muted-foreground mt-1">
            Manage who has access to Huf and what they can do.
          </p>
        </div>
        <Button onClick={() => setShowInvite(true)}>
          <UserPlus className="h-4 w-4 mr-2" />
          Invite user
        </Button>
      </div>

      {/* Table */}
      {loading ? (
        <div className="text-sm text-muted-foreground py-12 text-center">Loading…</div>
      ) : users.length === 0 ? (
        <div className="text-sm text-muted-foreground py-12 text-center">No users found.</div>
      ) : (
        <div className="border rounded-lg overflow-hidden">
          <table className="w-full text-sm">
            <thead className="bg-muted/50">
              <tr>
                <th className="text-left px-4 py-3 font-medium">User</th>
                <th className="text-left px-4 py-3 font-medium">Role</th>
                <th className="text-left px-4 py-3 font-medium">Status</th>
                <th className="text-left px-4 py-3 font-medium">Actions</th>
              </tr>
            </thead>
            <tbody className="divide-y">
              {users.map((u) => (
                <tr key={u.user} className="hover:bg-muted/20">
                  <td className="px-4 py-3">
                    <div className="font-medium">{u.full_name || u.email}</div>
                    <div className="text-xs text-muted-foreground">{u.email}</div>
                  </td>
                  <td className="px-4 py-3">
                    <DropdownMenu>
                      <DropdownMenuTrigger asChild>
                        <button className="flex items-center gap-1 hover:opacity-80">
                          <Badge className={roleBadgeClass(u.huf_role)}>{u.huf_role}</Badge>
                          <ChevronDown className="h-3 w-3 text-muted-foreground" />
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
                  </td>
                  <td className="px-4 py-3">
                    <span
                      className={`text-xs font-medium ${u.enabled ? 'text-green-700' : 'text-red-600'}`}
                    >
                      {u.enabled ? 'Active' : 'Disabled'}
                    </span>
                  </td>
                  <td className="px-4 py-3">
                    <button
                      onClick={() => handleToggleEnabled(u)}
                      className="text-muted-foreground hover:text-foreground"
                      title={u.enabled ? 'Disable user' : 'Enable user'}
                    >
                      {u.enabled ? (
                        <ToggleRight className="h-5 w-5 text-green-600" />
                      ) : (
                        <ToggleLeft className="h-5 w-5" />
                      )}
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      <InviteDialog
        open={showInvite}
        roles={roles}
        onClose={() => setShowInvite(false)}
        onInvited={(u) => setUsers((prev) => [u, ...prev])}
      />
    </div>
  );
}
