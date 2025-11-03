import { Play, History, Upload } from 'lucide-react';
import { Button } from './ui/button';

export function FlowsHeaderActions() {
  return (
    <>
      <Button variant="ghost" size="sm" className="gap-2">
        <Play className="w-4 h-4" />
        <span>Run</span>
      </Button>
      <Button variant="ghost" size="sm" className="gap-2">
        <History className="w-4 h-4" />
        <span>Versions</span>
      </Button>
      <Button variant="default" size="sm" className="gap-2">
        <Upload className="w-4 h-4" />
        <span>Publish</span>
      </Button>
    </>
  );
}
