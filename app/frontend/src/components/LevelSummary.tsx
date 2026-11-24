import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { desiredLabel, explanationWithoutHigher, higherNotice, levelLabel, unassessedItems } from '@/lib/levelView';
import type { AssessedLevel, LevelPool } from '@/types';

function CriterionList({ title, items, empty }: { title: string; items: LevelPool[]; empty: string }) {
  return (
    <details className="rounded-lg border border-line px-3 py-2 text-sm">
      <summary className="min-h-8 cursor-pointer py-1 font-medium text-ink hover:text-primary-strong focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-ring">
        {title} <span className="tabular-nums text-ink-muted">({items.length})</span>
      </summary>
      {items.length === 0 ? (
        <p className="mt-1 text-ink-muted">{empty}</p>
      ) : (
        <ul className="mt-1 flex list-disc flex-col gap-1 pl-5 text-ink-muted">
          {items.map((c) => <li key={c.id} className="[overflow-wrap:anywhere]">{c.title || c.id}</li>)}
        </ul>
      )}
    </details>
  );
}

/**
 * Desired level (the candidate's own statement) next to the level supported by the graded answers. The level is an
 * assessment of the supplied answers under the level policy, not verified work history and not a chance of being hired.
 * Compact card for the side column; the criterion lists are collapsed into one "Деталі рівня" block.
 */
export function LevelSummary({ level, profileTarget }: { level: AssessedLevel | null | undefined; profileTarget: string | null }) {
  const desired = desiredLabel(level ? level.desired_level : profileTarget);
  const unknown = !level || level.assessed_level === 'UNKNOWN';
  const checked = level ? level.confirmed_strengths.length + level.critical_gaps.length : 0;
  const total = level ? checked + unassessedItems(level).length : 0;
  return (
    <Card className="min-w-0">
      <CardHeader>
        <CardTitle id="level-title">Ваш рівень</CardTitle>
        <CardDescription>
          Висновок спирається лише на оцінки ваших відповідей і не впливає на порядок вакансій.
        </CardDescription>
      </CardHeader>
      <CardContent className="flex flex-col gap-3">
        <dl className="grid grid-cols-2 gap-2">
          <div className="rounded-xl bg-surface-muted p-3">
            <dt className="text-xs text-ink-subtle">Бажаний</dt>
            <dd className="text-lg font-semibold text-ink">{desired}</dd>
          </div>
          <div className="rounded-xl bg-primary-soft p-3">
            <dt className="text-xs text-ink-subtle">Підтверджений</dt>
            <dd className="text-lg font-semibold text-primary">
              {level && !unknown ? levelLabel(level.assessed_level) : 'Не визначено'}
            </dd>
          </div>
        </dl>
        {unknown && (
          <p className="text-sm text-ink-muted">
            {level && total > 0
              ? `Підтверджено ${level.confirmed_strengths.length} із ${total} критичних вимог. `
              : 'Рівень не вдалося визначити за збереженими оцінками. '}
            Щоб рівень можна було визначити, відповідайте в співбесіді розгорнутіше й із прикладами.
          </p>
        )}
        {level && (() => {
          const notice = higherNotice(level);
          if (!notice) return null;
          if (notice.kind === 'blocked') {
            return (
              <p role="alert" className="rounded-xl border border-danger bg-danger-soft p-3 text-sm font-medium text-ink">
                {notice.text}
              </p>
            );
          }
          return (
            <div className="rounded-xl border border-line p-3" role="note" aria-labelledby="level-higher-title">
              <p id="level-higher-title" className="text-xs text-ink-subtle">Найвищий рівень із доказами</p>
              <p className="text-lg font-semibold text-ink">{levelLabel(notice.level)}</p>
              <p className="mt-1 text-sm text-ink-muted">{notice.text}</p>
            </div>
          );
        })()}
        {level && (
          <details className="rounded-lg border border-line px-3 py-2 text-sm">
            <summary className="min-h-8 cursor-pointer py-1 font-medium text-ink hover:text-primary-strong focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-ring">
              Деталі рівня
            </summary>
            <div className="mt-2 flex flex-col gap-2">
              {explanationWithoutHigher(level).length > 0 && (
                <ul className="flex flex-col gap-1 text-ink-muted">
                  {explanationWithoutHigher(level).map((line, i) => <li key={i}>{line}</li>)}
                </ul>
              )}
              <CriterionList title="Підтверджено" items={level.confirmed_strengths} empty="Підтверджених критичних критеріїв поки немає." />
              <CriterionList title="Прогалини" items={level.critical_gaps} empty="Критичних прогалин не виявлено." />
              <CriterionList title="Не перевірено" items={unassessedItems(level)} empty="Усі критичні вимоги перевірено." />
              {!!level.unresolved_pools?.length && (
                <CriterionList title="Межові відповіді: не зараховано ні як підтвердження, ні як прогалину"
                  items={level.unresolved_pools} empty="" />
              )}
              {!!level.no_experience_pools?.length && (
                <CriterionList title="Без досвіду з інструментом: альтернативу не перевіряли"
                  items={level.no_experience_pools} empty="" />
              )}
            </div>
          </details>
        )}
        {level && (
          <p className="text-xs text-ink-muted">
            <span aria-hidden="true">ⓘ </span>Правила визначення рівня — робоче припущення, ще не перевірене експертами.
          </p>
        )}
      </CardContent>
    </Card>
  );
}
