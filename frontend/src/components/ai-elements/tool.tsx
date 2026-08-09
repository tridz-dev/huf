"use client";

import {
  Collapsible,
  CollapsibleContent,
  CollapsibleTrigger,
} from "@/components/ui/collapsible";
import { cn } from "@/lib/utils";
import type { ToolUIPart } from "ai";
import { ChevronRightIcon, Layers2Icon, ShieldAlertIcon, WrenchIcon } from "lucide-react";
import type { ComponentProps, ReactNode } from "react";
import { isValidElement, useState } from "react";
import { CodeBlock } from "./code-block";
import { Video } from "./video";
import { extractVideoFromToolResult } from "@/components/chat/videoDetection";
import type { ExtendedToolState } from "./types";

export type ToolProps = ComponentProps<typeof Collapsible>;

// A tool call is a footnote to the answer, not a card: no border, no fill,
// just a slim collapsible line.
export const Tool = ({ className, ...props }: ToolProps) => (
  <Collapsible className={cn("not-prose mb-1 w-full", className)} {...props} />
);

const STATUS_LABELS: Record<ExtendedToolState, string> = {
  "input-streaming": "pending",
  "input-available": "running",
  "approval-requested": "needs approval",
  "approval-responded": "responded",
  "output-available": "done",
  "output-error": "failed",
  "output-denied": "denied",
};

const STATUS_DOT_CLASSES: Record<ExtendedToolState, string> = {
  "input-streaming": "bg-muted-foreground/40",
  "input-available": "bg-warning",
  "approval-requested": "bg-warning",
  "approval-responded": "bg-muted-foreground/40",
  "output-available": "bg-good",
  "output-error": "bg-destructive",
  "output-denied": "bg-destructive",
};

function formatDuration(ms: number): string {
  if (ms < 1000) return `${Math.round(ms)}ms`;
  return `${(ms / 1000).toFixed(1)}s`;
}

/**
 * Inline Allow/Deny pair for an `approval-requested` tool call, matching the
 * lightweight text/mini-button treatment already used for the "Retry"
 * button — no card, no dialog, just two small buttons inline in the 24px row.
 */
function ApprovalActions({
  onApprove,
  onDeny,
}: {
  onApprove?: () => void;
  onDeny?: () => void;
}) {
  return (
    <div className="flex shrink-0 items-center gap-1.5">
      <button
        type="button"
        onClick={(event) => {
          event.stopPropagation();
          onApprove?.();
        }}
        className="rounded-[5px] bg-foreground px-2 py-[3px] text-[11px] font-medium text-background hover:opacity-90"
      >
        Allow
      </button>
      <button
        type="button"
        onClick={(event) => {
          event.stopPropagation();
          onDeny?.();
        }}
        className="rounded-[5px] border border-line px-2 py-[3px] text-[11px] font-medium text-foreground hover:bg-muted/60"
      >
        Deny
      </button>
    </div>
  );
}

export type ToolHeaderProps = {
  title?: string;
  type: ToolUIPart["type"];
  state: ExtendedToolState;
  /** Client-side approximated elapsed time, in ms, once the tool reaches a terminal state. */
  durationMs?: number;
  /** Shown as a "Retry" text-button next to the failed-state text, when provided. */
  onRetry?: () => void;
  /** Shown as an inline "Allow" button when state is "approval-requested". */
  onApprove?: () => void;
  /** Shown as an inline "Deny" button when state is "approval-requested". */
  onDeny?: () => void;
  className?: string;
};

export const ToolHeader = ({
  className,
  title,
  type,
  state,
  durationMs,
  onRetry,
  onApprove,
  onDeny,
  ...props
}: ToolHeaderProps) => {
  const isFailed = state === "output-error";
  const isApprovalNeeded = state === "approval-requested";
  const toneClass = isFailed
    ? "text-destructive"
    : isApprovalNeeded
      ? "text-warning"
      : "text-muted-foreground";
  const ToolIcon = isApprovalNeeded ? ShieldAlertIcon : WrenchIcon;

  return (
    <div className="flex items-center gap-2">
      <CollapsibleTrigger
        className={cn(
          "group flex min-w-0 flex-1 items-center gap-1.5 rounded-[7px] px-[7px] py-[3px] -ml-[7px] text-left leading-[24px] transition-colors hover:bg-muted/60",
          className
        )}
        {...props}
      >
        <ToolIcon
          className={cn(
            "size-[13px] shrink-0",
            isFailed ? "text-destructive" : isApprovalNeeded ? "text-warning" : "text-muted-foreground"
          )}
        />
        <span className="truncate font-mono text-[12px] text-foreground">
          {title ?? type.split("-").slice(1).join("-")}
        </span>
        <span className="shrink-0 text-muted-foreground/50">&middot;</span>
        <span className={cn("shrink-0 text-[12px]", toneClass)}>
          {STATUS_LABELS[state]}
        </span>
        {durationMs !== undefined && (
          <span className="shrink-0 font-mono text-[11px] text-muted-foreground">
            {formatDuration(durationMs)}
          </span>
        )}
        {!isApprovalNeeded && (
          <ChevronRightIcon className="ml-auto size-[13px] shrink-0 text-muted-foreground transition-transform group-data-[state=open]:rotate-90" />
        )}
      </CollapsibleTrigger>
      {isFailed && onRetry && (
        <button
          type="button"
          onClick={(event) => {
            event.stopPropagation();
            onRetry();
          }}
          className="shrink-0 text-[12px] text-destructive hover:underline underline-offset-2"
        >
          Retry
        </button>
      )}
      {isApprovalNeeded && (
        <>
          <ApprovalActions onApprove={onApprove} onDeny={onDeny} />
          {/* Row stays expandable while approval is pending, so the user can
           * inspect the call's input/output before deciding — this second
           * trigger (bound to the same Collapsible) keeps the chevron at the
           * far right, matching every other state, with Allow/Deny just
           * before it. */}
          <CollapsibleTrigger
            className="group shrink-0 rounded-[5px] p-[3px] text-muted-foreground hover:bg-muted/60"
            aria-label="Toggle details"
          >
            <ChevronRightIcon className="size-[13px] shrink-0 transition-transform group-data-[state=open]:rotate-90" />
          </CollapsibleTrigger>
        </>
      )}
    </div>
  );
};

export type ToolContentProps = ComponentProps<typeof CollapsibleContent>;

export const ToolContent = ({ className, ...props }: ToolContentProps) => (
  <CollapsibleContent
    className={cn(
      "mt-1 space-y-2 border-line/60 border-l pl-3 text-popover-foreground outline-none data-[state=closed]:fade-out-0 data-[state=closed]:slide-out-to-top-2 data-[state=open]:slide-in-from-top-2 data-[state=closed]:animate-out data-[state=open]:animate-in",
      className
    )}
    {...props}
  />
);

/**
 * Formats an arbitrary tool payload as a single-line, truncated, mono key-summary,
 * e.g. `{ description: "hello" }`. Used as the default (non-code-block) view for
 * tool input/output — payloads are a footnote, not a syntax-highlighted panel.
 */
export function summarizeToolPayload(payload: unknown, maxKeys = 4): string {
  if (payload === null || payload === undefined) return "{}";
  if (typeof payload === "string") {
    return payload.length > 80 ? `${payload.slice(0, 80)}…` : payload;
  }
  if (typeof payload !== "object") return String(payload);
  if (Array.isArray(payload)) {
    return `[${payload.length} item${payload.length === 1 ? "" : "s"}]`;
  }

  const entries = Object.entries(payload as Record<string, unknown>);
  if (entries.length === 0) return "{}";

  const shown = entries.slice(0, maxKeys);
  const parts = shown.map(([key, value]) => `${key}: ${summarizeValue(value)}`);
  const remaining = entries.length - shown.length;
  const rest = remaining > 0 ? `, …+${remaining}` : "";
  return `{ ${parts.join(", ")}${rest} }`;
}

function summarizeValue(value: unknown, maxLen = 40): string {
  if (value === null) return "null";
  if (value === undefined) return "undefined";
  if (typeof value === "string") {
    const truncated = value.length > maxLen ? `${value.slice(0, maxLen)}…` : value;
    return JSON.stringify(truncated);
  }
  if (typeof value === "number" || typeof value === "boolean") return String(value);
  if (Array.isArray(value)) {
    return `[${value.length} item${value.length === 1 ? "" : "s"}]`;
  }
  if (typeof value === "object") {
    const keys = Object.keys(value as Record<string, unknown>);
    return `{${keys.length} field${keys.length === 1 ? "" : "s"}}`;
  }
  return String(value);
}

async function copyJson(json: string): Promise<void> {
  if (typeof window === "undefined" || !navigator?.clipboard?.writeText) return;
  try {
    await navigator.clipboard.writeText(json);
  } catch {
    // Clipboard unavailable or denied — silently no-op, this is a non-critical affordance.
  }
}

function PayloadActions({
  json,
  showRaw,
  onToggleRaw,
}: {
  json: string;
  showRaw: boolean;
  onToggleRaw: () => void;
}) {
  return (
    <div className="flex items-center gap-3">
      <button
        type="button"
        onClick={() => void copyJson(json)}
        className="text-[11px] text-muted-foreground hover:text-foreground hover:underline"
      >
        Copy JSON
      </button>
      <button
        type="button"
        onClick={onToggleRaw}
        className="text-[11px] text-muted-foreground hover:text-foreground hover:underline"
      >
        {showRaw ? "Hide raw" : "Raw"}
      </button>
    </div>
  );
}

export type ToolInputProps = ComponentProps<"div"> & {
  input: ToolUIPart["input"];
};

export const ToolInput = ({ className, input, ...props }: ToolInputProps) => {
  const [showRaw, setShowRaw] = useState(false);
  const json = JSON.stringify(input, null, 2);
  const summary = summarizeToolPayload(input);

  return (
    <div className={cn("space-y-1.5 py-1", className)} {...props}>
      <div className="truncate font-mono text-xs text-muted-foreground">{summary}</div>
      <PayloadActions json={json} showRaw={showRaw} onToggleRaw={() => setShowRaw((v) => !v)} />
      {showRaw && (
        <div className="rounded-md bg-muted/50">
          <CodeBlock code={json} language="json" />
        </div>
      )}
    </div>
  );
};

export type ToolOutputProps = ComponentProps<"div"> & {
  output: ToolUIPart["output"];
  errorText: ToolUIPart["errorText"];
};

export const ToolOutput = ({
  className,
  output,
  errorText,
  ...props
}: ToolOutputProps) => {
  const [showRaw, setShowRaw] = useState(false);

  if (!(output || errorText)) {
    return null;
  }

  const detectedVideo = output ? extractVideoFromToolResult(output) : null;
  const isElementOutput = isValidElement(output);

  if (detectedVideo) {
    return (
      <div className={cn("py-1", className)} {...props}>
        <Video
          src={detectedVideo.src}
          mediaType={detectedVideo.mediaType}
          title={detectedVideo.title}
          poster={detectedVideo.poster}
          downloadName={detectedVideo.downloadName}
          className="max-w-md"
        />
      </div>
    );
  }

  if (isElementOutput) {
    return (
      <div className={cn("py-1", className)} {...props}>
        {output as ReactNode}
      </div>
    );
  }

  const json = errorText ?? (typeof output === "string" ? output : JSON.stringify(output, null, 2));
  const summary = errorText
    ? errorText.length > 120
      ? `${errorText.slice(0, 120)}…`
      : errorText
    : typeof output === "string"
      ? output.length > 80
        ? `${output.slice(0, 80)}…`
        : output
      : summarizeToolPayload(output);

  return (
    <div className={cn("space-y-1.5 py-1", className)} {...props}>
      <div
        className={cn(
          "truncate font-mono text-xs",
          errorText ? "text-destructive" : "text-muted-foreground"
        )}
      >
        {summary}
      </div>
      <PayloadActions json={json} showRaw={showRaw} onToggleRaw={() => setShowRaw((v) => !v)} />
      {showRaw && (
        <div
          className={cn(
            "overflow-x-auto rounded-md text-xs [&_table]:w-full",
            errorText ? "bg-destructive/10 text-destructive" : "bg-muted/50 text-foreground"
          )}
        >
          <CodeBlock code={json} language={errorText ? "text" : "json"} />
        </div>
      )}
    </div>
  );
};

/**
 * A single tool call within a `ToolGroup`. Deliberately a narrower shape than
 * the full tool-call record so `ToolGroup` can be fed straight from
 * `MessageType["tools"]` without re-mapping status names.
 */
export type ToolGroupCall = {
  /** Identifies the call to `onApprove`/`onDeny` — required to act on an `approval-requested` call. */
  callId?: string;
  name: string;
  state: ExtendedToolState;
  input?: unknown;
  output?: unknown;
  errorText?: string;
  durationMs?: number;
};

export type ToolGroupProps = ComponentProps<typeof Collapsible> & {
  calls: ToolGroupCall[];
  /** Called with the call's `callId` when its inline "Allow" button is clicked. */
  onApprove?: (callId: string) => void;
  /** Called with the call's `callId` when its inline "Deny" button is clicked. */
  onDeny?: (callId: string) => void;
};

/**
 * Consecutive tool calls in the same turn collapse into a single group line:
 * a stack icon, "Ran N tools", a mono grey "name ×count" summary, and total
 * duration. Expanding reveals a compact per-call row (not the full `Tool`
 * card) so the group still reads as one footnote, not N cards stacked.
 *
 * Grouping boundary: this groups an entire message's `tools[]` as one group,
 * since that's the only "same turn" boundary the data model currently
 * exposes. Splitting a single message's tools into multiple groups based on
 * prose interleaved between calls would need backend turn-boundary data that
 * doesn't exist yet — deliberately out of scope here, not an oversight.
 */
export const ToolGroup = ({ calls, onApprove, onDeny, className, ...props }: ToolGroupProps) => {
  const counts = new Map<string, number>();
  for (const call of calls) {
    counts.set(call.name, (counts.get(call.name) ?? 0) + 1);
  }
  const nameSummary = Array.from(counts.entries())
    .map(([name, count]) => `${name} ×${count}`)
    .join(", ");

  const durations = calls.map((call) => call.durationMs).filter((ms): ms is number => ms !== undefined);
  const totalDurationMs = durations.length > 0 ? durations.reduce((sum, ms) => sum + ms, 0) : undefined;

  return (
    <Collapsible className={cn("not-prose mb-1 w-full", className)} {...props}>
      <CollapsibleTrigger className="group flex w-full min-w-0 items-center gap-1.5 rounded-[7px] px-[7px] py-[3px] -ml-[7px] text-left leading-[24px] transition-colors hover:bg-muted/60">
        <Layers2Icon className="size-[13px] shrink-0 text-muted-foreground" />
        <span className="shrink-0 text-[12.5px] font-medium text-foreground">
          Ran {calls.length} tools
        </span>
        <span className="min-w-0 flex-1 truncate font-mono text-[11px] text-muted-foreground">
          {nameSummary}
        </span>
        {totalDurationMs !== undefined && (
          <span className="shrink-0 font-mono text-[11px] text-muted-foreground">
            {formatDuration(totalDurationMs)}
          </span>
        )}
        <ChevronRightIcon className="ml-1 size-[13px] shrink-0 text-muted-foreground transition-transform group-data-[state=open]:rotate-90" />
      </CollapsibleTrigger>
      <CollapsibleContent className="mt-0.5 space-y-0.5 border-line/60 border-l pl-3 outline-none data-[state=closed]:fade-out-0 data-[state=closed]:slide-out-to-top-2 data-[state=open]:slide-in-from-top-2 data-[state=closed]:animate-out data-[state=open]:animate-in">
        {calls.map((call, index) => {
          const isApprovalNeeded = call.state === "approval-requested";
          const summary = isApprovalNeeded
            ? "needs approval"
            : call.errorText
              ? call.errorText.length > 80
                ? `${call.errorText.slice(0, 80)}…`
                : call.errorText
              : call.output !== undefined
                ? summarizeToolPayload(call.output)
                : summarizeToolPayload(call.input);

          return (
            <div key={index} className="flex min-w-0 items-center gap-2 py-[2px] leading-[18px]">
              <span className="w-4 shrink-0 text-right font-mono text-[10px] text-muted-foreground">
                {index + 1}
              </span>
              {isApprovalNeeded ? (
                <ShieldAlertIcon className="size-[11px] shrink-0 text-warning" />
              ) : (
                <span className={cn("size-[5px] shrink-0 rounded-full", STATUS_DOT_CLASSES[call.state])} />
              )}
              <span className="max-w-[40%] shrink-0 truncate font-mono text-[12px] text-foreground">
                {call.name}
              </span>
              <span
                className={cn(
                  "min-w-0 flex-1 truncate font-mono text-[11px]",
                  isApprovalNeeded ? "text-warning" : call.errorText ? "text-destructive" : "text-muted-foreground"
                )}
              >
                {summary}
              </span>
              {isApprovalNeeded ? (
                <ApprovalActions
                  onApprove={call.callId ? () => onApprove?.(call.callId!) : undefined}
                  onDeny={call.callId ? () => onDeny?.(call.callId!) : undefined}
                />
              ) : (
                call.durationMs !== undefined && (
                  <span className="shrink-0 font-mono text-[11px] text-muted-foreground">
                    {formatDuration(call.durationMs)}
                  </span>
                )
              )}
            </div>
          );
        })}
      </CollapsibleContent>
    </Collapsible>
  );
};
