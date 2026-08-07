import { NavLink } from 'react-router-dom';
import { cn } from '@/lib/utils';

const promptSections = [
  { label: 'Instructions', to: '/prompts' },
  { label: 'Summarization', to: '/summary-prompts' },
];

export function PromptLibraryTabs() {
  return (
    <nav
      aria-label="Prompt sections"
      className="mb-5 inline-flex items-center justify-start border-b border-ink bg-transparent p-0"
    >
      {promptSections.map((section) => (
        <NavLink
          key={section.to}
          to={section.to}
          end
          className={({ isActive }) =>
            cn(
              'inline-flex items-center justify-center whitespace-nowrap border-b-2 border-transparent px-4 py-2 font-body text-[13px] font-medium text-steel transition-colors hover:text-ink',
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
