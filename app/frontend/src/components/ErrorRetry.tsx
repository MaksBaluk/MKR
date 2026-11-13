import { RefreshCw } from 'lucide-react';
import { Alert } from '@/components/ui/alert';
import { Button } from '@/components/ui/button';

/** Error message with a retry action next to it. */
export function ErrorRetry({ message, onRetry }: { message: string | null; onRetry: () => void }) {
  return (
    <Alert role="alert" variant="danger">
      <div className="flex flex-col items-start gap-3">
        <span>{message ?? 'Сталася помилка. Спробуйте ще раз.'}</span>
        <Button variant="outline" size="sm" onClick={onRetry}>
          <RefreshCw className="size-4" aria-hidden="true" />Спробувати ще раз
        </Button>
      </div>
    </Alert>
  );
}
