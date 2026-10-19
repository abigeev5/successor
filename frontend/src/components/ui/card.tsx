import type { HTMLAttributes } from "react";

import { cn } from "@/lib/cn";

const PADDING = { sm: "p-4", md: "p-6" };

export function Card({
  padding = "md",
  className,
  ...props
}: HTMLAttributes<HTMLDivElement> & { padding?: keyof typeof PADDING }) {
  return (
    <div
      className={cn("rounded-[var(--radius-card)] bg-surface", PADDING[padding], className)}
      {...props}
    />
  );
}
