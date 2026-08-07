import { NavLink } from 'react-router-dom';
import { cn } from '@/lib/utils';

const providerModelSections = [
  { label: 'Providers', to: '/providers' },
  { label: 'Models', to: '/models' },
];

export function ProviderModelTabs() {
  return (
    <nav aria-label="Provider and model sections" className="mb-5 flex border-b border-ink">
      {providerModelSections.map((section) => (
        <NavLink
          key={section.to}
          to={section.to}
          end
          className={({ isActive }) =>
            cn(
              'border-b-2 border-transparent px-4 pb-2 font-mono text-[11.5px] uppercase tracking-wide text-steel transition-colors hover:text-ink',
              isActive && '-mb-px border-signal text-ink',
            )
          }
        >
          {section.label}
        </NavLink>
      ))}
    </nav>
  );
}
