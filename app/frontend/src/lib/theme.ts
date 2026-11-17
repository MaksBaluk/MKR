/** Theme choice: light, dark or follow the device. Stored in localStorage (best effort) and applied to <html>. */
export type ThemeChoice = 'light' | 'dark' | 'system';

const KEY = 'cm-theme';

export function normalizeTheme(raw: string | null): ThemeChoice {
  return raw === 'light' || raw === 'dark' ? raw : 'system';
}

export function resolveTheme(choice: ThemeChoice, systemDark: boolean): 'light' | 'dark' {
  return choice === 'system' ? (systemDark ? 'dark' : 'light') : choice;
}

export function getStoredTheme(): ThemeChoice {
  try {
    return normalizeTheme(localStorage.getItem(KEY));
  } catch {
    return 'system';
  }
}

export function storeTheme(choice: ThemeChoice): void {
  try {
    localStorage.setItem(KEY, choice);
  } catch {
    // private mode or blocked storage: the choice still applies for this page view
  }
}

const dark = () => window.matchMedia?.('(prefers-color-scheme: dark)').matches ?? false;

export function applyTheme(choice: ThemeChoice): void {
  const theme = resolveTheme(choice, dark());
  const root = document.documentElement;
  root.dataset.theme = theme;
  root.style.colorScheme = theme;
  document.querySelector('meta[name="theme-color"]')?.setAttribute('content', theme === 'dark' ? '#0b1220' : '#f5f7fb');
}

/** Apply the stored choice at startup and follow device changes while the choice is «system». */
export function initTheme(): void {
  applyTheme(getStoredTheme());
  window.matchMedia?.('(prefers-color-scheme: dark)').addEventListener?.('change', () => {
    if (getStoredTheme() === 'system') applyTheme('system');
  });
}
