"use client";

import { Slot } from "@radix-ui/react-slot";
import { cva, type VariantProps } from "class-variance-authority";
import * as React from "react";

import { cn } from "@/lib/utils";

const buttonVariants = cva(
  "inline-flex items-center justify-center gap-2 whitespace-nowrap rounded-md font-mono text-xs uppercase tracking-wider transition-colors disabled:pointer-events-none disabled:opacity-40",
  {
    variants: {
      variant: {
        default:
          "border border-signal-idle/40 bg-signal-idle/10 text-signal-idle hover:bg-signal-idle/20",
        outline:
          "border border-hairline-bright bg-transparent text-chalk-muted hover:border-chalk-faint hover:text-chalk",
        ghost: "text-chalk-muted hover:bg-hairline/60 hover:text-chalk",
        danger:
          "border border-signal-block/40 bg-signal-block/10 text-signal-block hover:bg-signal-block/20",
        approve:
          "border border-signal-allow/40 bg-signal-allow/10 text-signal-allow hover:bg-signal-allow/20",
      },
      size: {
        default: "h-9 px-4",
        sm: "h-7 px-3 text-[10px]",
        lg: "h-11 px-6 text-sm",
        icon: "h-9 w-9",
      },
    },
    defaultVariants: { variant: "default", size: "default" },
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
