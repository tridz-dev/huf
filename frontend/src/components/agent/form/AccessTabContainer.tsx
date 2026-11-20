/** Owns the user / role option lookups so they only run while the Access tab is shown. */
import { AccessTab, type AccessTabProps } from '../tabs/AccessTab';
import { useAccessPrincipals } from '../tabs/useAccessPrincipals';

export function AccessTabContainer(props: Omit<AccessTabProps, 'userOptions' | 'roleOptions' | 'usersLoading' | 'rolesLoading' | 'onUserSearch' | 'userQuery'>) {
  const users = props.form.watch('allowed_users') ?? [];
  const roles = props.form.watch('allowed_roles') ?? [];
  const p = useAccessPrincipals(users, roles);
  return (
    <AccessTab {...props} userOptions={p.userOptions} roleOptions={p.roleOptions} usersLoading={p.usersLoading}
      rolesLoading={p.rolesLoading} onUserSearch={p.setUserQuery} userQuery={p.userQuery} />
  );
}
