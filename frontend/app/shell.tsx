"use client";

import { NavBar } from "@/lib/components/shared";
import { useSyncExternalStore } from "react";

function noopSubscribe() {
  return () => {};
}

function useClientMounted() {
  return useSyncExternalStore(noopSubscribe, () => true, () => false);
}

export function Shell({ children }: { children: React.ReactNode }) {
  const mounted = useClientMounted();
  if (!mounted) {
    return <AppLoadingShell />;
  }
  return (
    <main className="min-h-screen bg-neutral-100 text-neutral-950">
      <a href="#main-content" className="sr-only focus:not-sr-only focus:absolute focus:left-2 focus:top-2 focus:z-50 focus:rounded focus:bg-white focus:px-4 focus:py-2 focus:text-sm focus:font-semibold focus:text-neutral-950">
        Skip to main content
      </a>
      <div className="grid min-h-screen grid-cols-1 md:grid-cols-[236px_1fr]">
        <NavBar />
        <section id="main-content" className="min-w-0">
          {children}
        </section>
      </div>
    </main>
  );
}

function AppLoadingShell() {
  return (
    <main className="min-h-screen bg-neutral-100 text-neutral-950">
      <div className="grid min-h-screen grid-cols-1 md:grid-cols-[236px_1fr]">
        <aside className="border-b border-neutral-200 bg-white md:border-b-0 md:border-r">
          <div className="border-b border-neutral-200 p-4">
            <h1 className="text-lg font-semibold tracking-normal">Agentic PWAD QA Doom</h1>
          </div>
          <nav className="grid grid-cols-3 gap-1 p-3 md:grid-cols-1">
            <div className="h-10 rounded bg-neutral-950" />
            <div className="h-10 rounded bg-neutral-100" />
            <div className="h-10 rounded bg-neutral-100" />
            <div className="h-10 rounded bg-neutral-100" />
          </nav>
        </aside>
        <section className="space-y-4 p-4 lg:p-6">
          <div className="h-8 w-40 rounded bg-neutral-200" />
          <div className="space-y-2">
            {[0, 1, 2].map((item) => (
              <div key={item} className="h-20 animate-pulse rounded border border-neutral-200 bg-white" />
            ))}
          </div>
        </section>
      </div>
    </main>
  );
}
