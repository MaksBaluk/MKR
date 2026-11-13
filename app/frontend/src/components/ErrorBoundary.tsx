import { Component, type ErrorInfo, type ReactNode } from 'react';
import { RefreshCw, TriangleAlert } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Card } from '@/components/ui/card';
import { isChunkLoadError } from '@/lib/errors';

interface Props {
  children: ReactNode;
  /** When this value changes (e.g. the route), a shown fallback resets and the children render again. */
  resetKey?: string;
}

/** Catches render errors and failed lazy chunks so the user sees a fallback instead of a blank page. */
export class ErrorBoundary extends Component<Props, { error: unknown }> {
  state: { error: unknown } = { error: null };

  static getDerivedStateFromError(error: unknown) {
    return { error };
  }

  componentDidCatch(error: unknown, _info: ErrorInfo) {
    // Only the error type: messages and component stacks may contain user data.
    console.error('UI error:', error instanceof Error ? error.name : typeof error);
  }

  componentDidUpdate(prev: Props) {
    if (this.state.error !== null && prev.resetKey !== this.props.resetKey) this.setState({ error: null });
  }

  render() {
    if (this.state.error === null) return this.props.children;
    const chunk = isChunkLoadError(this.state.error);
    return (
      <Card role="alert" className="flex flex-col items-start gap-3 p-6">
        <span className="flex size-12 items-center justify-center rounded-2xl bg-danger-soft text-danger-ink">
          <TriangleAlert className="size-6" aria-hidden="true" />
        </span>
        <h2 className="text-lg font-semibold tracking-tight text-ink">Щось пішло не так</h2>
        <p className="max-w-prose text-sm text-ink-muted">
          {chunk
            ? 'Не вдалося завантажити частину застосунку. Перевірте з’єднання з мережею й оновіть сторінку.'
            : 'Цю частину сторінки не вдалося показати. Спробуйте ще раз або оновіть сторінку. Ваші дані збережено на сервері.'}
        </p>
        <div className="flex flex-wrap gap-2">
          {!chunk && (
            <Button onClick={() => this.setState({ error: null })}>Спробувати ще раз</Button>
          )}
          <Button variant={chunk ? 'default' : 'outline'} onClick={() => window.location.reload()}>
            <RefreshCw className="size-4" aria-hidden="true" />Оновити сторінку
          </Button>
        </div>
      </Card>
    );
  }
}
