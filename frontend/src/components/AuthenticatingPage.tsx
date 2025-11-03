import { Loader2 } from 'lucide-react';

export function AuthenticatingPage() {
  return (
    <div className="flex items-center justify-center min-h-screen bg-background">
      <div className="flex flex-col items-center gap-4">
        <Loader2 className="h-8 w-8 animate-spin text-primary" />
        <div className="text-center">
          <p className="text-lg font-semibold text-foreground">Authenticating</p>
          <p className="text-sm text-muted-foreground mt-1">
            Please wait while we verify your session
          </p>
        </div>
      </div>
    </div>
  );
}

