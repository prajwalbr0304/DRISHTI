import * as React from "react";
import { ChevronDown } from "lucide-react";
import { cn } from "@/lib/utils";

export interface SelectOption {
  value: string;
  label: string;
}

/** Lightweight native <select> styled with Calm Authority tokens. */
export function NativeSelect({
  value,
  onChange,
  options,
  placeholder = "Any",
  className,
  "aria-label": ariaLabel,
}: {
  value: string;
  onChange: (v: string) => void;
  options: SelectOption[];
  placeholder?: string;
  className?: string;
  "aria-label"?: string;
}) {
  return (
    <div className={cn("relative", className)}>
      <select
        value={value}
        aria-label={ariaLabel}
        onChange={(e) => onChange(e.target.value)}
        className={cn(
          "h-8 w-full appearance-none rounded-control border border-hairline bg-surface-2 pl-2.5 pr-7 text-13 text-content",
          "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary/60",
          value ? "text-content" : "text-content-dim",
        )}
      >
        <option value="">{placeholder}</option>
        {options.map((o) => (
          <option key={o.value} value={o.value} className="bg-surface text-content">
            {o.label}
          </option>
        ))}
      </select>
      <ChevronDown className="pointer-events-none absolute right-2 top-1/2 size-3.5 -translate-y-1/2 text-content-dim" />
    </div>
  );
}
