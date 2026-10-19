import { useState } from "react";
import Markdown from "react-markdown";
import { useNavigate, useParams } from "react-router-dom";

import { useAcceptConsent, useConsentText } from "@/api/handovers";
import { ErrorNote } from "@/components/ErrorNote";
import { FullPageSpinner } from "@/components/Spinner";
import { Button } from "@/components/ui/button";

export function ConsentPage() {
  const { handoverId = "" } = useParams();
  const text = useConsentText();
  const accept = useAcceptConsent(handoverId);
  const navigate = useNavigate();
  const [read, setRead] = useState(false);

  if (text.isPending) return <FullPageSpinner />;
  if (text.isError) return <ErrorNote error={text.error} />;

  return (
    <section className="mx-auto max-w-2xl space-y-6">
      <div className="space-y-3 rounded-[var(--radius-card)] bg-surface p-6 sm:p-10 [&_blockquote]:rounded-xl [&_blockquote]:bg-white [&_blockquote]:px-4 [&_blockquote]:py-2 [&_blockquote]:text-xs [&_blockquote]:text-ink-muted [&_h1]:mb-5 [&_h1]:text-[28px] [&_h1]:leading-tight [&_h1]:font-semibold [&_h1]:tracking-tight [&_p]:text-sm [&_p]:leading-relaxed [&_strong]:text-ink [&_ul]:list-disc [&_ul]:pl-5 [&_ul]:text-sm">
        <p className="eyebrow">Согласие · версия {text.data.version}</p>
        <Markdown>{text.data.text}</Markdown>
      </div>
      <label className="flex items-start gap-3 text-sm">
        <input
          type="checkbox"
          className="mt-0.5 size-4 accent-primary"
          checked={read}
          onChange={(e) => setRead(e.target.checked)}
        />
        Я прочитал(а) и согласен(на) на запись и обработку рабочих бесед на этих условиях.
      </label>
      <ErrorNote error={accept.error} />
      <div className="flex gap-2">
        <Button
          disabled={!read || accept.isPending}
          onClick={() =>
            accept.mutate(undefined, { onSuccess: () => navigate(`/handovers/${handoverId}`) })
          }
        >
          Принять согласие
        </Button>
        <Button variant="ghost" onClick={() => navigate(-1)}>
          Назад
        </Button>
      </div>
    </section>
  );
}
