import { clsx, type ClassValue } from 'clsx';
import { extendTailwindMerge } from 'tailwind-merge';

// tailwind.config.js defines custom scale keys (control-sm/md/lg, chat-row,
// chat-header, chat-footer, chat-rail, chat-turn, chat-measure, chat-bubble,
// chat-send, ...) on top of Tailwind's default spacing/height/width/radius
// scales. A plain, unconfigured `twMerge` has no idea these keys exist, so it
// does not recognise `h-control-md` and `size-[26px]` (or `px-control` and
// `px-[13px]`) as members of the same conflict group — BOTH classes survive
// into the DOM and whichever one the component itself wrote wins the
// cascade, silently discarding any override passed in via `className`. This
// was found when `<Button size="icon" className="size-[26px]">` measured
// 34x34 in the live page instead of 26x26. `extendTailwindMerge` teaches
// tailwind-merge about every custom key so overrides can actually win.
const cnMerge = extendTailwindMerge({
  extend: {
    classGroups: {
      // Custom font-size utilities from tailwind.config.js `fontSize`. Without
      // these, tailwind-merge reads `text-micro` as a text COLOUR and drops it
      // when a real colour class (text-steel) follows, or vice versa.
      'font-size': [
        { text: ['display', 'title', 'subtitle', 'micro', 'body-text', 'ui-text', 'meta', 'eyebrow'] },
      ],
      // Each classGroup entry must mirror tailwind-merge's own default-config
      // shape: `<groupId>: [{ <groupId>: [suffixes...] }]`. The inner object
      // key is what actually gets walked into the class-name trie (`h-` +
      // suffix); the outer key only tags which conflict group it joins.
      h: [{ h: ['control-sm', 'control-md', 'control-lg', 'chat-row', 'chat-header', 'chat-footer'] }],
      w: [{ w: ['control-sm', 'control-md', 'control-lg', 'chat-rail'] }],
      px: [{ px: ['control', 'control-sm', 'control-lg'] }],
      py: [{ py: ['control-y'] }],
      p: [{ p: ['control', 'control-sm', 'control-lg', 'control-y'] }],
      gap: [{ gap: ['chat-turn'] }],
      'max-w': [{ 'max-w': ['chat-measure'] }],
      rounded: [{ rounded: ['chat-row', 'chat-bubble', 'chat-send'] }],
    },
  },
});

export function cn(...inputs: ClassValue[]) {
  return cnMerge(clsx(inputs));
}

/**
 * Run independent promises together without one denial/failure taking the
 * rest down with it (the failure mode of a plain `Promise.all` when one
 * branch is a 403-denied API call). Each slot resolves to its value on
 * success or `undefined` on failure; `onError` is called per failed slot so
 * callers can toast or log without losing the others.
 */
export async function settleAll<T extends readonly unknown[]>(
  promises: readonly [...{ [K in keyof T]: Promise<T[K]> }],
  onError?: (index: number, error: unknown) => void,
): Promise<{ [K in keyof T]: T[K] | undefined }> {
  const results = await Promise.allSettled(promises);
  return results.map((result, index) => {
    if (result.status === 'fulfilled') {
      return result.value;
    }
    onError?.(index, result.reason);
    return undefined;
  }) as { [K in keyof T]: T[K] | undefined };
}

/**
 * The visible text of a sidebar button is hidden when the sidebar is collapsed to icons: keep the control
 * named for assistive tech by falling back to its tooltip text as the accessible name.
 */
export function nameWhenCollapsed<P extends { 'aria-label'?: string }>(
  props: P,
  collapsed: boolean,
  tooltip: string | { children?: unknown } | undefined,
): P {
  const text = typeof tooltip === 'string' ? tooltip : typeof tooltip?.children === 'string' ? tooltip.children : undefined;
  return { ...props, 'aria-label': props['aria-label'] ?? (collapsed ? text : undefined) };
}
