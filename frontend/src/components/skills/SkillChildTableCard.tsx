import { useState } from 'react';
import { Plus } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from '@/components/ui/card';
import { MultiSelectCombobox } from '@/components/ui/multi-select-combobox';

interface ChildTableCardProps {
  title: string;
  description: string;
  icon: React.ElementType;
  emptyText: string;
  addLabel: string;
  options: { value: string; label: string; subtitle?: string }[];
  /** Receives every picked value at once so callers can add them in one update. */
  onAdd: (values: string[]) => void;
  children: React.ReactNode;
}

export function ChildTableCard({
  title,
  description,
  icon: Icon,
  emptyText,
  addLabel,
  options,
  onAdd,
  children,
}: ChildTableCardProps) {
  const [values, setValues] = useState<string[]>([]);
  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2">
          <Icon className="w-5 h-5" />
          {title}
        </CardTitle>
        <CardDescription>{description}</CardDescription>
      </CardHeader>
      <CardContent className="space-y-4">
        <div className="flex items-end gap-2">
          <div className="flex-1 min-w-0">
            <MultiSelectCombobox
              options={options.map((o) => ({ value: o.value, label: o.label, description: o.subtitle }))}
              values={values}
              onValuesChange={setValues}
              placeholder={`Select ${title.toLowerCase()}`}
              searchPlaceholder={`Search ${title.toLowerCase()}...`}
              emptyText={`No ${title.toLowerCase()} found`}
            />
          </div>
          <Button
            type="button"
            size="sm"
            variant="outline"
            onClick={() => {
              if (values.length) {
                onAdd(values);
                setValues([]);
              }
            }}
            disabled={values.length === 0}
          >
            <Plus className="w-4 h-4 mr-2" />
            {values.length > 1 ? `${addLabel} (${values.length})` : addLabel}
          </Button>
        </div>

        {Array.isArray(children) && children.length === 0 ? (
          <div className="text-center py-12 border border-dashed rounded-lg bg-muted/20">
            <p className="text-muted-foreground">{emptyText}</p>
          </div>
        ) : (
          <div className="grid gap-3">{children}</div>
        )}
      </CardContent>
    </Card>
  );
}
