import { useState } from 'react';
import { Check, Monitor, Moon, Sun, type LucideIcon } from 'lucide-react';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { applyTheme, getStoredTheme, storeTheme, type ThemeChoice } from '@/lib/theme';
import { cn } from '@/lib/utils';

const OPTIONS: { value: ThemeChoice; label: string; icon: LucideIcon }[] = [
  { value: 'light', label: 'Світла', icon: Sun },
  { value: 'dark', label: 'Темна', icon: Moon },
  { value: 'system', label: 'Системна', icon: Monitor },
];

/** Settings: only the colour theme for now. The choice applies immediately and is remembered on this device. */
export function SettingsScreen() {
  const [choice, setChoice] = useState<ThemeChoice>(getStoredTheme);
  const [notice, setNotice] = useState('');

  function pick(value: ThemeChoice) {
    setChoice(value);
    storeTheme(value);
    applyTheme(value);
    setNotice(`Тему змінено: ${OPTIONS.find((o) => o.value === value)?.label.toLowerCase()}`);
  }

  return (
    <Card className="max-w-2xl">
      <CardHeader>
        <CardTitle>Тема</CardTitle>
        <CardDescription>Системна збігається з налаштуванням вашого пристрою.</CardDescription>
      </CardHeader>
      <CardContent className="flex flex-col gap-3">
        <div role="radiogroup" aria-label="Тема" className="grid gap-3 sm:grid-cols-3">
          {OPTIONS.map((o) => {
            const on = choice === o.value;
            return (
              <button key={o.value} type="button" role="radio" aria-checked={on} onClick={() => pick(o.value)}
                className={cn('flex min-h-14 cursor-pointer items-center gap-3 rounded-xl border px-4 text-left text-sm font-medium',
                  'focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-ring',
                  on ? 'border-primary bg-primary-soft text-primary-strong' : 'border-line bg-surface text-ink hover:bg-surface-muted')}>
                <o.icon className="size-5 shrink-0" aria-hidden="true" />
                <span className="flex-1">{o.label}</span>
                {on && <Check className="size-4 shrink-0" aria-hidden="true" />}
              </button>
            );
          })}
        </div>
        <p role="status" aria-live="polite" className="text-sm text-ink-muted">{notice}</p>
      </CardContent>
    </Card>
  );
}
