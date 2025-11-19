import type { ToolUIPart } from "ai";

export type ExtendedToolState =
  | ToolUIPart["state"]
  | "approval-requested"
  | "approval-responded"
  | "output-denied";

