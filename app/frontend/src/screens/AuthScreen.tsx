import { useState, type FormEvent } from 'react';
import { LogIn, Play, Target } from 'lucide-react';
import { uk } from '../i18n/uk';
import { Card, ErrorAlert } from '../components/ui';

export type AuthSubmit = (mode: 'login' | 'register', data: { email: string; password: string; name: string }) => Promise<void>;

export function AuthScreen({ busy, error, demoMode, onSubmit, onDemo, onDismissError }: {
  busy: boolean; error: string; demoMode: boolean; onSubmit: AuthSubmit; onDemo: () => void; onDismissError: () => void;
}) {
  const [mode, setMode] = useState<'login' | 'register'>('login');
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [name, setName] = useState('');

  function handle(e: FormEvent) {
    e.preventDefault();
    void onSubmit(mode, { email, password, name });
  }

  return (
    <div className="auth-shell">
      <div className="auth-brand"><div className="brand-logo"><Target size={27} aria-hidden="true" /></div><span>Competence<span>Match</span></span></div>
      <div className="auth-layout">
        <div className="auth-story">
          <h1>Знайдіть вакансії, що відповідають вашим навичкам</h1>
          <p>{uk.auth.intro}</p>
        </div>
        <Card className="auth-panel">
          <h2>{mode === 'login' ? uk.auth.loginTitle : uk.auth.registerTitle}</h2>
          <form onSubmit={handle} noValidate={false}>
            {mode === 'register' && (
              <div className="field">
                <label htmlFor="auth-name">{uk.auth.name}</label>
                <input id="auth-name" autoComplete="name" required minLength={2} value={name} onChange={e => setName(e.target.value)} />
              </div>
            )}
            <div className="field">
              <label htmlFor="auth-email">{uk.auth.email}</label>
              <input id="auth-email" type="email" autoComplete="email" required value={email} onChange={e => setEmail(e.target.value)} />
            </div>
            <div className="field">
              <label htmlFor="auth-password">{uk.auth.password}</label>
              <input id="auth-password" type="password" autoComplete={mode === 'login' ? 'current-password' : 'new-password'}
                required minLength={mode === 'register' ? 10 : undefined} value={password} onChange={e => setPassword(e.target.value)} />
            </div>
            <button disabled={busy} className="btn primary stretch" type="submit">
              <LogIn size={17} aria-hidden="true" />{mode === 'login' ? uk.auth.login : uk.auth.register}
            </button>
          </form>
          <button className="text-link" type="button" onClick={() => setMode(mode === 'login' ? 'register' : 'login')}>
            {mode === 'login' ? uk.auth.toRegister : uk.auth.toLogin}
          </button>
          {demoMode && (
            <div className="demo-access">
              <p className="muted">{uk.auth.demoHint}</p>
              <button className="btn ghost stretch" type="button" onClick={onDemo} disabled={busy}><Play size={16} aria-hidden="true" />{uk.auth.demo}</button>
            </div>
          )}
          {error && <ErrorAlert message={error} onDismiss={onDismissError} />}
        </Card>
      </div>
      <footer className="auth-footer">{uk.auth.footer}</footer>
    </div>
  );
}
