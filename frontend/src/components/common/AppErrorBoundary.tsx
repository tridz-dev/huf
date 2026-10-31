import { Component, type ErrorInfo, type ReactNode } from 'react';
import { Button } from '@/components/ui/button';

/** Last line of defence above the router: a crash while starting the app shows a readable screen, not a blank page. */
export class AppErrorBoundary extends Component<{ children: ReactNode }, { failed: boolean }> {
  state = { failed: false };

  static getDerivedStateFromError() {
    return { failed: true };
  }

  componentDidCatch(error: Error, info: ErrorInfo) {
    console.error('Huf failed to render', error, info.componentStack);
  }

  render() {
    if (!this.state.failed) return this.props.children;
    return (
      <div role="alert" data-testid="app-error-screen" className="min-h-screen flex flex-col items-center justify-center gap-3 bg-paper text-center px-6">
        <p className="text-sm text-ink font-medium">Something went wrong</p>
        <p className="text-xs text-steel max-w-sm">Huf could not finish loading. Reloading the page usually fixes this.</p>
        <Button size="sm" onClick={() => window.location.reload()}>
          Reload
        </Button>
      </div>
    );
  }
}
