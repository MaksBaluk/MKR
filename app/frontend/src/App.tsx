import { BrowserRouter } from 'react-router-dom';
import { ErrorBoundary } from '@/components/ErrorBoundary';
import { AppRoutes } from '@/routes';
import { SessionProvider } from '@/session';

export default function App() {
  return (
    <BrowserRouter>
      <SessionProvider>
        <ErrorBoundary>
          <AppRoutes />
        </ErrorBoundary>
      </SessionProvider>
    </BrowserRouter>
  );
}
