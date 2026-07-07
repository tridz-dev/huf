import { Database, Globe, Cpu, Bot, Code } from 'lucide-react';
import { cn } from '@/lib/utils';
import type { ToolTemplate } from '@/types/toolTemplate.types';

interface ToolTemplateCardProps {
  template: ToolTemplate;
  onClick: () => void;
}

const iconMap = {
  database: Database,
  globe: Globe,
  cpu: Cpu,
  bot: Bot,
  code: Code,
};

export function ToolTemplateCard({ template, onClick }: ToolTemplateCardProps) {
  const Icon = iconMap[template.icon as keyof typeof iconMap] || Database;

  return (
    <div
      onClick={onClick}
      className={cn(
        'cursor-pointer group relative flex flex-col items-start p-5',
        'bg-white border border-gray-200 rounded-xl',
        'hover:border-purple-500 hover:shadow-md transition-all'
      )}
    >
      <div
        className={cn(
          'h-10 w-10 rounded-lg bg-gray-50 text-purple-600',
          'flex items-center justify-center mb-4',
          'group-hover:bg-purple-50 transition-colors'
        )}
      >
        <Icon className="w-6 h-6" aria-hidden="true" />
      </div>
      <h3 className="font-semibold text-gray-900 mb-1">{template.name}</h3>
      <p className="text-sm text-gray-500 leading-relaxed">{template.description}</p>
    </div>
  );
}
