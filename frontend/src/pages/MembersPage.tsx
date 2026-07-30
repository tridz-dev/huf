import { useSearchParams } from 'react-router-dom';
import UsersPage from './UsersPage';
import RolesPage from './RolesPage';

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
          <button
            key={item.value}
            type="button"
            onClick={() => setSearchParams(item.value === 'people' ? {} : { view: item.value })}
            className={`border-b-2 px-4 pb-2 font-mono text-[11.5px] uppercase tracking-wide transition-colors ${
              view === item.value
                ? '-mb-px border-signal text-ink'
                : 'border-transparent text-steel hover:text-ink'
            }`}
          >
            {item.label}
          </button>
        ))}
      </nav>
      <div className="min-h-0 flex-1">
        {view === 'roles' ? <RolesPage /> : <UsersPage />}
      </div>
    </div>
  );
}
