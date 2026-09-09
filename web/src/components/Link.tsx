import type { ReactNode } from "react";
import { navigate } from "../router";

export function Link({
  to,
  className,
  children,
  "aria-label": ariaLabel,
}: {
  to: string;
  className?: string;
  children: ReactNode;
  "aria-label"?: string;
}) {
  return (
    <a
      href={to}
      className={className}
      aria-label={ariaLabel}
      onClick={(event) => {
        event.preventDefault();
        navigate(to);
      }}
    >
      {children}
    </a>
  );
}
