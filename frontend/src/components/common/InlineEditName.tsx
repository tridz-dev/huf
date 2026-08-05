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

  const isButtonHidden = isEditing || disabled;

  const editButton = (
    <Button
      type="button"
      variant="ghost"
      size="icon"
      aria-label="Edit name"
      onClick={startEditing}
      disabled={isButtonHidden}
      tabIndex={isButtonHidden ? -1 : undefined}
      className={cn(isButtonHidden && 'invisible')}
    >
      <Pencil className="h-4 w-4" />
    </Button>
  );

  if (isEditing) {
    return (
      <div className={cn('flex items-center gap-2 w-full max-w-md min-w-0', className)}>
        <Input
          value={value}
          onChange={(event) => onChange(event.target.value)}
          onBlur={commit}
          onKeyDown={handleKeyDown}
          autoFocus
          className="font-display text-title text-ink h-auto border-0 px-0 py-0 focus-visible:ring-0 flex-1 min-w-0"
        />
        {editButton}
      </div>
    );
  }

  return (
    <div className={cn('inline-flex items-center gap-2 max-w-md min-w-0', className)}>
      <h1 className="font-display text-title text-ink min-w-0 max-w-full truncate">
        {value || placeholder}
      </h1>
      {editButton}
    </div>
  );
}
