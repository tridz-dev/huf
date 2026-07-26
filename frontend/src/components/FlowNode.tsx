import { ReactNode } from 'react';
import { Card } from './ui/card';

interface FlowNodeProps {
  icon: ReactNode;
  title: string;
  subtitle?: string;
  variant?: 'default' | 'primary' | 'success';
  showLine?: boolean;
}

export function FlowNode({ icon, title, subtitle, variant = 'default', showLine = true }: FlowNodeProps) {
  const variantStyles = {
    default: 'border-border bg-card',
    primary: 'border-primary bg-primary/5',
    success: 'border-green-500 bg-green-500/5',
  };

  return (
    <div className="flex flex-col items-center">
      <Card className={`w-64 p-4 ${variantStyles[variant]} hover:shadow-md transition-shadow cursor-pointer`}>
        <div className="flex items-center gap-3">
          <div className="w-10 h-10 rounded-lg bg-primary/10 flex items-center justify-center text-primary">
            {icon}
          </div>
          <div className="flex-1 min-w-0">
            <div className="text-sm font-medium text-card-foreground">{title}</div>
            {subtitle && <div className="text-xs text-muted-foreground">{subtitle}</div>}
          </div>
        </div>
      </Card>
      {showLine && (
        <div className="w-0.5 h-8 bg-border my-2" />
      )}
    </div>
  );
}
