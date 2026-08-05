import { Skeleton } from '@/components/ui/skeleton';
import { Tabs, TabsList, TabsTrigger } from '@/components/ui/tabs';
import { Button } from '@/components/ui/button';
import { SkeletonListView } from '../views/SkeletonListView';
import { Card, CardContent, CardHeader } from '@/components/ui/card';

export function DashboardPageLoader() {
  return (
    <div className="h-full overflow-auto">
      <div className="p-6 space-y-6">
        <div>
          <Skeleton className="h-10 w-48" />
          <Skeleton className="h-4 w-72 mt-2" />
        </div>

        <div className="border border-ink grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 divide-y sm:divide-y-0 sm:divide-x divide-line">
          {Array.from({ length: 4 }).map((_, index) => (
            <div key={`metric-skeleton-${index}`} className="p-4 min-w-0 space-y-2">
              <Skeleton className="h-3 w-24" />
              <Skeleton className="h-3 w-16" />
              <Skeleton className="h-[38px] w-24" />
            </div>
          ))}
        </div>

        <div className="space-y-4">
          <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
            <Tabs value="agents">
              <TabsList>
                <TabsTrigger value="agents" disabled>
                  Agents
                </TabsTrigger>
                <TabsTrigger value="flows" disabled>
                  Flows
                </TabsTrigger>
                <TabsTrigger value="executions" disabled>
                  Executions
                </TabsTrigger>
              </TabsList>
            </Tabs>
            <Button variant="outline" size="sm" disabled>
              Show more
            </Button>
          </div>

          <Card>
            <CardHeader>
              <Skeleton className="h-6 w-36" />
            </CardHeader>
            <CardContent className="min-h-[520px]">
              <SkeletonListView count={10} showLeadingDot />
            </CardContent>
          </Card>
        </div>
      </div>
    </div>
  );
}
