import { Database, Globe, Cpu, Bot, Code, Search } from 'lucide-react';
import { Card, CardContent } from '@/components/ui/card';
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
  search: Search,
};

export function ToolTemplateCard({ template, onClick }: ToolTemplateCardProps) {
  const Icon = iconMap[template.icon as keyof typeof iconMap] || Database;

  return (
    <Card
      onClick={onClick}
      className={cn(
        'cursor-pointer group transition-colors',
        'hover:bg-paper-deep hover:border-ink'
      )}
    >
      <CardContent className="flex flex-col items-start p-5">
        <div
          className={cn(
            'h-10 w-10 rounded-none bg-paper-deep/30 text-muted-foreground',
            'flex items-center justify-center mb-4',
            'group-hover:text-ink transition-colors'
          )}
        >
          <Icon className="w-6 h-6" aria-hidden="true" />
        </div>
        <h3 className="font-semibold text-foreground mb-1">{template.name}</h3>
        <p className="text-sm text-steel leading-relaxed">{template.description}</p>
      </CardContent>
    </Card>
  );
}
