import type { ReactNode } from 'react';
import { LogOut } from 'lucide-react';
import { initials } from '@/lib/bands';

export function AppShell({ title, name, onLogout, right, children }: {
  title: string;
  name: string;
  onLogout: () => void;
  right?: ReactNode;
  children: ReactNode;
}) {
  return (
    <div className="min-h-screen bg-gradient-to-b from-slate-50 to-blue-50/40">
      <header className="border-b border-slate-200 bg-white/90 backdrop-blur">
        <div className="mx-auto flex max-w-6xl items-center justify-between gap-4 px-4 py-3">
          <h1 className="text-xl font-bold tracking-tight text-slate-900">{title}</h1>
          <div className="flex items-center gap-4">
            {right}
            <div className="flex items-center gap-2">
              <span
                className="flex size-9 items-center justify-center rounded-full bg-blue-100 text-sm font-semibold text-blue-700"
                aria-hidden="true"
              >
                {initials(name)}
              </span>
              <button
                onClick={onLogout}
                aria-label="Вийти"
                className="flex items-center gap-1 rounded-md px-2 py-1 text-sm text-slate-600 hover:bg-slate-100 focus-visible:outline-2 focus-visible:outline-blue-600"
              >
                <LogOut className="size-4" aria-hidden="true" />
                <span className="hidden sm:inline" aria-hidden="true">Вийти</span>
              </button>
            </div>
          </div>
        </div>
      </header>
      <main className="mx-auto max-w-6xl p-4">{children}</main>
    </div>
  );
}
