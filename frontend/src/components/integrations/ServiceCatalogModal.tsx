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
import { Button } from '@/components/ui/button';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import { Badge } from '@/components/ui/badge';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { getIntegrationServices } from '@/services/integrationApi';
import { parseRequiredCredentials } from '@/types/integration.types';
import type { IntegrationServiceDoc } from '@/types/integration.types';
import { getFrappeErrorMessage } from '@/lib/frappe-error';
import { toast } from 'sonner';
import { getServiceIdentity } from '@/data/serviceIdentity';

interface ServiceCatalogModalProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  kind?: 'channels' | 'integrations';
}

export function ServiceCatalogModal({
  open,
  onOpenChange,
  kind = 'integrations',
}: ServiceCatalogModalProps) {
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
      const isGateway = (service.surface || 'Integration') === 'Gateway';
      // GW-24: the Gateways page's "Channel credentials" catalog (kind='channels')
      // and the Integrations page's "Add Integration" catalog (kind='integrations')
      // used to be filtered so strictly by surface that the 6+ Communication-category
      // Gateway services (WhatsApp, Slack, Telegram, ...) were entirely invisible
      // from the generic Integrations catalog -- searching "Slack" there found
      // nothing, with no indication a Gateway surface existed for it. The generic
      // catalog now also lists Gateway-surface services; handleSelect below routes
      // each one to its correct entry point (Gateway vs Integration) regardless of
      // which catalog it was found in.
      const matchesKind = kind === 'channels' ? isGateway : true;
      const matchesCategory = category === 'all' || service.category === category;
      const matchesSearch =
        !query ||
        service.service_name.toLowerCase().includes(query) ||
        service.description?.toLowerCase().includes(query) ||
        service.category?.toLowerCase().includes(query);
      return matchesKind && matchesCategory && matchesSearch;
    });
  }, [services, search, category, kind]);

  const handleSelect = (serviceName: string) => {
    onOpenChange(false);
    setSearch('');
    setCategory('all');
    const service = services.find((s) => s.service_name === serviceName);
    const isGateway = (service?.surface || 'Integration') === 'Gateway';
    // Route by the service's own surface, not by which catalog it was found
    // in -- a Communication service found via the generic "Add Integration"
    // catalog still needs to be configured as a Gateway.
    const base = isGateway ? '/gateways' : '/integrations';
    navigate(`${base}/new?service=${encodeURIComponent(serviceName)}`);
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-[960px] max-h-[85vh] overflow-hidden flex flex-col">
        <DialogHeader>
          <DialogTitle>{kind === 'channels' ? 'Add Channel' : 'Add Integration'}</DialogTitle>
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
          <Select value={category} onValueChange={setCategory}>
            <SelectTrigger className="w-auto min-w-[10rem]">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              {categories.map((cat) => (
                <SelectItem key={cat} value={cat}>
                  {cat === 'all' ? 'All categories' : cat}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
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
                const identity = getServiceIdentity(service.service_name);
                const Icon = identity.icon;
                const isGatewayService = (service.surface || 'Integration') === 'Gateway';
                return (
                  <Card
                    key={service.name}
                    className="cursor-pointer transition-colors hover:border-primary/50"
                    onClick={() => handleSelect(service.service_name)}
                  >
                    <CardHeader className="pb-2">
                      <div className="flex items-start justify-between gap-2">
                        <CardTitle className="flex items-center gap-2 text-base">
                          <Icon className="h-5 w-5 text-steel-soft" />
                          {identity.title}
                        </CardTitle>
                        <Badge variant="outline">{service.category}</Badge>
                      </div>
                      {service.description && (
                        <CardDescription className="line-clamp-2">{service.description}</CardDescription>
                      )}
                    </CardHeader>
                    <CardContent className="space-y-2">
                      {kind === 'integrations' && isGatewayService && (
                        <p className="text-xs text-primary">Configured as a channel gateway</p>
                      )}
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

        {kind === 'integrations' && <div className="flex items-center justify-between gap-3 pt-2 border-t">
          <Button
            type="button"
            variant="link"
            className="h-auto p-0 text-sm"
            onClick={() => {
              onOpenChange(false);
              navigate('/integration-services/new');
            }}
          >
            Create custom service
          </Button>
        </div>}
      </DialogContent>
    </Dialog>
  );
}
