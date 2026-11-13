import { Button } from '@/components/ui/button';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { ArrowRight, LogOut, ListChecks } from 'lucide-react';

export function WelcomeScreen({ onContinue, onLogout }: { onContinue: () => void; onLogout: () => void }) {
  return (
    <main className="mx-auto flex min-h-screen max-w-xl flex-col justify-center gap-4 p-4">
      <Card>
        <CardHeader>
          <CardTitle>Ласкаво просимо</CardTitle>
        </CardHeader>
        <CardContent className="flex flex-col gap-4 text-slate-700">
          <p>
            Ми підберемо вакансії з каталогу та проведемо коротку розмову про ваш досвід. Відповідайте своїми словами: немає
            правильних чи неправильних тестів.
          </p>
          <p className="flex items-start gap-2 text-sm">
            <ListChecks className="mt-0.5 size-4 shrink-0 text-blue-700" aria-hidden="true" />
            Оцінки з розмови — лише оцінка ваших відповідей, а не підтверджений досвід роботи.
          </p>
          <Button onClick={onContinue} className="self-start">
            Почати
            <ArrowRight className="size-4" aria-hidden="true" />
          </Button>
        </CardContent>
      </Card>
      <Button variant="ghost" onClick={onLogout} className="self-start">
        <LogOut className="size-4" aria-hidden="true" />
        Вийти
      </Button>
    </main>
  );
}
