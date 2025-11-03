import { useNavigate } from 'react-router-dom';
import { Button } from '../components/ui/button';
import { Home, AlertCircle } from 'lucide-react';

export function NotFoundPage() {
  const navigate = useNavigate();

  return (
    <div className="h-full flex items-center justify-center">
      <div className="text-center space-y-6 max-w-md">
        <div className="flex justify-center">
          <div className="w-16 h-16 rounded-full bg-destructive/10 flex items-center justify-center">
            <AlertCircle className="w-8 h-8 text-destructive" />
          </div>
        </div>

        <div>
          <h1 className="text-4xl font-bold mb-2">404</h1>
          <h2 className="text-xl font-semibold mb-2">Page Not Found</h2>
          <p className="text-muted-foreground">
            The page you're looking for doesn't exist or has been moved.
          </p>
        </div>

        <div className="flex gap-3 justify-center">
          <Button onClick={() => navigate(-1)} variant="outline">
            Go Back
          </Button>
          <Button onClick={() => navigate('/')}>
            <Home className="w-4 h-4 mr-2" />
            Back to Dashboard
          </Button>
        </div>
      </div>
    </div>
  );
}
