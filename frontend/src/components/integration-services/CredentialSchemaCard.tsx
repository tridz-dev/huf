import { Trash2 } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Textarea } from '@/components/ui/textarea';
import { Checkbox } from '@/components/ui/checkbox';
import { Card, CardContent } from '@/components/ui/card';
import { Label } from '@/components/ui/label';
import type { CredentialSchemaItem } from '@/types/integration.types';

interface CredentialSchemaCardProps {
  item: CredentialSchemaItem;
  index: number;
  onChange: (index: number, data: Partial<CredentialSchemaItem>) => void;
  onDelete: (index: number) => void;
  canDelete: boolean;
}

export function CredentialSchemaCard({
  item,
  index,
  onChange,
  onDelete,
  canDelete,
}: CredentialSchemaCardProps) {
  const handleChange = (field: keyof CredentialSchemaItem, value: string | boolean) => {
    onChange(index, { [field]: value });
  };

  return (
    <Card>
      <CardContent className="p-4 space-y-4">
        <div className="flex items-center justify-between mb-2">
          <h4 className="font-medium text-sm">Credential {index + 1}</h4>
          <Button
            type="button"
            variant="ghost"
            size="sm"
            onClick={() => onDelete(index)}
            disabled={!canDelete}
            className="h-8 w-8 p-0 text-destructive hover:text-destructive hover:bg-destructive/10"
          >
            <Trash2 className="w-4 h-4" />
          </Button>
        </div>

        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          <div className="space-y-2">
            <Label htmlFor={`cred-key-${index}`}>
              Key<span className="text-destructive">*</span>
            </Label>
            <Input
              id={`cred-key-${index}`}
              value={item.key}
              onChange={(e) => handleChange('key', e.target.value)}
              placeholder="e.g. api_key"
            />
          </div>

          <div className="space-y-2">
            <Label htmlFor={`cred-label-${index}`}>
              Label<span className="text-destructive">*</span>
            </Label>
            <Input
              id={`cred-label-${index}`}
              value={item.label}
              onChange={(e) => handleChange('label', e.target.value)}
              placeholder="e.g. API Key"
            />
          </div>
        </div>

        <div className="space-y-2">
          <Label htmlFor={`cred-description-${index}`}>Description</Label>
          <Textarea
            id={`cred-description-${index}`}
            value={item.description || ''}
            onChange={(e) => handleChange('description', e.target.value)}
            placeholder="Optional help text shown in Integration Settings"
            rows={2}
          />
        </div>

        <div className="flex items-center space-x-2">
          <Checkbox
            id={`cred-required-${index}`}
            checked={item.required !== false}
            onCheckedChange={(checked) => handleChange('required', checked === true)}
          />
          <Label htmlFor={`cred-required-${index}`} className="font-normal">
            Required credential
          </Label>
        </div>
      </CardContent>
    </Card>
  );
}
