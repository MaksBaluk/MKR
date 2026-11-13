import { BrowserRouter } from 'react-router-dom';
import { AppRoutes } from '@/routes';
import { SessionProvider } from '@/session';

export default function App() {
  return (
    <BrowserRouter>
      <SessionProvider>
        <AppRoutes />
      </SessionProvider>
    </BrowserRouter>
  );
}
