import { Loader2 } from 'lucide-react';

export function PageLoader() {
  return (
    <div className="flex flex-1 items-center justify-center min-h-[200px]">
      <Loader2 className="h-8 w-8 animate-spin text-muted-foreground" />
    </div>
  );
}
