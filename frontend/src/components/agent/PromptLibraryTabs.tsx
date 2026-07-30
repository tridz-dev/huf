import { NavLink } from 'react-router-dom';
import { cn } from '@/lib/utils';

const promptSections = [
  { label: 'Instructions', to: '/prompts' },
  { label: 'Summarization', to: '/summary-prompts' },
];

export function PromptLibraryTabs() {
  return (
    <nav aria-label="Prompt sections" className="mb-5 flex border-b border-ink">
      {promptSections.map((section) => (
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
