import { Trash2 } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Card, CardContent } from '@/components/ui/card';
import { Label } from '@/components/ui/label';
import { Checkbox } from '@/components/ui/checkbox';
import { Combobox, type ComboboxOption } from '@/components/ui/combobox';

export interface ExecutionProfilePermissionFormRow {
  name?: string;
  capability: string;
  reference_doctype?: string;
  is_read_only?: boolean;
}

interface ExecutionProfilePermissionCardProps {
  permission: ExecutionProfilePermissionFormRow;
  index: number;
  docTypeOptions: ComboboxOption[];
  loadingDocTypes?: boolean;
  onChange: (index: number, data: Partial<ExecutionProfilePermissionFormRow>) => void;
  onDelete: (index: number) => void;
}

export function ExecutionProfilePermissionCard({
  permission,
  index,
  docTypeOptions,
  loadingDocTypes,
  onChange,
  onDelete,
}: ExecutionProfilePermissionCardProps) {
  const handleChange = (field: keyof ExecutionProfilePermissionFormRow, value: string | boolean) => {
    onChange(index, { [field]: value });
  };

  return (
    <Card>
      <CardContent className="p-4">
        <div className="flex items-center justify-between mb-4">
          <h4 className="font-medium text-sm">Permission {index + 1}</h4>
          <Button
            type="button"
            variant="ghost"
            size="sm"
            onClick={() => onDelete(index)}
            className="h-8 w-8 p-0 text-destructive hover:text-destructive hover:bg-destructive/10"
          >
            <Trash2 className="w-4 h-4" />
          </Button>
        </div>

        <div className="grid grid-cols-2 gap-4">
          <div className="space-y-2">
            <Label htmlFor={`permission-capability-${index}`}>Capability</Label>
            <Input
              id={`permission-capability-${index}`}
              value={permission.capability || ''}
              onChange={(e) => handleChange('capability', e.target.value)}
              placeholder="e.g. doc.read"
            />
          </div>

          <div className="space-y-2">
            <Label htmlFor={`permission-reference-doctype-${index}`}>Reference doctype</Label>
            <Combobox
              options={docTypeOptions}
              value={permission.reference_doctype || ''}
              onValueChange={(value) => handleChange('reference_doctype', value)}
              placeholder="Any doctype"
              searchPlaceholder="Search doctypes..."
              emptyText="No doctype found."
              disabled={loadingDocTypes}
            />
          </div>
        </div>

        <div className="flex items-center gap-2 mt-4">
          <Checkbox
            id={`permission-read-only-${index}`}
            checked={permission.is_read_only === true}
            onCheckedChange={(checked) => handleChange('is_read_only', checked === true)}
          />
          <Label htmlFor={`permission-read-only-${index}`} className="font-normal">
            Read only — this capability may not create, update, or delete records
          </Label>
        </div>
      </CardContent>
    </Card>
  );
}
