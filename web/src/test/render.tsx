/* eslint-disable react-refresh/only-export-components -- test-only facade re-exports Testing Library utilities. */
import type { ReactNode } from "react";
import {
  render as testingLibraryRender,
  type RenderOptions,
} from "@testing-library/react/pure";
import { LanguageProvider } from "@/providers/LanguageProvider";

export * from "@testing-library/react/pure";

type DefaultRenderOptions = Omit<RenderOptions, "queries">;

/**
 * Application-aware render used by component tests. Production routes always
 * run beneath LanguageProvider; mirror that invariant while preserving any
 * wrapper supplied by an individual test.
 */
export function render(ui: ReactNode, options: DefaultRenderOptions = {}) {
  const { wrapper: CallerWrapper, ...renderOptions } = options;

  function TestProviders({ children }: { children: ReactNode }) {
    return (
      <LanguageProvider>
        {CallerWrapper ? <CallerWrapper>{children}</CallerWrapper> : children}
      </LanguageProvider>
    );
  }

  return testingLibraryRender(ui, {
    ...renderOptions,
    wrapper: TestProviders,
  });
}
