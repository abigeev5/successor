import { forwardRef, type SelectHTMLAttributes, type TextareaHTMLAttributes } from "react";

import { cn } from "@/lib/cn";

const FIELD =
  "w-full rounded-md border border-black/15 bg-white px-3 py-2 text-sm text-ink focus:border-primary focus:outline-none focus:ring-2 focus:ring-primary-light";

export function Select({ className, ...props }: SelectHTMLAttributes<HTMLSelectElement>) {
  return <select className={cn(FIELD, className)} {...props} />;
}

export const Textarea = forwardRef<
  HTMLTextAreaElement,
  TextareaHTMLAttributes<HTMLTextAreaElement>
>(function Textarea({ className, ...props }, ref) {
  return <textarea ref={ref} className={cn(FIELD, "resize-y", className)} {...props} />;
});
