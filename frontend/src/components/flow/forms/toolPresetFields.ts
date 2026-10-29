/** Fallback `input` keys per preset tool, used until/unless the tool's own schema is loaded. */
export const PRESET_FIELDS: Record<string, Array<{ key: string; label: string; optional?: boolean; placeholder?: string; hint?: string }>> = {
  gmail_send_email: [
    { key: 'to', label: 'To', placeholder: 'name@example.com', hint: 'One address, or several separated by commas.' },
    { key: 'subject', label: 'Subject', hint: 'The subject line of the email.' },
    { key: 'body', label: 'Body', hint: 'The message text. Use Insert data to add details from earlier steps.' },
  ],
  slack_send_message: [
    { key: 'channel', label: 'Channel', placeholder: '#general', hint: 'The channel name (like #general) or the channel ID. The bot must be invited to it.' },
    { key: 'text', label: 'Message', hint: 'The text to post. Use Insert data to add details from earlier steps.' },
  ],
  slack_send_thread_reply: [
    { key: 'channel', label: 'Channel', placeholder: '#general', hint: 'The channel name (like #general) or the channel ID. The bot must be invited to it.' },
    { key: 'thread_ts', label: 'Thread', placeholder: '1712345678.000100', hint: 'The timestamp of the first message in the thread: right-click it, then Copy link; it is the number after "p".' },
    { key: 'text', label: 'Message', hint: 'The text of the reply.' },
  ],
  gsheets_read: [
    { key: 'spreadsheet_id', label: 'Spreadsheet ID', placeholder: '1AbC...xYz', hint: 'In the sheet URL, the long text between /d/ and /edit.' },
    { key: 'range', label: 'Range', optional: true, placeholder: 'Sheet1!A1:D20', hint: 'Which cells to read. Leave empty to read the first sheet.' },
  ],
  gsheets_update: [
    { key: 'spreadsheet_id', label: 'Spreadsheet ID', placeholder: '1AbC...xYz', hint: 'In the sheet URL, the long text between /d/ and /edit.' },
    { key: 'range', label: 'Range', placeholder: 'Sheet1!A1:D20', hint: 'Where to write, starting cell first. Existing cells there are replaced.' },
    { key: 'data', label: 'Data', hint: 'The rows to write, as a list of lists: [["Name","Amount"],["Ada",120]]. Choose JSON as the value type.' },
  ],
  gsheets_create: [{ key: 'title', label: 'Title', hint: 'The name of the new spreadsheet.', placeholder: 'Weekly report' }],
  gdrive_list_files: [
    { key: 'limit', label: 'Limit', optional: true, placeholder: '20', hint: 'The most files to list. Leave empty for the default.' },
    { key: 'query', label: 'Query', optional: true, placeholder: "name contains 'invoice'", hint: 'Optional filter written in Google Drive search syntax.' },
  ],
  gdrive_search_files: [{ key: 'query', label: 'Search for', placeholder: 'invoice', hint: 'Words to look for in file names and content.' }],
  gdrive_get_file: [
    { key: 'file_id', label: 'File ID', placeholder: '1AbC...xYz', hint: 'In Drive, open the file and copy the text after /d/ (or after id=) in its URL.' },
  ],
};
