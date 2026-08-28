import * as React from "react";
import { Slot } from "@radix-ui/react-slot";
import { cva, type VariantProps } from "class-variance-authority";
import { cn } from "@/lib/utils";

const buttonVariants = cva(
  // AWS console buttons are pills with bold labels (Cloudscape fontWeightButton).
  "inline-flex items-center justify-center gap-2 whitespace-nowrap rounded-full text-13 font-bold transition-colors duration-150 focus-visible:outline-none disabled:pointer-events-none disabled:opacity-50 [&_svg]:pointer-events-none [&_svg]:size-4 [&_svg]:shrink-0",
  {
    variants: {
      variant: {
        primary: "bg-primary text-primary-fg hover:bg-primary/90",
        secondary: "bg-surface-2 text-content hover:bg-surface-2/70",
        outline: "border border-hairline bg-transparent text-content hover:bg-surface-2",
        ghost: "text-content-dim hover:bg-surface-2 hover:text-content",
        danger: "bg-severity-critical text-white hover:bg-severity-critical/90",
        link: "text-primary underline-offset-4 hover:underline",
      },
      size: {
        sm: "h-7 px-2.5",
        md: "h-9 px-3.5",
        lg: "h-10 px-5 text-14",
        icon: "h-9 w-9",
        "icon-sm": "h-7 w-7",
      },
    },
    defaultVariants: { variant: "primary", size: "md" },
  },
);

export interface ButtonProps
  extends React.ButtonHTMLAttributes<HTMLButtonElement>,
    VariantProps<typeof buttonVariants> {
  asChild?: boolean;
}

export const Button = React.forwardRef<HTMLButtonElement, ButtonProps>(
  ({ className, variant, size, asChild = false, ...props }, ref) => {
    const Comp = asChild ? Slot : "button";
    return (
      <Comp className={cn(buttonVariants({ variant, size }), className)} ref={ref} {...props} />
    );
  },
);
Button.displayName = "Button";

export { buttonVariants };
