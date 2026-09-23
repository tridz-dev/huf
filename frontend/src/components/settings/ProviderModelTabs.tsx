import { NavLink } from 'react-router-dom';
import { cn } from '@/lib/utils';
import { usePermissions } from '@/contexts/PermissionsContext';

const providerModelSections = [
  { label: 'Providers', to: '/providers' },
  { label: 'Models', to: '/models' },
  { label: 'Decision', to: '/decision-models', requiresCapability: 'decision.admin' },
];

export function ProviderModelTabs() {
  const { hasCapability } = usePermissions();

  const visibleSections = providerModelSections.filter((section) =>
    section.requiresCapability ? hasCapability(section.requiresCapability) : true
  );

  return (
    <nav aria-label="Provider and model sections" className="mb-5 flex border-b border-ink">
      {visibleSections.map((section) => (
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
