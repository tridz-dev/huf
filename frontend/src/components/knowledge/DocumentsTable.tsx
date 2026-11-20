import { useMemo, useState } from "react";
import {
  FileText,
  Globe,
  Loader2,
  MoreHorizontal,
  RefreshCw,
  Search,
  Trash2,
  Type,
  Cloud,
  ExternalLink,
} from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { formatTimeAgo } from "@/utils/time";
import type { KnowledgeInputDoc } from "@/types/knowledge.types";
import { DocumentDetailSheet } from "./DocumentDetailSheet";
import { filterInputs, type DocFilter } from "./import/docFilter";
import { ConfirmActionDialog } from "./import/ConfirmActionDialog";
import {
  displayFileLabel,
  itemReason,
  itemStatusLabel,
} from "./import/ingestionLabels";

/** Title shown for an input: its title, else file name, URL or the first 60 characters of text. */
export function inputTitle(input: KnowledgeInputDoc): string {
  if (input.title?.trim()) return input.title.trim();
  if (input.input_type === "URL") return input.url || "Web page";
  if (input.input_type === "Text")
    return input.text?.trim().slice(0, 60) || "Text";
  return (
    displayFileLabel(input.file_name, input.external_key) ||
    input.file ||
    "Untitled file"
  );
}

/** Where the content came from, in plain words. */
export function inputOrigin(input: KnowledgeInputDoc): {
  label: string;
  icon: typeof FileText;
} {
  if (input.input_type === "URL")
    return { label: input.url || "Web page", icon: Globe };
  if (input.input_type === "Text") return { label: "Typed text", icon: Type };
  const key = input.external_key || "";
  if (key.startsWith("s3://"))
    return { label: key.replace(/#[0-9a-f]{40}$/, ""), icon: Cloud };
  return { label: "Uploaded file", icon: FileText };
}

const STATUS_VARIANT: Record<
  string,
  "pill-success" | "pill-info" | "pill-danger" | "pill-neutral"
> = {
  Indexed: "pill-success",
  Pending: "pill-info",
  Processing: "pill-info",
  Error: "pill-danger",
  Skipped: "pill-neutral",
};

interface DocumentsTableProps {
  inputs: KnowledgeInputDoc[];
  loading: boolean;
  filter?: DocFilter | null;
  onReprocess: (name: string) => Promise<void> | void;
  onRemove: (name: string) => Promise<void> | void;
}

export function DocumentsTable({
  inputs,
  loading,
  filter = null,
  onReprocess,
  onRemove,
}: DocumentsTableProps) {
  const [query, setQuery] = useState("");
  const [removeTarget, setRemoveTarget] = useState<string | null>(null);
  const [openName, setOpenName] = useState<string | null>(null);
  const rows = useMemo(() => {
    const q = query.trim().toLowerCase();
    const base = filterInputs(inputs, filter);
    if (!q) return base;
    return base.filter((i) =>
      `${inputTitle(i)} ${inputOrigin(i).label}`.toLowerCase().includes(q),
    );
  }, [inputs, query, filter]);

  if (loading && inputs.length === 0) {
    return (
      <div className="flex justify-center py-8">
        <Loader2 className="h-5 w-5 animate-spin text-steel-soft" />
      </div>
    );
  }
  if (inputs.length === 0) return null;

  return (
    <div className="space-y-3" data-testid="documents-table">
      <div className="relative max-w-sm">
        <Search className="pointer-events-none absolute left-2.5 top-2.5 h-4 w-4 text-steel-soft" />
        <Input
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          placeholder="Search documents"
          className="pl-8"
          aria-label="Search documents"
        />
      </div>
      <div className="rounded-md border">
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>Title</TableHead>
              <TableHead>Origin</TableHead>
              <TableHead>Status</TableHead>
              <TableHead>Added</TableHead>
              <TableHead className="w-10" />
            </TableRow>
          </TableHeader>
          <TableBody>
            {rows.length === 0 && (
              <TableRow>
                <TableCell
                  colSpan={5}
                  className="py-6 text-center text-sm text-steel"
                >
                  No documents match your search.
                </TableCell>
              </TableRow>
            )}
            {rows.map((input) => {
              const origin = inputOrigin(input);
              const Icon = origin.icon;
              const busy =
                input.status === "Pending" || input.status === "Processing";
              const problem =
                input.status === "Error" || input.status === "Skipped";
              return (
                <TableRow key={input.name}>
                  <TableCell className="max-w-[18rem]">
                    <p className="truncate font-medium">{inputTitle(input)}</p>
                    {problem && (
                      <p className="truncate text-xs text-steel-soft">
                        {itemReason(input)}
                      </p>
                    )}
                  </TableCell>
                  <TableCell className="max-w-[14rem]">
                    <span className="flex items-center gap-1.5 text-sm text-steel">
                      <Icon className="h-3.5 w-3.5 shrink-0" />
                      <span className="truncate">{origin.label}</span>
                    </span>
                  </TableCell>
                  <TableCell>
                    <Badge
                      variant={STATUS_VARIANT[input.status] ?? "pill-neutral"}
                    >
                      {itemStatusLabel(input.status)}
                    </Badge>
                  </TableCell>
                  <TableCell className="whitespace-nowrap text-sm text-steel">
                    {formatTimeAgo(input.creation)}
                  </TableCell>
                  <TableCell>
                    <DropdownMenu>
                      <DropdownMenuTrigger asChild>
                        <Button
                          type="button"
                          variant="ghost"
                          size="icon-sm"
                          aria-label="Document actions"
                        >
                          <MoreHorizontal className="h-4 w-4" />
                        </Button>
                      </DropdownMenuTrigger>
                      <DropdownMenuContent align="end">
                        <DropdownMenuItem
                          onSelect={() => setOpenName(input.name)}
                        >
                          <ExternalLink className="mr-2 h-4 w-4" />
                          Open
                        </DropdownMenuItem>
                        <DropdownMenuItem
                          disabled={busy}
                          onSelect={() => void onReprocess(input.name)}
                        >
                          <RefreshCw className="mr-2 h-4 w-4" />
                          Reprocess
                        </DropdownMenuItem>
                        <DropdownMenuItem
                          className="text-destructive"
                          onSelect={() => setRemoveTarget(input.name)}
                        >
                          <Trash2 className="mr-2 h-4 w-4" />
                          Remove
                        </DropdownMenuItem>
                      </DropdownMenuContent>
                    </DropdownMenu>
                  </TableCell>
                </TableRow>
              );
            })}
          </TableBody>
        </Table>
      </div>
      <DocumentDetailSheet
        input={inputs.find((i) => i.name === openName) ?? null}
        onOpenChange={(o) => !o && setOpenName(null)}
      />
      <ConfirmActionDialog
        open={removeTarget !== null}
        onOpenChange={(o) => !o && setRemoveTarget(null)}
        title="Remove this document?"
        description="It is removed from this source and agents can no longer use it. This cannot be undone."
        confirmLabel="Remove"
        destructive
        onConfirm={async () => {
          const target = removeTarget;
          setRemoveTarget(null);
          if (target) await onRemove(target);
        }}
      />
    </div>
  );
}
