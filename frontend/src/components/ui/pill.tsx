import type { HTMLAttributes } from "react";

import { cn } from "@/lib/cn";

type Tone = "blue" | "white";

const TONES: Record<Tone, string> = {
  blue: "bg-primary-light text-primary-dark",
  white: "bg-white text-ink-muted",
};

export function Pill({
  tone = "blue",
  className,
  ...props
}: HTMLAttributes<HTMLSpanElement> & { tone?: Tone }) {
  return (
    <span
      className={cn(
        "inline-flex items-center gap-1 rounded-full px-2.5 py-0.5 text-xs font-medium",
        TONES[tone],
        className,
      )}
      {...props}
    />
  );
}
