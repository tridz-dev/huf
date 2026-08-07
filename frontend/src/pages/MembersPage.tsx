import { useSearchParams } from 'react-router-dom';
import UsersPage from './UsersPage';
import RolesPage from './RolesPage';
import { PageFrame } from '@/layouts/PageFrame';
import { Tabs, TabsList, TabsTrigger } from '@/components/ui/tabs';

const views = [
  { value: 'people', label: 'People' },
  { value: 'roles', label: 'Roles & access' },
] as const;

export default function MembersPage() {
  const [searchParams, setSearchParams] = useSearchParams();
  const view = searchParams.get('view') === 'roles' ? 'roles' : 'people';

  // NOTE: UsersPage still renders its own <PageFrame> (for its "Invite user"
  // action and search/status FilterBar) and RolesPage still renders its own
  // <h1>. Once nested here, that produces a second head bar / a duplicated
  // page name. This PageFrame is the correct single frame for /members — the
  // follow-up (owned by whichever agent is in UsersPage.tsx / RolesPage.tsx)
  // is to stop those two from framing themselves when rendered under
  // MembersPage. See the bottom of this file's task report for detail.
  return (
    <PageFrame
      title="Members"
      filters={
        <Tabs value={view} onValueChange={(value) => setSearchParams(value === 'people' ? {} : { view: value })}>
          <TabsList>
            {views.map((item) => (
              <TabsTrigger key={item.value} value={item.value}>
                {item.label}
              </TabsTrigger>
            ))}
          </TabsList>
        </Tabs>
      }
    >
      {view === 'roles' ? <RolesPage /> : <UsersPage />}
    </PageFrame>
  );
}
