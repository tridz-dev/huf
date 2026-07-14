import * as React from 'react';
import { Pencil } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { cn } from '@/lib/utils';

interface InlineEditNameProps {
  value: string;
  onChange: (value: string) => void;
  placeholder?: string;
  className?: string;
  disabled?: boolean;
}

export function InlineEditName({
  value,
  onChange,
  placeholder,
  className,
  disabled,
}: InlineEditNameProps) {
  const [isEditing, setIsEditing] = React.useState(false);
  const snapshotRef = React.useRef(value);

  const commit = () => {
    setIsEditing(false);
    if (!value.trim()) {
      onChange(snapshotRef.current);
    }
  };

  const revert = () => {
    setIsEditing(false);
    onChange(snapshotRef.current);
  };

  const handleKeyDown = (event: React.KeyboardEvent<HTMLInputElement>) => {
    if (event.key === 'Enter') {
      event.preventDefault();
      commit();
    } else if (event.key === 'Escape') {
      event.preventDefault();
      revert();
    }
  };

  const startEditing = () => {
    snapshotRef.current = value;
    setIsEditing(true);
  };

  if (isEditing) {
    return (
      <Input
        value={value}
        onChange={(event) => onChange(event.target.value)}
        onBlur={commit}
        onKeyDown={handleKeyDown}
        autoFocus
        className={cn(
          'text-2xl font-bold h-auto border-0 px-0 focus-visible:ring-0 max-w-md',
          className
        )}
      />
    );
  }

  return (
    <div className={cn('flex items-center gap-2', className)}>
      <h1 className="text-2xl font-bold">{value || placeholder}</h1>
      {!disabled && (
        <Button
          type="button"
          variant="ghost"
          size="icon"
          aria-label="Edit name"
          onClick={startEditing}
        >
          <Pencil className="h-4 w-4" />
        </Button>
      )}
    </div>
  );
}
