import { ReactNode } from 'react';
import { LucideIcon } from 'lucide-react';
import { CardHeader, CardTitle, CardDescription, CardContent, CardAction } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { BaseCard } from './BaseCard';
import { cn } from '@/lib/utils';

type BadgeVariant = 'default' | 'secondary' | 'destructive' | 'outline';

interface MetadataItem {
  label: string;
  value: ReactNode;
  icon?: LucideIcon;
}

interface ActionButton {
  icon: LucideIcon;
  label: string;
  onClick: () => void;
  variant?: 'default' | 'ghost' | 'outline';
}

interface ItemCardProps {
  title: string;
  description?: string;
  status?: {
    label: string;
    variant?: BadgeVariant;
  };
  metadata?: MetadataItem[];
  actions?: ActionButton[];
  footer?: ReactNode;
  onClick?: () => void;
  className?: string;
}

export function ItemCard({
  title,
  description,
  status,
  metadata = [],
  actions = [],
  footer,
  onClick,
  className,
}: ItemCardProps) {
  return (
    <BaseCard onClick={onClick} className={cn('flex flex-col', className)}>
      <div className="flex flex-col flex-1">
        <CardHeader className="pb-3">
          <CardTitle className="text-xl font-semibold line-clamp-1">{title}</CardTitle>
          {description && (
            <CardDescription className="text-sm line-clamp-2 min-h-[2.5rem]">{description}</CardDescription>
          )}
          {status && (
            <CardAction className="top-5">
              <Badge variant={status.variant || 'default'} className="text-xs">
                {status.label}
              </Badge>
            </CardAction>
          )}
        </CardHeader>

        {(metadata.length > 0 || actions.length > 0 || footer) && (
          <CardContent className="flex flex-col flex-1 min-h-0 pb-3">
            {metadata.length > 0 && (
              <div className="space-y-1">
                {metadata.map((item, index) => (
                  <div
                    key={index}
                    className="flex items-center justify-between text-sm leading-tight"
                  >
                    <div className="flex items-center gap-1 text-muted-foreground">
                      {item.icon && <item.icon className="w-3 h-3" />}
                      <span>{item.label}</span>
                    </div>
                    <span className="font-medium">{item.value}</span>
                  </div>
                ))}
              </div>
            )}

            {(actions.length > 0 || footer) && (
              <div className="mt-auto pt-1">
                {actions.length > 0 && (
                  <div className="flex gap-2">
                    {actions.map((action, index) => (
                      <Button
                        key={index}
                        variant={action.variant || 'ghost'}
                        size="icon"
                        className="h-8 w-8"
                        title={action.label}
                        onClick={(e) => {
                          e.stopPropagation();
                          action.onClick();
                        }}
                      >
                        <action.icon className="w-4 h-4" />
                      </Button>
                    ))}
                  </div>
                )}

                {footer && <div className="pt-2">{footer}</div>}
              </div>
            )}
          </CardContent>
        )}
      </div>
    </BaseCard>
  );
}
