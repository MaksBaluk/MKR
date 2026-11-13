import { useId, useState, type FormEvent } from 'react';
import { api, setToken, ApiError } from '@/api';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Alert } from '@/components/ui/alert';
import { LogIn, UserPlus } from 'lucide-react';

export function AuthScreen({ onSignedIn }: { onSignedIn: () => void }) {
  const [mode, setMode] = useState<'login' | 'register'>('login');
  const [email, setEmail] = useState('');
  const [name, setName] = useState('');
  const [password, setPassword] = useState('');
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const ids = { email: useId(), name: useId(), password: useId() };

  async function submit(e: FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      const body =
        mode === 'login'
          ? await api<{ token: string }>('/auth/login', { method: 'POST', json: { email, password } })
          : await api<{ token: string }>('/auth/register', {
              method: 'POST',
              json: { email, display_name: name, password },
            });
      setToken(body.token);
      onSignedIn();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Не вдалося увійти. Спробуйте ще раз.');
    } finally {
      setBusy(false);
    }
  }

  return (
    <main className="mx-auto flex min-h-screen max-w-md flex-col justify-center p-4">
      <Card>
        <CardHeader>
          <CardTitle>{mode === 'login' ? 'Вхід' : 'Створення акаунта'}</CardTitle>
        </CardHeader>
        <CardContent>
          <form className="flex flex-col gap-4" onSubmit={submit} noValidate>
            {mode === 'register' && (
              <div className="flex flex-col gap-1">
                <Label htmlFor={ids.name}>Ім’я</Label>
                <Input id={ids.name} value={name} onChange={(e) => setName(e.target.value)} autoComplete="name" required minLength={2} />
              </div>
            )}
            <div className="flex flex-col gap-1">
              <Label htmlFor={ids.email}>Електронна пошта</Label>
              <Input id={ids.email} type="email" value={email} onChange={(e) => setEmail(e.target.value)} autoComplete="email" required />
            </div>
            <div className="flex flex-col gap-1">
              <Label htmlFor={ids.password}>Пароль</Label>
              <Input
                id={ids.password}
                type="password"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                autoComplete={mode === 'login' ? 'current-password' : 'new-password'}
                required
                minLength={10}
              />
              {mode === 'register' && <p className="text-xs text-slate-500">Щонайменше 10 символів.</p>}
            </div>
            {error && <Alert role="alert">{error}</Alert>}
            <Button type="submit" disabled={busy}>
              {mode === 'login' ? <LogIn className="size-4" aria-hidden="true" /> : <UserPlus className="size-4" aria-hidden="true" />}
              {busy ? 'Зачекайте…' : mode === 'login' ? 'Увійти' : 'Створити акаунт'}
            </Button>
            <button
              type="button"
              className="text-sm text-blue-700 underline underline-offset-2"
              onClick={() => {
                setMode(mode === 'login' ? 'register' : 'login');
                setError(null);
              }}
            >
              {mode === 'login' ? 'Немає акаунта? Зареєструватися' : 'Уже маєте акаунт? Увійти'}
            </button>
          </form>
        </CardContent>
      </Card>
    </main>
  );
}
