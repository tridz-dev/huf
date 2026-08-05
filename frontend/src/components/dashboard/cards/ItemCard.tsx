import { ComponentType, ReactNode } from 'react';
import { LucideIcon, MoreVertical } from 'lucide-react';
import { CardHeader, CardTitle, CardDescription, CardContent, CardAction } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { DropdownMenu, DropdownMenuContent, DropdownMenuItem, DropdownMenuTrigger } from '@/components/ui/dropdown-menu';
import { BaseCard } from './BaseCard';
import { StatusDot, type StatusDotVariant } from '@/components/dashboard/ledger/LedgerSection';
import { cn } from '@/lib/utils';

type BadgeVariant = 'default' | 'secondary' | 'destructive' | 'success' | 'outline';

function badgeVariantToStatusDot(variant?: BadgeVariant): StatusDotVariant {
  switch (variant) {
    case 'success':
    case 'default':
      return 'ok';
    case 'destructive':
      return 'fail';
    case 'secondary':
    case 'outline':
    default:
      return 'idle';
  }
}

interface MetadataItem {
  label: string;
  value: ReactNode;
  icon?: LucideIcon;
}

interface ActionButton {
  icon: LucideIcon;
  label: string;
  onClick: () => void;
  variant?: 'default' | 'ghost' | 'outline' | 'destructive';
}

interface ItemCardProps {
  title: string;
  description?: string;
  icon?: ComponentType<{ className?: string }>;
  avatarColor?: string | null;
  status?: {
    label: string;
    variant?: BadgeVariant;
  };
  metadata?: MetadataItem[];
  badges?: Array<{ label: ReactNode; variant?: BadgeVariant }>;
  actions?: ActionButton[];
  menuActions?: ActionButton[];
  menuIcon?: LucideIcon;
  footer?: ReactNode;
  cornerBadge?: ReactNode;
  onClick?: () => void;
  className?: string;
}

export function ItemCard({
  title,
  description,
  icon: TitleIcon,
  avatarColor,
  status,
  metadata = [],
  badges = [],
  actions = [],
  menuActions = [],
  menuIcon: MenuIcon = MoreVertical,
  footer,
  cornerBadge,
  onClick,
  className,
}: ItemCardProps) {
  return (
    <BaseCard onClick={onClick} className={cn('flex flex-col', className)}>
      {cornerBadge ? (
        <div className="absolute bottom-3 right-3 z-10">
          {cornerBadge}
        </div>
      ) : null}
      <div className="flex flex-col flex-1">
        <CardHeader className="pb-3">
          <CardTitle className="line-clamp-1 flex items-center gap-2 text-body-text font-semibold">
            {avatarColor && (
              <span
                className="w-3 h-3 rounded-sm shrink-0 border border-border"
                style={{ backgroundColor: avatarColor }}
                aria-hidden
              />
            )}
            {TitleIcon && <TitleIcon className="w-5 h-5 shrink-0 text-steel-soft" />}
            {title}
          </CardTitle>
          {description && (
            <CardDescription className="text-steel text-[13px] line-clamp-2 min-h-[2.5rem]">{description}</CardDescription>
          )}
          {status && (
            <CardAction className="top-5 flex items-center gap-2">
              <StatusDot variant={badgeVariantToStatusDot(status.variant)} />
              <span className="font-body text-[13px] font-medium text-steel">{status.label}</span>
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
                    <div className="flex items-center gap-1 font-mono text-eyebrow uppercase text-steel-soft">
                      {item.icon && <item.icon className="w-3 h-3" />}
                      <span>{item.label}</span>
                    </div>
                    <span className="font-mono text-[12px] text-steel">{item.value}</span>
                  </div>
                ))}
              </div>
            )}

            {badges.length > 0 && (
              <div className="flex flex-wrap gap-1.5 mt-2">
                {badges.map((badge, index) => (
                  <Badge key={index} variant={badge.variant || 'secondary'} size="sm">
                    {badge.label}
                  </Badge>
                ))}
              </div>
            )}

            {((actions && actions.length > 0) || (menuActions && menuActions.length > 0) || footer) && (
              <div className="mt-auto pt-1">
                {((actions && actions.length > 0) || (menuActions && menuActions.length > 0)) && (
                  <div className="flex items-center gap-2">
                    {actions && actions.length > 0 && actions.map((action, index) => (
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

                    {menuActions && menuActions.length > 0 && (
                      <DropdownMenu>
                        <DropdownMenuTrigger asChild>
                          <Button
                            variant="ghost"
                            size="icon"
                            className="h-8 w-8"
                            title="More actions"
                            onClick={(e) => e.stopPropagation()}
                          >
                            <MenuIcon className="w-4 h-4" />
                          </Button>
                        </DropdownMenuTrigger>
                        <DropdownMenuContent align="end" onClick={(e) => e.stopPropagation()}>
                          {menuActions.map((action, index) => (
                            <DropdownMenuItem
                              key={index}
                              onClick={(e) => {
                                e.stopPropagation();
                                action.onClick();
                              }}
                              className={action.variant === 'destructive' ? 'text-destructive focus:text-destructive' : ''}
                            >
                              <action.icon className="w-4 h-4 mr-2" />
                              {action.label}
                            </DropdownMenuItem>
                          ))}
                        </DropdownMenuContent>
                      </DropdownMenu>
                    )}
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
