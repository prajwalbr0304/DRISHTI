import * as React from "react";
import { cva, type VariantProps } from "class-variance-authority";
import { cn } from "@/lib/utils";

const badgeVariants = cva(
  "inline-flex items-center gap-1 rounded-full border px-2 py-0.5 text-12 font-medium leading-none transition-colors",
  {
    variants: {
      variant: {
        neutral: "border-hairline bg-surface-2 text-content-dim",
        primary: "border-transparent bg-primary/15 text-primary",
        accent: "border-transparent bg-accent/15 text-accent",
        outline: "border-hairline text-content",
        critical: "border-transparent bg-severity-critical/15 text-severity-critical",
        high: "border-transparent bg-severity-high/15 text-severity-high",
        medium: "border-transparent bg-severity-medium/15 text-severity-medium",
        low: "border-transparent bg-severity-low/15 text-severity-low",
      },
    },
    defaultVariants: { variant: "neutral" },
  },
);

export interface BadgeProps
  extends React.HTMLAttributes<HTMLSpanElement>,
    VariantProps<typeof badgeVariants> {}

export function Badge({ className, variant, ...props }: BadgeProps) {
  return <span className={cn(badgeVariants({ variant }), className)} {...props} />;
}

export { badgeVariants };
