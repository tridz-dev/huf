import { useEffect, useMemo, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { ExternalLink, Search } from 'lucide-react';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';
import { Input } from '@/components/ui/input';
import { Badge } from '@/components/ui/badge';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { getIntegrationServices } from '@/services/integrationApi';
import { parseRequiredCredentials } from '@/types/integration.types';
import type { IntegrationServiceDoc } from '@/types/integration.types';
import { getFrappeErrorMessage } from '@/lib/frappe-error';
import { toast } from 'sonner';

interface ServiceCatalogModalProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
}

export function ServiceCatalogModal({ open, onOpenChange }: ServiceCatalogModalProps) {
  const navigate = useNavigate();
  const [services, setServices] = useState<IntegrationServiceDoc[]>([]);
  const [loading, setLoading] = useState(false);
  const [search, setSearch] = useState('');
  const [category, setCategory] = useState('all');

  useEffect(() => {
    if (!open) return;

    setLoading(true);
    getIntegrationServices()
      .then(setServices)
      .catch((error) => {
        toast.error(getFrappeErrorMessage(error) || 'Failed to load integration services');
      })
      .finally(() => setLoading(false));
  }, [open]);

  const categories = useMemo(() => {
    const unique = new Set(services.map((s) => s.category).filter(Boolean));
    return ['all', ...Array.from(unique).sort()];
  }, [services]);

  const filteredServices = useMemo(() => {
    const query = search.trim().toLowerCase();
    return services.filter((service) => {
      const matchesCategory = category === 'all' || service.category === category;
      const matchesSearch =
        !query ||
        service.service_name.toLowerCase().includes(query) ||
        service.description?.toLowerCase().includes(query) ||
        service.category?.toLowerCase().includes(query);
      return matchesCategory && matchesSearch;
    });
  }, [services, search, category]);

  const handleSelect = (serviceName: string) => {
    onOpenChange(false);
    setSearch('');
    setCategory('all');
    navigate(`/integrations/new?service=${encodeURIComponent(serviceName)}`);
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-3xl max-h-[85vh] overflow-hidden flex flex-col">
        <DialogHeader>
          <DialogTitle>Add Integration</DialogTitle>
          <DialogDescription>
            Choose a service to connect. Required credentials are shown for each integration.
          </DialogDescription>
        </DialogHeader>

        <div className="flex flex-col sm:flex-row gap-3">
          <div className="relative flex-1">
            <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-muted-foreground" />
            <Input
              placeholder="Search services..."
              className="pl-9"
              value={search}
              onChange={(e) => setSearch(e.target.value)}
            />
          </div>
          <select
            className="h-10 rounded-md border border-input bg-background px-3 text-sm"
            value={category}
            onChange={(e) => setCategory(e.target.value)}
          >
            {categories.map((cat) => (
              <option key={cat} value={cat}>
                {cat === 'all' ? 'All categories' : cat}
              </option>
            ))}
          </select>
        </div>

        <div className="flex-1 overflow-y-auto min-h-0 py-2">
          {loading ? (
            <div className="text-center py-12 text-muted-foreground">Loading services...</div>
          ) : filteredServices.length === 0 ? (
            <div className="text-center py-12 text-muted-foreground">No services found.</div>
          ) : (
            <div className="grid gap-3 sm:grid-cols-2">
              {filteredServices.map((service) => {
                const credSchema = parseRequiredCredentials(service.required_credentials);
                return (
                  <Card
                    key={service.name}
                    className="cursor-pointer transition-colors hover:border-primary/50"
                    onClick={() => handleSelect(service.service_name)}
                  >
                    <CardHeader className="pb-2">
                      <div className="flex items-start justify-between gap-2">
                        <CardTitle className="text-base capitalize">
                          {service.service_name.replace(/_/g, ' ')}
                        </CardTitle>
                        <Badge variant="outline">{service.category}</Badge>
                      </div>
                      {service.description && (
                        <CardDescription className="line-clamp-2">{service.description}</CardDescription>
                      )}
                    </CardHeader>
                    <CardContent className="space-y-2">
                      {credSchema.length > 0 && (
                        <p className="text-xs text-muted-foreground">
                          Requires: {credSchema.map((c) => c.label).join(', ')}
                        </p>
                      )}
                      {service.documentation_url && (
                        <a
                          href={service.documentation_url}
                          target="_blank"
                          rel="noopener noreferrer"
                          className="inline-flex items-center text-xs text-primary hover:underline"
                          onClick={(e) => e.stopPropagation()}
                        >
                          Documentation
                          <ExternalLink className="w-3 h-3 ml-1" />
                        </a>
                      )}
                    </CardContent>
                  </Card>
                );
              })}
            </div>
          )}
        </div>
      </DialogContent>
    </Dialog>
  );
}
