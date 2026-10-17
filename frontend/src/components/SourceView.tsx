import type { Source } from "@/api/client";
import { Card } from "@/components/ui/card";

/** The quote highlighted inside the expert's full answer (SPEC 7.7); successors see the quote only. */
export function SourceView({ source }: { source: Source }) {
  const context = source.context ?? "";
  const at = context.indexOf(source.quote);
  return (
    <Card className="space-y-1 p-3 text-sm">
      <p className="text-xs text-ink-muted">{source.label}</p>
      {at >= 0 ? (
        <p className="whitespace-pre-line">
          {context.slice(0, at)}
          <mark className="rounded bg-primary-light px-0.5">{source.quote}</mark>
          {context.slice(at + source.quote.length)}
        </p>
      ) : (
        <blockquote className="border-l-2 border-primary pl-2">«{source.quote}»</blockquote>
      )}
    </Card>
  );
}
