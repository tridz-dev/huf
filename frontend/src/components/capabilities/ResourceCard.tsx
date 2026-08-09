import { Star } from 'lucide-react';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';

interface ResourceCardResource {
  doctype: string;
  title: string;
  visibility: string;
  is_exposed?: boolean;
  submittable?: boolean;
}

interface ResourceCardProps {
  resource: ResourceCardResource;
  onSelect: (doctype: string) => void;
}

export function ResourceCard({ resource, onSelect }: ResourceCardProps) {
  const isRecommended = resource.is_exposed || resource.visibility === 'recommended';

  return (
    <Card
      role="button"
      tabIndex={0}
      onClick={() => onSelect(resource.doctype)}
      onKeyDown={(e) => {
        if (e.key === 'Enter' || e.key === ' ') {
          e.preventDefault();
          onSelect(resource.doctype);
        }
      }}
      className="cursor-pointer hover:bg-paper-deep transition-colors"
    >
      <CardHeader>
        <div className="flex items-start justify-between gap-2">
          <CardTitle className="text-sm">{resource.title}</CardTitle>
          {isRecommended && (
            <Badge variant="success" className="shrink-0 flex items-center gap-1">
              <Star className="w-3 h-3" />
              Recommended
            </Badge>
          )}
        </div>
      </CardHeader>
      <CardContent className="pt-0">
        <div className="flex items-center gap-2 flex-wrap">
          <Badge variant="outline">{resource.doctype}</Badge>
          <Badge variant="secondary" className="capitalize">
            {resource.visibility}
          </Badge>
          {resource.submittable && <Badge variant="outline">Submittable</Badge>}
        </div>
      </CardContent>
    </Card>
  );
}
