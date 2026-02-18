import { Trash2 } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Card, CardContent } from '@/components/ui/card';
import { Label } from '@/components/ui/label';

export type HttpHeaderData = {
  key: string;
  value: string;
};

interface HttpHeaderCardProps {
  header: HttpHeaderData;
  index: number;
  onChange: (index: number, data: Partial<HttpHeaderData>) => void;
  onDelete: (index: number) => void;
}

export function HttpHeaderCard({
  header,
  index,
  onChange,
  onDelete,
}: HttpHeaderCardProps) {
  const handleChange = (field: keyof HttpHeaderData, value: string) => {
    onChange(index, { [field]: value });
  };

  return (
    <Card className="border-gray-200">
      <CardContent className="p-4">
        <div className="flex items-center justify-between mb-4">
          <h4 className="font-medium text-sm">Header {index + 1}</h4>
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
            <Label htmlFor={`header-key-${index}`}>Key</Label>
            <Input
              id={`header-key-${index}`}
              value={header.key || ''}
              onChange={(e) => handleChange('key', e.target.value)}
              placeholder="e.g., Authorization"
            />
          </div>

          <div className="space-y-2">
            <Label htmlFor={`header-value-${index}`}>Value</Label>
            <Input
              id={`header-value-${index}`}
              value={header.value || ''}
              onChange={(e) => handleChange('value', e.target.value)}
              placeholder="e.g., Bearer token123"
            />
          </div>
        </div>
      </CardContent>
    </Card>
  );
}
