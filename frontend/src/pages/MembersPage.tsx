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
      {view === 'roles' ? <RolesPage embedded /> : <UsersPage embedded />}
    </PageFrame>
  );
}
