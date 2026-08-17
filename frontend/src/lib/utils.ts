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
