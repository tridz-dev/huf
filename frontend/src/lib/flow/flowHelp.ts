/**
 * Plain-language help copy for the Flow editor: one place, so hints stay consistent and are easy to review.
 * Keep it product language (no internal terms); every example must be something a user can type as is.
 */

/** Public guide (also in the repository at docs/flow/USER_GUIDE.md). */
export const FLOW_GUIDE_URL = 'https://github.com/tridz-dev/huf/blob/develop/docs/flow/USER_GUIDE.md';

export interface ShortcutHelp {
  keys: string;
  does: string;
}

export const FLOW_SHORTCUTS: ShortcutHelp[] = [
  { keys: 'Ctrl/Cmd + K', does: 'Search steps, flows and actions' },
  { keys: 'Ctrl/Cmd + S', does: 'Save the flow' },
  { keys: 'Ctrl/Cmd + Z', does: 'Undo any edit (Shift + Z or Ctrl + Y redoes it)' },
  { keys: 'Ctrl/Cmd + D', does: 'Duplicate the selected step' },
  { keys: 'Ctrl/Cmd + C, V', does: 'Copy and paste steps, also into another flow' },
  { keys: 'Shift + click or drag', does: 'Select several steps' },
  { keys: 'Delete or Backspace', does: 'Remove the selected step or connection (asks first)' },
  { keys: 'Tab', does: 'Move between the steps' },
  { keys: 'Enter', does: 'Open the "Add step" card that has focus' },
  { keys: 'Esc', does: 'Close a dialog or panel' },
  { keys: '?', does: 'Show every keyboard shortcut' },
];

/** The three things to do on an empty canvas. */
export const FIRST_RUN_STEPS = [
  'Choose what starts the flow.',
  'Add steps.',
  'Save, then Run or Publish.',
];

// ─── Transform ──────────────────────────────────────────────────────────

export interface TransformHelp {
  /** What the operation does, in one line. */
  summary: string;
  /** A tiny worked example: input and result. */
  example: string;
}

export const TRANSFORM_HELP: Record<string, TransformHelp> = {
  lower: { summary: 'Turns text into lowercase.', example: '"Hello World" becomes "hello world".' },
  upper: { summary: 'Turns text into uppercase.', example: '"Hello World" becomes "HELLO WORLD".' },
  trim: { summary: 'Removes spaces and line breaks from both ends of the text.', example: '"  Alice  " becomes "Alice".' },
  replace: { summary: 'Replaces part of the text with other text.', example: 'Replace "-" with " " in "a-b-c" gives "a b c".' },
  contains: { summary: 'Gives true when the text includes the words you look for, otherwise false.', example: '"order #42" contains "#42" gives true.' },
  starts_with: { summary: 'Gives true when the text begins with the words you give, otherwise false.', example: '"INV-1001" starts with "INV-" gives true.' },
  split_first: { summary: 'Keeps only the first part of the text, split at a separator (a space by default).', example: '"Ada Lovelace" gives "Ada".' },
  regex_extract: { summary: 'Pulls out the first piece of text that matches a pattern.', example: 'Pattern "[0-9]+" on "order 4521 shipped" gives "4521".' },
  concat: { summary: 'Joins several values into one piece of text.', example: 'Parts ["a","b","c"] with separator "-" gives "a-b-c".' },
  select: { summary: 'Keeps only some fields of each row.', example: 'Fields ["name"] on [{"name":"Ada","age":36}] gives [{"name":"Ada"}].' },
  filter: { summary: 'Keeps only the rows that pass a check. Write the check with row, for example row[\'amount\'] > 100.', example: "Rows with amounts 50 and 150, check row['amount'] > 100, keeps the 150 row." },
  sort: { summary: 'Puts the rows in order by one field.', example: 'Sort by "age", ascending: 20, 31, 45.' },
  limit: { summary: 'Keeps only the first few rows.', example: 'Count 2 on 5 rows keeps the first 2.' },
  group_by: { summary: 'Groups rows that share the same value in one field.', example: 'Group by "city": one group for Pune, one for Delhi.' },
  aggregate: { summary: 'Counts the rows or adds up, averages or finds the smallest or largest value of a field.', example: 'sum of "amount" over rows 10, 20, 30 gives 60.' },
  join: { summary: 'Combines two lists of rows where a field matches.', example: 'Orders joined with customers on customer id gives orders with customer details.' },
  lookup: { summary: 'Adds the matching row from another list to each row.', example: 'Add the customer row (as "customer") to every order.' },
  batch: { summary: 'Splits rows into groups of a fixed size.', example: 'Size 2 on 5 rows gives groups of 2, 2 and 1.' },
  distinct: { summary: 'Removes duplicate rows (compares one field, or the whole row).', example: 'Distinct on "email" keeps one row per email.' },
  coalesce: { summary: 'Gives the first value in the list that is not empty.', example: '[null, "", "backup"] gives "backup".' },
};

export interface ParamHelp {
  label: string;
  hint: string;
  placeholder?: string;
}

const PARAMS: Record<string, ParamHelp> = {
  text: { label: 'Text', hint: 'The text to work on. Pick data from the trigger or an earlier step.', placeholder: 'Hello World' },
  find: { label: 'Text to find', hint: 'The words to look for. Cannot be empty.', placeholder: '-' },
  with: { label: 'Replace with', hint: 'What to put in their place. Leave empty to remove the found text.', placeholder: ' ' },
  count: { label: 'How many', hint: 'A whole number.', placeholder: '5' },
  needle: { label: 'Look for', hint: 'The words to look for inside the text.', placeholder: '#42' },
  ignore_case: { label: 'Ignore capital letters', hint: 'Choose Yes to treat "A" and "a" as the same. Leave it not set for exact matching.' },
  prefix: { label: 'Starts with', hint: 'The words the text should begin with.', placeholder: 'INV-' },
  separator: { label: 'Separator', hint: 'The characters between parts. Leave empty to use a space.', placeholder: ',' },
  pattern: { label: 'Pattern', hint: 'A regular expression. For example [0-9]+ finds the first number.', placeholder: '[0-9]+' },
  group: { label: 'Group number', hint: 'Which bracketed part of the pattern to return. Leave empty for the whole match.', placeholder: '0' },
  default: { label: 'If nothing matches', hint: 'What to return when there is no match. Leave empty for nothing.', placeholder: 'unknown' },
  parts: { label: 'Parts to join', hint: 'A list, for example ["a","b"], or pick a list from an earlier step.', placeholder: '["a","b","c"]' },
  fields: { label: 'Fields to keep', hint: 'A list of field names.', placeholder: '["name","email"]' },
  rows: { label: 'Rows', hint: 'A list of records, usually from an earlier step. Pick it with Use data.', placeholder: '[{"name":"Ada"}]' },
  where: { label: 'Keep rows where', hint: "A check written with row, for example row['amount'] > 100.", placeholder: "row['amount'] > 100" },
  key: { label: 'Field', hint: 'The field to use, for example city or customer.name.', placeholder: 'city' },
  order: { label: 'Order', hint: 'asc for smallest first (default), desc for largest first.', placeholder: 'asc' },
  op: { label: 'What to calculate', hint: 'One of count, sum, avg, min, max.', placeholder: 'sum' },
  field: { label: 'Field', hint: 'The field to calculate on. Not needed for count.', placeholder: 'amount' },
  left: { label: 'First list', hint: 'The rows to keep.', placeholder: '[{"id":1}]' },
  right: { label: 'Second list', hint: 'The rows to match against.', placeholder: '[{"id":1,"name":"Ada"}]' },
  left_key: { label: 'Field in the first list', hint: 'The field to compare.', placeholder: 'customer_id' },
  right_key: { label: 'Field in the second list', hint: 'The field it must equal.', placeholder: 'id' },
  how: { label: 'Keep', hint: 'inner keeps only matches (default). left keeps every row of the first list.', placeholder: 'inner' },
  from: { label: 'Rows to look in', hint: 'The list that holds the extra information.', placeholder: '[{"id":1,"name":"Ada"}]' },
  on: { label: 'Field in the lookup list', hint: 'The field that must equal the field above. Leave empty to use the same name.', placeholder: 'id' },
  as: { label: 'Save the match as', hint: 'The new field that gets the matching row.', placeholder: 'customer' },
  size: { label: 'Group size', hint: 'How many rows in each group.', placeholder: '10' },
  values: { label: 'Values', hint: 'A list. The first value that is not empty is returned.', placeholder: '[null, "backup"]' },
};

/** Per-operation wording where the same field name means something different. */
const PARAM_OVERRIDES: Record<string, Partial<Record<string, ParamHelp>>> = {
  replace: { count: { label: 'Replace only the first', hint: 'How many matches to replace. Leave empty to replace all.', placeholder: '1' } },
  limit: { count: { label: 'Rows to keep', hint: 'How many rows to keep from the start.', placeholder: '10' } },
  sort: { key: { label: 'Sort by field', hint: 'The field that sets the order, for example age.', placeholder: 'age' } },
  group_by: { key: { label: 'Group by field', hint: 'Rows with the same value in this field end up together.', placeholder: 'city' } },
  distinct: { key: { label: 'Compare field', hint: 'Rows with the same value here count as duplicates. Leave empty to compare whole rows.', placeholder: 'email' } },
  lookup: { key: { label: 'Field in each row', hint: 'The field in your rows that points to the other list.', placeholder: 'customer_id' } },
  concat: { separator: { label: 'Separator', hint: 'The characters put between the parts. Leave empty for none.', placeholder: ', ' } },
  coalesce: { values: { label: 'Values', hint: 'A list of values. The first one that is not empty wins.', placeholder: '[null, "backup"]' } },
};

export function transformParamHelp(op: string | undefined, param: string): ParamHelp {
  return (op && PARAM_OVERRIDES[op]?.[param]) || PARAMS[param] || { label: param, hint: '' };
}

// ─── Condition ──────────────────────────────────────────────────────────

export const CONDITION_EXAMPLES: Array<{ text: string; meaning: string }> = [
  { text: "input['amount'] > 100", meaning: 'a number from the trigger is above 100' },
  { text: "input['status'] == 'paid'", meaning: 'a text value equals "paid" (use quotes for text)' },
  { text: "input['country'] in ['IN', 'US']", meaning: 'the value is one of a list' },
  { text: "input['vip'] and input['total'] >= 500", meaning: 'both must be true (use "or" for either, "not" to flip)' },
  { text: "startswith(input['sku'], 'AB-')", meaning: 'the text begins with AB- (also endswith)' },
  { text: "lower(input['status']) == 'paid'", meaning: 'ignores capital letters: Paid, PAID and paid all match' },
  { text: "number(input['amount']) > 100", meaning: 'treats text such as 150 from a form as a number' },
  { text: "input['note'] not in [None, '']", meaning: 'the field is not empty' },
];

const CONDITION_SYNTAX =
  "Compare with ==, !=, >, >=, <, <= or in, and combine checks with and, or, not. Also available: lower(), number(), startswith() and endswith().";

/** Help under the Condition box. Only people who can edit are told about the Use data button. */
export function conditionHelp(canEdit: boolean): string {
  return canEdit
    ? `Write a check that is true or false. Read the trigger data as input['field'], and use + Use data for an earlier step's result. ${CONDITION_SYNTAX}`
    : `A check that is true or false. Trigger data is read as input['field']. ${CONDITION_SYNTAX}`;
}

// ─── Data trigger ───────────────────────────────────────────────────────

export const DOC_EVENT_HELP: Record<string, string> = {
  after_insert: 'Runs once, right after a new record is saved for the first time.',
  on_update: 'Runs every time an existing record is saved with changes.',
  on_submit: 'Runs when a record is submitted. Only for document types that can be submitted.',
  on_cancel: 'Runs when a submitted record is cancelled. Only for document types that can be submitted.',
  on_trash: 'Runs when a record is deleted.',
};

// ─── Schedule ───────────────────────────────────────────────────────────

export const SCHEDULE_EXAMPLES: Array<{ cron: string; meaning: string }> = [
  { cron: '*/15 * * * *', meaning: 'every 15 minutes' },
  { cron: '0 9 * * 1-5', meaning: 'weekdays at 09:00' },
  { cron: '30 18 1 * *', meaning: 'on the 1st of each month at 18:30' },
];

// ─── Webhook ────────────────────────────────────────────────────────────

export const WEBHOOK_RESPONSES: Array<{ code: string; meaning: string }> = [
  { code: '200', meaning: 'The flow started. The answer holds the run id.' },
  { code: '403', meaning: 'Wrong or missing secret, or the flow is not live yet.' },
  { code: '405', meaning: 'The request used a different method than the one chosen above.' },
  { code: '429', meaning: 'Too many calls (more than 60 a minute from one address).' },
];

// ─── Human approval ─────────────────────────────────────────────────────

export const APPROVER_TYPE_HELP: Record<string, string> = {
  role: 'Anyone who has this role can approve or reject. The first answer counts.',
  user: 'Only the people you list can approve or reject. The first answer counts.',
};

export const APPROVAL_TIMEOUT_HELP =
  'If nobody answers in time, the flow follows the "Timed out" path. Leave empty to wait for as long as it takes.';

// ─── Loop ───────────────────────────────────────────────────────────────

export const LOOP_HELP =
  "Runs the steps on the 'For each item' path once for every entry of a list, one after the other, then continues on 'When done'. Inside the loop, pick the current entry with Use data.";

// ─── Integrations ───────────────────────────────────────────────────────

export const INTEGRATION_NEEDS: Record<string, string> = {
  email: 'Needs Gmail to be connected in Integrations. It sends from that account.',
  slack: 'Needs Slack to be connected in Integrations, and the bot invited to the channel.',
  sheets: 'Needs Google Sheets to be connected in Integrations.',
  file: 'Needs Google Drive to be connected in Integrations.',
};

/** A note shown under a step name in the sidebar: what it needs and what it gives to the next step. */
export const STEP_NEEDS_HINT = 'Steps after this one can use its result: choose it in Use data.';
