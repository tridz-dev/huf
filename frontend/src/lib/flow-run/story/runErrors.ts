/**
 * A run's error as a person reads it: no engine words ("Node ... of type ... declares no on_error successor"),
 * no Python class names, no internal prefixes ("state.set:"), no tool or key ids.
 */

const ENGINE_WRAPPER = /^Node '[^']+' of type '[^']+' failed and declares no on_error successor: ([\s\S]*)$/;
const PYTHON_CLASS = /^(?:[A-Za-z]+\.)*[A-Z][A-Za-z]*(?:Error|Exception|Exit|Interrupt):\s*/;
const INTERNAL_PREFIX = /^(?:state\.(?:set|get|delete)|flow\.\w+|engine|foreach|tool\.call|agent\.run|code\.run):\s*/i;

const TRANSLATIONS: Array<[RegExp, (m: RegExpExecArray) => string]> = [
  [/absolute path '([^']+)' is outside the sandbox workspace/i, (m) => `The code tried to open a file it is not allowed to use (${m[1]}). Only files inside the flow's own workspace can be used.`],
  [/Import of module '([^']+)' is not permitted[^.]*\.?/i, (m) => `The code tried to use "${m[1]}", which this step is not allowed to use. Change the code, or ask an admin to allow it.`],
  [/Execution approval rejected by ([^\s.]+(?:\.[^\s.]+)*)\.?/i, (m) => `${m[1]} did not approve running this code.`],
  [/Requests to private\/internal addresses are not allowed\.?/i, () => 'That address is on a private network, so this step cannot reach it. Use a public address, or ask an admin.'],
  [/another run was saving the same key at that moment\./i, () => 'another run was saving the same value at that moment.'],
];

/** The reason a step failed, in plain words. `stepTitle` drops a repeated "<step> failed: " lead-in. */
export function plainRunError(message: string | null | undefined, stepTitle?: string | null): string {
  let text = (message ?? '').trim();
  if (!text) return '';
  const wrapped = ENGINE_WRAPPER.exec(text);
  if (wrapped) text = wrapped[1];
  if (stepTitle && text.startsWith(`${stepTitle} failed: `)) text = text.slice(stepTitle.length + ' failed: '.length);
  for (let i = 0; i < 3; i += 1) {
    const before = text;
    text = text.replace(INTERNAL_PREFIX, '').replace(PYTHON_CLASS, '');
    if (text === before) break;
  }
  for (const [re, make] of TRANSLATIONS) {
    const m = re.exec(text);
    if (m) text = text.replace(re, make(m));
  }
  text = text.replace(/\s*Connect it in Integrations\.?$/i, '').trim();
  // A sentence that starts with an address or user name ("ada@example.com did not approve...") keeps it as typed.
  if (/^[^\s@]+@\S+/.test(text)) return text;
  return text.charAt(0).toUpperCase() + text.slice(1);
}
