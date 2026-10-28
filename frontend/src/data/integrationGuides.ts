/** Short setup guides shown on the Integrations screen for services whose credentials come from another site. */

export interface IntegrationGuide {
  title: string;
  steps: string[];
  /** Exactly the permissions the Huf tools for this service need. */
  scopes: string;
}

export const INTEGRATION_GUIDES: Record<string, IntegrationGuide> = {
  gmail: {
    title: 'How to connect Gmail',
    steps: [
      'In Google Cloud Console, create a project and turn on the Gmail API.',
      'Create an OAuth client ID (type: Web application) and copy its client ID and client secret.',
      'Authorize the scope below for your Google account, for example with Google\'s OAuth Playground, and copy the refresh token.',
      'Paste the three values on the Credentials tab, then press Test connection.',
    ],
    scopes: 'Scopes: gmail.send to send email. Add gmail.readonly to read email, gmail.compose for drafts and gmail.modify to mark email as read.',
  },
  google_sheets: {
    title: 'How to connect Google Sheets',
    steps: [
      'In Google Cloud Console, create a project and turn on the Google Sheets API.',
      'Create an OAuth client ID (type: Web application) and copy its client ID and client secret.',
      'Authorize the scope below for your Google account, for example with Google\'s OAuth Playground, and copy the refresh token.',
      'Paste the three values on the Credentials tab, then press Test connection.',
    ],
    scopes: 'Scope: spreadsheets (read, update and create sheets).',
  },
  google_drive: {
    title: 'How to connect Google Drive',
    steps: [
      'In Google Cloud Console, create a project and turn on the Google Drive API.',
      'Create an OAuth client ID (type: Web application) and copy its client ID and client secret.',
      'Authorize the scope below for your Google account, for example with Google\'s OAuth Playground, and copy the refresh token.',
      'Paste the three values on the Credentials tab, then press Test connection.',
    ],
    scopes: 'Scope: drive.readonly to list, search and read files (or drive for full access).',
  },
  slack: {
    title: 'How to connect Slack',
    steps: [
      'Create a Slack app at api.slack.com/apps (From scratch) in your workspace.',
      'Under OAuth & Permissions, add the bot token scopes below.',
      'Install the app to your workspace and copy the Bot User OAuth Token (it starts with xoxb-).',
      'Paste the token on the Credentials tab, then press Test connection. Invite the bot to any channel it should post in.',
    ],
    scopes: 'Bot scopes: chat:write to post messages. Add channels:read and groups:read to list channels, channels:history and groups:history to read history, and users:read to list people.',
  },
};

/** Services that have a Test connection button. */
export const TESTABLE_SERVICES = Object.keys(INTEGRATION_GUIDES);
