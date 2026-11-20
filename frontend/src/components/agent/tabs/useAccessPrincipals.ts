/**
 * Loads and searches the user / role option lists for AccessTab, seeding them with the
 * agent's current picks so saved values always render as labelled options (same behaviour
 * as the legacy PermissionsTab). The page may use this hook or supply its own options.
 */
import { useEffect, useMemo, useState } from 'react';
import { useDebounce } from '@/hooks/useDebounce';
import { searchUsers, searchRoles, fetchUsersByName, fetchRolesByName } from '@/services/agentApi';
import type { MultiSelectComboboxOption } from '@/components/ui/multi-select-combobox';

interface Named { name: string }

function mergeByName(base: Named[], extra: Named[]): Named[] {
  const seen = new Set(base.map((i) => i.name));
  return [...base, ...extra.filter((i) => !seen.has(i.name) && seen.add(i.name))];
}

export function useAccessPrincipals(currentUsers: string[], currentRoles: string[]) {
  const [userQuery, setUserQuery] = useState('');
  const [users, setUsers] = useState<Named[]>([]);
  const [roles, setRoles] = useState<Named[]>([]);
  const [usersLoading, setUsersLoading] = useState(true);
  const [rolesLoading, setRolesLoading] = useState(true);
  const debounced = useDebounce(userQuery, 250);

  useEffect(() => {
    let cancelled = false;
    setRolesLoading(true);
    Promise.all([searchRoles(''), fetchRolesByName(currentRoles)]).then(([defaults, selected]) => {
      if (cancelled) return;
      const resolved = new Set(selected.map((r) => r.name));
      setRoles(mergeByName(mergeByName(defaults, selected), currentRoles.filter((n) => !resolved.has(n)).map((name) => ({ name }))));
      setRolesLoading(false);
    });
    return () => { cancelled = true; };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => {
    let cancelled = false;
    setUsersLoading(true);
    Promise.all([searchUsers(debounced), debounced ? Promise.resolve([]) : fetchUsersByName(currentUsers)]).then(([found, selected]) => {
      if (cancelled) return;
      const resolved = new Set([...found, ...selected].map((u) => u.name));
      const unresolved = currentUsers.filter((n) => !resolved.has(n)).map((name) => ({ name }));
      setUsers((prev) => mergeByName(mergeByName(found, selected), mergeByName(unresolved, prev.filter((p) => currentUsers.includes(p.name)))));
      setUsersLoading(false);
    });
    return () => { cancelled = true; };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [debounced]);

  const toOptions = (items: Named[]): MultiSelectComboboxOption[] => items.map((i) => ({ value: i.name, label: i.name }));
  return {
    userOptions: useMemo(() => toOptions(users), [users]),
    roleOptions: useMemo(() => toOptions(roles), [roles]),
    usersLoading, rolesLoading, userQuery, setUserQuery,
  };
}
