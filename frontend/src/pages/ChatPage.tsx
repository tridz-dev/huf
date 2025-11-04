import { MessageSquare } from 'lucide-react';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '../components/ui/card';
import { Button } from '../components/ui/button';

export function ChatPage() {
  return (
    <div className="h-full overflow-auto">
      <div className="p-6 space-y-6">
        <div>
          <p className="text-muted-foreground">
            Chat with your AI agents
          </p>
        </div>

        <Card className="border-dashed">
          <CardHeader className="text-center pb-4">
            <div className="flex justify-center mb-4">
              <MessageSquare className="w-12 h-12 text-muted-foreground" />
            </div>
            <CardTitle className="text-lg">Coming Soon</CardTitle>
            <CardDescription>
              Chat interface will be available here
            </CardDescription>
          </CardHeader>
          <CardContent className="flex justify-center">
            <Button variant="outline">Learn More</Button>
          </CardContent>
        </Card>
      </div>
    </div>
  );
}
