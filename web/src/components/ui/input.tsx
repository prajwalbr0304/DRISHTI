import * as React from "react";
import { cn } from "@/lib/utils";

export const Input = React.forwardRef<HTMLInputElement, React.InputHTMLAttributes<HTMLInputElement>>(
  ({ className, type, ...props }, ref) => (
    <input
      type={type}
      ref={ref}
      className={cn(
        "flex h-9 w-full rounded-control border border-hairline bg-surface-2 px-3 py-1 text-14 text-content shadow-sm transition-colors",
        "placeholder:text-content-dim focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary/60",
        "disabled:cursor-not-allowed disabled:opacity-50",
        className,
      )}
      {...props}
    />
  ),
);
Input.displayName = "Input";
