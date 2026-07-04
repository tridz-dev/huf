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
        'bg-card border border-border rounded-xl',
        'hover:border-primary hover:shadow-md transition-all'
      )}
    >
      <div
        className={cn(
          'h-10 w-10 rounded-lg bg-muted text-primary',
          'flex items-center justify-center mb-4',
          'group-hover:bg-primary/10 transition-colors'
        )}
      >
        <Icon className="w-6 h-6" aria-hidden="true" />
      </div>
      <h3 className="font-semibold text-foreground mb-1">{template.name}</h3>
      <p className="text-sm text-muted-foreground leading-relaxed">{template.description}</p>
    </div>
  );
}
