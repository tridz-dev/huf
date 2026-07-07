import { Trash2 } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Textarea } from '@/components/ui/textarea';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import { Checkbox } from '@/components/ui/checkbox';
import { Card, CardContent } from '@/components/ui/card';
import { Label } from '@/components/ui/label';

export type ParameterData = {
  label: string;
  fieldname: string;
  type: 'string' | 'integer' | 'number' | 'float' | 'boolean' | 'object' | 'array';
  required: boolean;
  description?: string;
  options?: string;
  child_table_name?: string;
};

interface ParameterCardProps {
  parameter: ParameterData;
  index: number;
  onChange: (index: number, data: Partial<ParameterData>) => void;
  onDelete: (index: number) => void;
}

const parameterTypes = [
  'string',
  'integer',
  'number',
  'float',
  'boolean',
  'object',
  'array',
] as const;

export function ParameterCard({
  parameter,
  index,
  onChange,
  onDelete,
}: ParameterCardProps) {
  const handleChange = (field: keyof ParameterData, value: any) => {
    onChange(index, { [field]: value });
  };

  return (
    <Card className="border-gray-200">
      <CardContent className="p-4 space-y-4">
        <div className="flex items-center justify-between mb-2">
          <h4 className="font-medium text-sm">Parameter {index + 1}</h4>
          <Button
            type="button"
            variant="ghost"
            size="sm"
            onClick={() => onDelete(index)}
            className="h-8 w-8 p-0 text-red-600 hover:text-red-700 hover:bg-red-50"
          >
            <Trash2 className="w-4 h-4" />
          </Button>
        </div>

        <div className="grid grid-cols-2 gap-4">
          <div className="space-y-2">
            <Label htmlFor={`param-label-${index}`}>
              Label<span className="text-red-500">*</span>
            </Label>
            <Input
              id={`param-label-${index}`}
              value={parameter.label || ''}
              onChange={(e) => handleChange('label', e.target.value)}
              placeholder="e.g., Document ID"
            />
          </div>

          <div className="space-y-2">
            <Label htmlFor={`param-fieldname-${index}`}>
              Fieldname<span className="text-red-500">*</span>
            </Label>
            <Input
              id={`param-fieldname-${index}`}
              value={parameter.fieldname || ''}
              onChange={(e) => handleChange('fieldname', e.target.value)}
              placeholder="e.g., document_id"
            />
          </div>
        </div>

        <div className="grid grid-cols-2 gap-4">
          <div className="space-y-2">
            <Label htmlFor={`param-type-${index}`}>
              Type<span className="text-red-500">*</span>
            </Label>
            <Select
              value={parameter.type}
              onValueChange={(value) => handleChange('type', value as ParameterData['type'])}
            >
              <SelectTrigger id={`param-type-${index}`}>
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                {parameterTypes.map((type) => (
                  <SelectItem key={type} value={type}>
                    {type}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>

          <div className="space-y-2">
            <Label htmlFor={`param-child-table-${index}`}>Child Table Name</Label>
            <Input
              id={`param-child-table-${index}`}
              value={parameter.child_table_name || ''}
              onChange={(e) => handleChange('child_table_name', e.target.value)}
              placeholder="Optional"
            />
          </div>
        </div>

        <div className="space-y-2">
          <Label htmlFor={`param-description-${index}`}>Description</Label>
          <Textarea
            id={`param-description-${index}`}
            value={parameter.description || ''}
            onChange={(e) => handleChange('description', e.target.value)}
            placeholder="Describe this parameter..."
            className="min-h-[60px]"
          />
        </div>

        <div className="grid grid-cols-2 gap-4">
          <div className="space-y-2">
            <Label htmlFor={`param-options-${index}`}>Options</Label>
            <Input
              id={`param-options-${index}`}
              value={parameter.options || ''}
              onChange={(e) => handleChange('options', e.target.value)}
              placeholder="Comma-separated options"
            />
          </div>

          <div className="flex items-center space-x-2 pt-8">
            <Checkbox
              id={`param-required-${index}`}
              checked={parameter.required || false}
              onCheckedChange={(checked) => handleChange('required', checked)}
            />
            <Label
              htmlFor={`param-required-${index}`}
              className="text-sm font-normal cursor-pointer"
            >
              Required
            </Label>
          </div>
        </div>
      </CardContent>
    </Card>
  );
}
