import type { ReactNode } from "react";

import { BrandHomeLink } from "../_components/brand-home-link";
import { Providers } from "../_components/providers";

export default function WorkflowLayout({ children }: { children: ReactNode }) {
  return (
    <Providers>
      <BrandHomeLink />
      {children}
    </Providers>
  );
}
