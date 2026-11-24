import { CheckCircle2, CircleDashed, MapPin, Briefcase, Layers, Monitor, Target, UserRound, type LucideIcon } from 'lucide-react';
import { Card } from '@/components/ui/card';
import { Progress } from '@/components/ui/progress';
import { profileSummary } from '@/lib/profileSummary';
import type { ProfileForm } from '@/lib/profiles';

const ICON: Record<string, LucideIcon> = {
  track: Layers, target_level: Target, years: Briefcase, work_mode: Monitor, location: MapPin, desired_title: UserRound,
};

/** «Поточний профіль»: the form as typed, how much of it is filled, and whether the interview can start. */
export function ProfileSummaryCard({ form, status, dirty, hasOpenAttempt }: {
  form: ProfileForm; status: string; dirty: boolean; hasOpenAttempt: boolean;
}) {
  const { rows, percent, ready } = profileSummary(form);
  return (
    <Card className="p-4 sm:p-5" role="region" aria-labelledby="profile-summary-title">
      <div>
        <h2 id="profile-summary-title" className="flex items-center gap-2 text-lg font-semibold text-ink">
          <UserRound className="size-5 text-primary" aria-hidden="true" />Поточний профіль
        </h2>
        <div className="mt-3 flex flex-col gap-1.5">
          <div className="flex items-center justify-between text-sm text-ink-muted">
            <span>Заповненість профілю</span>
            <span className="font-semibold tabular-nums text-ink">{percent}%</span>
          </div>
          <Progress value={percent} label="Заповненість профілю" />
        </div>
        <dl className="mt-4 flex flex-col gap-3 border-t border-line pt-4">
          {rows.map((r) => {
            const Icon = ICON[r.key] ?? Layers;
            return (
              <div key={r.key} className="flex items-start gap-3">
                <Icon className="mt-0.5 size-4 shrink-0 text-ink-subtle" aria-hidden="true" />
                <div className="min-w-0">
                  <dt className="text-xs font-semibold text-ink">{r.label}{r.required && <span className="text-danger" aria-hidden="true"> *</span>}</dt>
                  <dd className={`text-sm [overflow-wrap:anywhere] ${r.value ? 'text-ink-muted' : 'text-ink-subtle'}`}>
                    {r.value ?? 'Не вказано'}{!r.value && r.required && <span className="sr-only"> (обов’язково)</span>}
                  </dd>
                </div>
              </div>
            );
          })}
        </dl>
        <div role="status" className={`mt-4 flex items-start gap-3 rounded-xl p-3 ${ready && !dirty ? 'bg-success-soft text-success-ink' : 'bg-warning-soft text-warning-ink'}`}>
          {ready && !dirty ? <CheckCircle2 className="mt-0.5 size-5 shrink-0" aria-hidden="true" /> : <CircleDashed className="mt-0.5 size-5 shrink-0" aria-hidden="true" />}
          <div className="text-sm">
            <p className="font-semibold">
              {dirty ? 'Є незбережені зміни' : ready ? 'Профіль готовий' : 'Профіль майже готовий'}
            </p>
            <p>
              {dirty ? 'Збережіть їх, щоб почати співбесіду.'
                : !ready ? 'Заповніть напрям, рівень і роки досвіду, щоб перейти до співбесіди.'
                  : hasOpenAttempt ? 'Співбесіда розпочата, її можна продовжити.' : 'Можна переходити до співбесіди.'}
            </p>
            <p className="mt-1 text-xs opacity-90">{status}</p>
          </div>
        </div>
      </div>
    </Card>
  );
}
