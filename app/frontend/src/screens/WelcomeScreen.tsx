import { useState } from 'react';
import { Link } from 'react-router-dom';
import { ArrowRight, BarChart3, Briefcase, Building2, Check, GraduationCap, Info, Play } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Card } from '@/components/ui/card';
import { Dialog } from '@/components/ui/dialog';
import { STEPS } from '@/lib/navigation';
import { useProfileInterview } from '@/hooks/useProfileInterview';

const STEP_TEXT: Record<string, string> = {
  welcome: 'Знайомство із системою та правилами оцінювання.',
  profile: 'Трек, бажана посада й за бажанням самооцінка. За треком система сама добирає вакансії.',
  interview: 'Розмова до 10 тем: відповідайте своїми словами, без варіантів на вибір.',
  results: 'Вакансії, упорядковані за вашими відповідями, оцінки розмови та ваша самооцінка.',
  vacancies: 'Вимоги й навички вакансій із добірки.',
  market: 'Які професійні дії найчастіше трапляються в добірці.',
};

/**
 * Decorative, static illustration (aria-hidden). The percentages are illustrative sample values of
 * profile fit («збіг профілю»), not data and not a hiring probability.
 */
function HeroIllustration() {
  return (
    <div aria-hidden="true" className="relative mx-auto hidden h-[22rem] w-full max-w-md select-none xl:block">
      <div className="absolute top-4 right-0 size-72 rounded-full bg-primary-soft blur-2xl" />
      <div className="absolute bottom-0 left-4 size-64 rounded-full bg-accent-soft blur-2xl" />
      <div className="absolute top-0 right-6 flex gap-1.5">
        <span className="h-4 w-1 rotate-[30deg] rounded-full bg-accent" />
        <span className="mt-2 h-4 w-1 rotate-[60deg] rounded-full bg-accent" />
      </div>

      <div className="absolute top-6 right-0 w-72 -rotate-2 rounded-2xl border border-line bg-surface p-4 shadow-float">
        <p className="flex items-center gap-2 text-sm font-semibold text-ink">
          <span className="flex size-8 items-center justify-center rounded-lg bg-primary-soft text-primary"><Briefcase className="size-4" /></span>
          Вакансії
        </p>
        {[96, 89].map((pct) => (
          <div key={pct} className="mt-3 flex items-center gap-3 rounded-xl border border-line p-2.5">
            <span className="flex size-8 items-center justify-center rounded-lg bg-canvas text-ink-subtle"><Building2 className="size-4" /></span>
            <span className="flex flex-1 flex-col gap-1.5">
              <span className="h-2 w-4/5 rounded-full bg-line-strong" />
              <span className="h-2 w-1/2 rounded-full bg-line" />
            </span>
            <span className="shrink-0 rounded-full bg-accent-soft px-2 py-0.5 text-[11px] font-semibold text-accent-ink">Збіг профілю: {pct}%</span>
          </div>
        ))}
      </div>

      <div className="absolute top-36 left-0 w-60 rotate-1 rounded-2xl border border-line bg-surface p-4 shadow-float">
        <p className="flex items-center gap-2 text-sm font-semibold text-ink">
          <span className="flex size-8 items-center justify-center rounded-lg bg-accent-soft text-accent-ink"><GraduationCap className="size-4" /></span>
          Компетентності
        </p>
        {['w-5/6', 'w-2/3', 'w-3/4'].map((w) => (
          <div key={w} className="mt-3 flex flex-col gap-1.5">
            <span className="h-1.5 w-1/2 rounded-full bg-line" />
            <span className="h-2 rounded-full bg-primary-soft"><span className={`block h-2 rounded-full bg-primary ${w}`} /></span>
          </div>
        ))}
      </div>

      <div className="absolute right-2 bottom-0 w-60 -rotate-1 rounded-2xl border border-line bg-surface p-4 shadow-float">
        <p className="flex items-center gap-2 text-sm font-semibold text-ink">
          <span className="flex size-8 items-center justify-center rounded-lg bg-primary-soft text-primary"><BarChart3 className="size-4" /></span>
          Рейтинг
        </p>
        <div className="mt-3 flex items-center gap-4">
          <svg viewBox="0 0 64 64" className="size-16 shrink-0">
            <circle cx="32" cy="32" r="26" fill="none" strokeWidth="7" className="stroke-accent-soft" />
            <circle cx="32" cy="32" r="26" fill="none" strokeWidth="7" strokeLinecap="round" strokeDasharray="150 164"
              transform="rotate(-90 32 32)" className="stroke-accent" />
            <text x="32" y="33" textAnchor="middle" className="fill-ink text-[13px] font-bold">92%</text>
            <text x="32" y="44" textAnchor="middle" className="fill-ink-muted text-[8px]">збіг</text>
          </svg>
          <ul className="flex flex-col gap-1.5 text-xs text-ink-muted">
            {['Оцінки розмови', 'Релевантні вакансії', 'Напрями розвитку'].map((t) => (
              <li key={t} className="flex items-center gap-1.5"><Check className="size-3.5 text-accent" strokeWidth={3} />{t}</li>
            ))}
          </ul>
        </div>
      </div>
    </div>
  );
}

/** Step 1 (route `/`). The primary action follows the candidate's stage. */
export function WelcomeScreen() {
  const interview = useProfileInterview();
  const [howOpen, setHowOpen] = useState(false);

  const cta =
    interview?.status === 'active' ? { to: `/interview/${interview.id}`, label: 'Продовжити співбесіду', icon: ArrowRight }
    : interview?.status === 'finished' ? { to: '/results', label: 'Переглянути результати', icon: ArrowRight }
    : { to: '/profile', label: 'Розпочати оцінювання', icon: Play };

  return (
    <Card className="relative overflow-hidden rounded-3xl">
      <div aria-hidden="true" className="pointer-events-none absolute -right-24 -bottom-24 size-[28rem] rounded-full bg-gradient-to-tr from-accent-soft/70 to-primary-soft/70 blur-3xl" />
      <div className="relative grid items-center gap-10 p-6 sm:p-10 lg:p-12 xl:grid-cols-[minmax(0,1fr)_minmax(0,1fr)]">
        <div>
          <h2 className="text-3xl leading-tight font-extrabold tracking-tight text-ink sm:text-4xl xl:text-[2.75rem]">
            Ласкаво просимо до CompetenceMatch
          </h2>
          <span aria-hidden="true" className="mt-5 block h-1.5 w-14 rounded-full bg-accent" />
          <p className="mt-5 max-w-xl text-base leading-relaxed text-ink-muted sm:text-lg">
            Система проведе коротку співбесіду про ваш професійний досвід, оцінить відповіді та впорядкує вакансії з
            каталогу за тим, які їхні вимоги ваші відповіді підтвердили.
          </p>
          {interview && (
            <p className="mt-3 text-sm font-medium text-primary-strong">
              {interview.status === 'active' ? 'У вас є незавершена співбесіда.' : 'Співбесіду завершено, результати готові.'}
            </p>
          )}
          <div className="mt-8 flex flex-col gap-3 sm:flex-row">
            <Button asChild size="lg">
              <Link to={cta.to}><cta.icon className="size-5" aria-hidden="true" />{cta.label}</Link>
            </Button>
            <Button variant="outline" size="lg" onClick={() => setHowOpen(true)}>
              <Info className="size-5" aria-hidden="true" />
              Як це працює
            </Button>
          </div>
        </div>
        <HeroIllustration />
      </div>

      <Dialog open={howOpen} onClose={() => setHowOpen(false)} title="Як це працює">
        <ol className="flex flex-col gap-3">
          {STEPS.map((s) => (
            <li key={s.key} className="flex gap-3">
              <span className="flex size-7 shrink-0 items-center justify-center rounded-full bg-primary-soft text-xs font-semibold text-primary-strong">{s.n}</span>
              <span className="text-sm">
                <span className="font-semibold text-ink">{s.label}.</span>{' '}
                <span className="text-ink-muted">{STEP_TEXT[s.key]}</span>
              </span>
            </li>
          ))}
        </ol>
        <div className="mt-5 rounded-xl bg-canvas p-4 text-sm text-ink-muted">
          <p className="font-semibold text-ink">Важливо знати</p>
          <ul className="mt-2 list-disc space-y-1 pl-5">
            <li>Оцінки розмови описують ваші відповіді, а не перевірений досвід роботи.</li>
            <li>Система не обчислює ймовірність працевлаштування.</li>
            <li>Змінювати можна лише власну самооцінку.</li>
          </ul>
        </div>
      </Dialog>
    </Card>
  );
}
