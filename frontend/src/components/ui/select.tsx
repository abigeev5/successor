import { forwardRef, type SelectHTMLAttributes, type TextareaHTMLAttributes } from "react";

import { cn } from "@/lib/cn";

import { fieldClass, type FieldOptions } from "./input";

export function Select({
  fit,
  compact,
  className,
  ...props
}: SelectHTMLAttributes<HTMLSelectElement> & FieldOptions) {
  return <select className={cn(fieldClass({ fit, compact }), className)} {...props} />;
}

export const Textarea = forwardRef<
  HTMLTextAreaElement,
  TextareaHTMLAttributes<HTMLTextAreaElement>
>(function Textarea({ className, ...props }, ref) {
  return <textarea ref={ref} className={cn(fieldClass(), "resize-y", className)} {...props} />;
});
