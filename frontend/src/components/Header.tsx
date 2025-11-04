import { Play, Clock, Moon, FileText } from 'lucide-react';
import { Button } from './ui/button';

export function Header() {
  return (
    <div className="border-b border-border px-4 py-3 flex items-center justify-between bg-card">
      <div className="flex items-center gap-2">
        <span className="text-sm text-muted-foreground">Uncategorized</span>
        <span className="text-sm text-muted-foreground">/</span>
        <span className="text-sm font-medium">Untitled</span>
      </div>

      <div className="flex items-center gap-2">
        <Button variant="ghost" size="sm">
          <Play className="w-4 h-4 mr-1" />
          Run
        </Button>
        <Button variant="ghost" size="sm">
          <Clock className="w-4 h-4 mr-1" />
          Versions
        </Button>
        <Button variant="ghost" size="icon">
          <Moon className="w-4 h-4" />
        </Button>
        <Button size="sm">
          <FileText className="w-4 h-4 mr-1" />
          Publish
        </Button>
      </div>
    </div>
  );
}
