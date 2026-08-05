import { useSearchParams } from 'react-router-dom';
import UsersPage from './UsersPage';
import RolesPage from './RolesPage';
import { Button } from '@/components/ui/button';

const views = [
  { value: 'people', label: 'People' },
  { value: 'roles', label: 'Roles & access' },
] as const;

export default function MembersPage() {
  const [searchParams, setSearchParams] = useSearchParams();
  const view = searchParams.get('view') === 'roles' ? 'roles' : 'people';

  return (
    <div className="flex h-full min-h-0 flex-col">
      <nav aria-label="Member administration" className="mx-6 mt-5 flex shrink-0 border-b border-ink">
        {views.map((item) => (
          <Button
            key={item.value}
            type="button"
            variant="ghost"
            className={`h-auto rounded-none border-b-2 px-4 pb-2 font-mono text-[11.5px] uppercase tracking-wide hover:bg-transparent ${
              view === item.value
                ? '-mb-px border-signal text-ink'
                : 'border-transparent text-steel hover:text-ink'
            }`}
            onClick={() => setSearchParams(item.value === 'people' ? {} : { view: item.value })}
          >
            {item.label}
          </Button>
        ))}
      </nav>
      <div className="min-h-0 flex-1">
        {view === 'roles' ? <RolesPage /> : <UsersPage />}
      </div>
    </div>
  );
}
