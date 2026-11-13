import { useId, useRef, useState, type ChangeEvent, type FormEvent } from 'react';
import { api, setToken, ApiError } from '@/api';
import { Logo } from '@/components/AppShell';
import { Alert } from '@/components/ui/alert';
import { Button } from '@/components/ui/button';
import { Card } from '@/components/ui/card';
import { Field, describedBy } from '@/components/ui/field';
import { Input } from '@/components/ui/input';
import { MIN_PASSWORD, validateAuth, type AuthErrors, type AuthFields, type AuthMode } from '@/lib/validation';
import { BarChart3, Eye, EyeOff, Loader2, LogIn, MessageSquareText, ShieldCheck, UserPlus } from 'lucide-react';

const FEATURES = [
  { icon: MessageSquareText, title: 'Розмова замість тестів', text: 'Відповідайте своїми словами, без варіантів на вибір.' },
  { icon: BarChart3, title: 'Пояснюване ранжування', text: 'Видно, які вимоги вакансій підтвердили ваші відповіді.' },
  { icon: ShieldCheck, title: 'Ваші дані під контролем', text: 'Самооцінку змінюєте лише ви; оцінки розмови не є перевіреним досвідом.' },
];

export function AuthScreen({ onSignedIn, notice = null }: { onSignedIn: () => void; notice?: string | null }) {
  const [mode, setMode] = useState<AuthMode>('login');
  const [fields, setFields] = useState<AuthFields>({ email: '', name: '', password: '' });
  const [touched, setTouched] = useState<Partial<Record<keyof AuthFields, boolean>>>({});
  const [submitted, setSubmitted] = useState(false);
  const [showPassword, setShowPassword] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const formRef = useRef<HTMLFormElement>(null);
  const ids = { email: useId(), name: useId(), password: useId() };

  const errors: AuthErrors = validateAuth(mode, fields);
  const visible = (k: keyof AuthFields) => ((submitted || touched[k]) ? errors[k] ?? null : null);
  const set = (k: keyof AuthFields) => (e: ChangeEvent<HTMLInputElement>) => setFields((f) => ({ ...f, [k]: e.target.value }));
  const blur = (k: keyof AuthFields) => () => setTouched((t) => ({ ...t, [k]: true }));

  async function submit(e: FormEvent) {
    e.preventDefault();
    setSubmitted(true);
    setError(null);
    if (Object.keys(errors).length) {
      formRef.current?.querySelector<HTMLInputElement>('[aria-invalid="true"]')?.focus();
      return;
    }
    setBusy(true);
    try {
      const email = fields.email.trim();
      const body =
        mode === 'login'
          ? await api<{ token: string }>('/auth/login', { method: 'POST', json: { email, password: fields.password } })
          : await api<{ token: string }>('/auth/register', {
              method: 'POST',
              json: { email, display_name: fields.name.trim(), password: fields.password },
            });
      setToken(body.token);
      onSignedIn();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Не вдалося увійти. Спробуйте ще раз.');
    } finally {
      setBusy(false);
    }
  }

  function switchMode() {
    setMode(mode === 'login' ? 'register' : 'login');
    setError(null);
    setSubmitted(false);
    setTouched({});
  }

  const passwordHint = mode === 'register' ? `Щонайменше ${MIN_PASSWORD} символів.` : undefined;

  return (
    <div className="grid min-h-dvh lg:grid-cols-[minmax(0,1fr)_minmax(0,1fr)]">
      <aside className="relative hidden overflow-hidden bg-gradient-to-br from-primary-strong to-brand-deep p-12 text-white lg:flex lg:flex-col lg:justify-between">
        <div aria-hidden="true" className="pointer-events-none absolute -top-24 -right-24 size-96 rounded-full bg-white/10 blur-3xl" />
        <div aria-hidden="true" className="pointer-events-none absolute -bottom-32 -left-16 size-96 rounded-full bg-sky-300/20 blur-3xl" />
        <Logo inverted />
        <div className="relative max-w-md">
          <p className="text-4xl leading-tight font-bold tracking-tight">Покажіть, що ви вмієте, — ми підберемо вакансії.</p>
          <p className="mt-4 text-lg text-blue-100">Коротка адаптивна співбесіда допомагає зрозуміти ваші професійні дії та порівняти їх із вимогами вакансій.</p>
          <ul className="mt-10 flex flex-col gap-5">
            {FEATURES.map((f) => (
              <li key={f.title} className="flex gap-4">
                <span className="flex size-11 shrink-0 items-center justify-center rounded-xl bg-white/15 ring-1 ring-white/20">
                  <f.icon className="size-5" aria-hidden="true" />
                </span>
                <span>
                  <span className="block font-semibold">{f.title}</span>
                  <span className="block text-sm text-blue-100">{f.text}</span>
                </span>
              </li>
            ))}
          </ul>
        </div>
      </aside>

      <main id="main-content" tabIndex={-1} className="flex items-center justify-center px-4 py-10 sm:px-6">
        <div className="w-full max-w-md">
          <div className="mb-8 flex justify-center lg:hidden"><Logo /></div>
          <Card className="p-6 shadow-raised sm:p-8">
            <h1 className="text-2xl font-bold tracking-tight text-ink">{mode === 'login' ? 'Вхід до акаунта' : 'Створення акаунта'}</h1>
            <p className="mt-1.5 text-sm text-ink-muted">
              {mode === 'login' ? 'Раді бачити вас знову. Увійдіть, щоб продовжити.' : 'Кілька полів — і можна починати оцінювання.'}
            </p>
            {notice && <Alert variant="info" className="mt-5">{notice}</Alert>}
            <form ref={formRef} className="mt-6 flex flex-col gap-4" onSubmit={submit} noValidate>
              {mode === 'register' && (
                <Field id={ids.name} label="Ім’я" error={visible('name')}>
                  <Input id={ids.name} value={fields.name} onChange={set('name')} onBlur={blur('name')} autoComplete="name" required
                    aria-invalid={!!visible('name')} aria-describedby={describedBy(ids.name, undefined, visible('name'))} />
                </Field>
              )}
              <Field id={ids.email} label="Електронна пошта" error={visible('email')}>
                <Input id={ids.email} type="email" inputMode="email" value={fields.email} onChange={set('email')} onBlur={blur('email')}
                  autoComplete="email" required placeholder="name@example.com"
                  aria-invalid={!!visible('email')} aria-describedby={describedBy(ids.email, undefined, visible('email'))} />
              </Field>
              <Field id={ids.password} label="Пароль" hint={passwordHint} error={visible('password')}>
                <div className="relative">
                  <Input id={ids.password} type={showPassword ? 'text' : 'password'} value={fields.password} onChange={set('password')}
                    onBlur={blur('password')} autoComplete={mode === 'login' ? 'current-password' : 'new-password'} required className="pr-12"
                    aria-invalid={!!visible('password')} aria-describedby={describedBy(ids.password, passwordHint, visible('password'))} />
                  <button type="button" onClick={() => setShowPassword((v) => !v)} aria-pressed={showPassword}
                    aria-label={showPassword ? 'Приховати пароль' : 'Показати пароль'} aria-controls={ids.password}
                    className="absolute top-0 right-0 flex size-11 cursor-pointer items-center justify-center rounded-xl text-ink-subtle hover:text-ink focus-visible:outline-2 focus-visible:outline-ring">
                    {showPassword ? <EyeOff className="size-5" aria-hidden="true" /> : <Eye className="size-5" aria-hidden="true" />}
                  </button>
                </div>
              </Field>
              {error && <Alert role="alert" variant="danger">{error}</Alert>}
              <Button type="submit" size="lg" disabled={busy} className="mt-1 w-full">
                {busy ? <Loader2 className="size-4 animate-spin motion-reduce:animate-none" aria-hidden="true" />
                  : mode === 'login' ? <LogIn className="size-4" aria-hidden="true" /> : <UserPlus className="size-4" aria-hidden="true" />}
                {busy ? 'Зачекайте…' : mode === 'login' ? 'Увійти' : 'Створити акаунт'}
              </Button>
            </form>
            <p className="mt-6 text-center text-sm text-ink-muted">
              {mode === 'login' ? 'Немає акаунта?' : 'Уже маєте акаунт?'}{' '}
              <button type="button" onClick={switchMode}
                className="inline-flex min-h-11 cursor-pointer items-center rounded-md font-semibold text-primary-strong underline-offset-4 hover:underline focus-visible:outline-2 focus-visible:outline-ring">
                {mode === 'login' ? 'Зареєструватися' : 'Увійти'}
              </button>
            </p>
          </Card>
        </div>
      </main>
    </div>
  );
}
