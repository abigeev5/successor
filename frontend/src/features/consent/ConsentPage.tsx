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
    <section className="mx-auto max-w-2xl space-y-4">
      <div className="prose-sm space-y-3 rounded-lg bg-white [&_h1]:text-xl [&_h1]:font-semibold [&_p]:text-sm [&_ul]:list-disc [&_ul]:pl-5 [&_ul]:text-sm [&_blockquote]:text-xs [&_blockquote]:text-ink-muted">
        <Markdown>{text.data.text}</Markdown>
      </div>
      <p className="text-xs text-ink-muted">Версия текста: {text.data.version}</p>
      <label className="flex items-start gap-2 text-sm">
        <input type="checkbox" checked={read} onChange={(e) => setRead(e.target.checked)} />Я
        прочитал(а) и согласен(на) на запись и обработку рабочих бесед на этих условиях.
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
