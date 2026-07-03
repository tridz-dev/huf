import { ExternalLink, Video, CalendarPlus } from 'lucide-react';
import { Badge } from '@/components/ui/badge';

export function GoogleMeetTab() {
  return (
    <div className="space-y-6 rounded-lg border p-6">
      <div>
        <h3 className="text-sm font-medium">Available tools</h3>
        <p className="text-sm text-muted-foreground mt-1">
          Agents can call these tools once this integration is configured and active.
        </p>
        <div className="mt-3 space-y-3">
          <div className="flex items-start gap-3 rounded-md border p-3">
            <Video className="h-4 w-4 mt-0.5 text-muted-foreground shrink-0" />
            <div>
              <div className="flex items-center gap-2">
                <span className="text-sm font-medium">google_meet_create_space</span>
                <Badge variant="secondary">Tool</Badge>
              </div>
              <p className="text-sm text-muted-foreground">
                Creates a standalone Google Meet space and returns its meeting code and join URL.
              </p>
            </div>
          </div>
          <div className="flex items-start gap-3 rounded-md border p-3">
            <CalendarPlus className="h-4 w-4 mt-0.5 text-muted-foreground shrink-0" />
            <div>
              <div className="flex items-center gap-2">
                <span className="text-sm font-medium">google_meet_create_event</span>
                <Badge variant="secondary">Tool</Badge>
              </div>
              <p className="text-sm text-muted-foreground">
                Creates a Google Calendar event with a Meet conference attached, returning the event
                link and join URL.
              </p>
            </div>
          </div>
        </div>
      </div>

      <div>
        <h3 className="text-sm font-medium">Setup</h3>
        <p className="text-sm text-muted-foreground mt-1">
          This integration authenticates via Google OAuth. Enter the credentials below on the
          Credentials tab:
        </p>
        <ul className="mt-2 list-disc list-inside text-sm text-muted-foreground space-y-1">
          <li><span className="font-mono text-xs">client_id</span> — OAuth client ID from Google Cloud Console</li>
          <li><span className="font-mono text-xs">client_secret</span> — OAuth client secret</li>
          <li><span className="font-mono text-xs">refresh_token</span> — a refresh token for a user/service account with Calendar and Meet scopes</li>
        </ul>
        <a
          href="https://developers.google.com/workspace/meet/api/guides/overview"
          target="_blank"
          rel="noreferrer"
          className="mt-3 inline-flex items-center gap-1 text-sm text-primary hover:underline"
        >
          Google Meet API documentation
          <ExternalLink className="h-3 w-3" />
        </a>
      </div>
    </div>
  );
}
