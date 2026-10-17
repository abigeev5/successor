import { Play } from "lucide-react";
import { useState } from "react";

import type { Source } from "@/api/client";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { timecode } from "@/lib/labels";

/** A step of a screen recording: the video opens at the step's start (SPEC 7.7, 13.3). */
function RecordingClip({ videoId, startMs }: { videoId: string; startMs: number }) {
  const [open, setOpen] = useState(false);
  if (!open) {
    return (
      <Button variant="secondary" className="px-3 py-1 text-xs" onClick={() => setOpen(true)}>
        <Play className="size-3.5" aria-hidden /> Смотреть с {timecode(startMs)}
      </Button>
    );
  }
  return (
    <video
      src={`/api/assets/${videoId}#t=${startMs / 1000}`}
      controls
      autoPlay
      preload="metadata"
      className="w-full rounded-md bg-black"
    />
  );
}

/** The quote highlighted inside its source (SPEC 7.7); successors see the quote only. */
export function SourceView({ source }: { source: Source }) {
  const context = source.context ?? "";
  const at = context.indexOf(source.quote);
  const videoId = source.link?.video_asset_id;
  return (
    <Card className="space-y-2 p-3 text-sm">
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
      {videoId && <RecordingClip videoId={videoId} startMs={source.start_ms ?? 0} />}
    </Card>
  );
}
