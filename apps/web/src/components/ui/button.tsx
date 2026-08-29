"use client";

import { Slot } from "@radix-ui/react-slot";
import { cva, type VariantProps } from "class-variance-authority";
import * as React from "react";

import { cn } from "@/lib/utils";

const buttonVariants = cva(
  "inline-flex items-center justify-center gap-2 whitespace-nowrap rounded-control font-medium transition-colors disabled:pointer-events-none disabled:opacity-45",
  {
    variants: {
      variant: {
        primary: "bg-accent text-white hover:bg-accent-hover",
        secondary:
          "border border-line-strong bg-surface text-ink hover:border-ink-muted hover:bg-surface-sunken",
        ghost: "text-ink-secondary hover:bg-surface-sunken hover:text-ink",
        // Verdict colours are reserved, so a destructive control borrows the
        // block colour only when the action itself revokes or denies.
        destructive: "border border-block-line bg-block-tint text-block hover:bg-block/10",
        approve: "border border-allow-line bg-allow-tint text-allow hover:bg-allow/10",
      },
      size: {
        sm: "h-8 px-3 text-caption",
        md: "h-9 px-4 text-body",
        lg: "h-10 px-5 text-body",
        icon: "h-9 w-9",
      },
    },
    defaultVariants: { variant: "secondary", size: "md" },
  },
);

export interface ButtonProps
  extends React.ButtonHTMLAttributes<HTMLButtonElement>,
    VariantProps<typeof buttonVariants> {
  asChild?: boolean;
}

const Button = React.forwardRef<HTMLButtonElement, ButtonProps>(
  ({ className, variant, size, asChild = false, ...props }, ref) => {
    const Comp = asChild ? Slot : "button";
    return (
      <Comp className={cn(buttonVariants({ variant, size, className }))} ref={ref} {...props} />
    );
  },
);
Button.displayName = "Button";

export { Button, buttonVariants };
