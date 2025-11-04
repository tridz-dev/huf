import { Plug, CheckCircle2 } from 'lucide-react';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '../components/ui/card';
import { Button } from '../components/ui/button';
import { Badge } from '../components/ui/badge';
import { useEffect, useState } from 'react';
import { mockApi } from '../services/mockApi';
import { AIProvider, AIModel } from '../types/agent.types';

export function IntegrationsPage() {
  const [providers, setProviders] = useState<AIProvider[]>([]);
  const [models, setModels] = useState<AIModel[]>([]);

  useEffect(() => {
    Promise.all([
      mockApi.providers.list(),
      mockApi.models.list(),
    ]).then(([providersData, modelsData]) => {
      setProviders(providersData);
      setModels(modelsData);
    });
  }, []);

  const getModelCountForProvider = (providerName: string) => {
    return models.filter(m => m.provider === providerName).length;
  };

  return (
    <div className="h-full overflow-auto">
      <div className="p-6 space-y-6">
        <div>
          <p className="text-muted-foreground">
            Connect AI providers and external services
          </p>
        </div>

        <div>
          <h2 className="text-lg font-semibold mb-4">AI Providers</h2>
          <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
            {providers.map((provider) => (
              <Card key={provider.name}>
                <CardHeader>
                  <div className="flex items-start justify-between">
                    <div className="flex items-center gap-3">
                      <div className="w-10 h-10 rounded-lg bg-primary/10 flex items-center justify-center">
                        <Plug className="w-5 h-5 text-primary" />
                      </div>
                      <div>
                        <CardTitle className="text-base">{provider.provider_name}</CardTitle>
                        <CardDescription className="text-xs">
                          {getModelCountForProvider(provider.name)} models
                        </CardDescription>
                      </div>
                    </div>
                    <CheckCircle2 className="w-5 h-5 text-muted-foreground" />
                  </div>
                </CardHeader>
                <CardContent>
                  <div className="flex flex-wrap gap-2 mb-3">
                    {models
                      .filter(m => m.provider === provider.name)
                      .slice(0, 3)
                      .map(model => (
                        <Badge key={model.name} variant="secondary" className="text-xs">
                          {model.model_name}
                        </Badge>
                      ))}
                  </div>
                  <div className="flex gap-2">
                    <Button variant="outline" size="sm" className="flex-1">
                      Configure
                    </Button>
                    <Button variant="ghost" size="sm" className="flex-1">
                      Test
                    </Button>
                  </div>
                </CardContent>
              </Card>
            ))}
          </div>
        </div>
      </div>
    </div>
  );
}
