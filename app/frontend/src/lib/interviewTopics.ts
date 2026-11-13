import type { TurnView } from '@/types';

export const MAX_TOPICS = 10;

export interface TopicItem {
  action_id: string;
  action_name: string;
  answeredCount: number;
  isCurrent: boolean;
}

/** Distinct topics in first-seen order; a re-asked topic is one entry with a higher answeredCount. */
export function deriveTopics(turns: TurnView[]): TopicItem[] {
  const byId = new Map<string, TopicItem>();
  for (const t of turns) {
    let item = byId.get(t.action_id);
    if (!item) {
      item = { action_id: t.action_id, action_name: t.action_name, answeredCount: 0, isCurrent: false };
      byId.set(t.action_id, item);
    }
    if (t.answer_text !== null) item.answeredCount += 1;
    else item.isCurrent = true;
  }
  return [...byId.values()];
}

/** True when text would reveal an LLM score or level to the candidate during the interview.
 * "оцінка" alone is allowed ("Автоматична оцінка зараз вимкнена"); it leaks only with a value.
 * Known over-match: any decimal such as "1.5" is flagged (safe side). */
export function containsScoreLeak(text: string): boolean {
  return /\d\s*\/\s*\d|\d[.,]\d|\d\s*%|оцінен|оцінк\S*\s*[:—-]?\s*(\d|висок|низьк|середн)|рівен|рівн|level|висок|низьк|середн/i.test(text);
}

export const topicsCountLabel = (used: number, max: number = MAX_TOPICS): string => `${used} з ${max} тем`;

export const PANEL_TEXT = {
  disclosure: 'Про розмову',
  topicsTitle: 'Теми розмови',
  topicsNote: 'Кожна тема — від 1 до 5 запитань.',
  topicsEmpty: 'Теми з’являться, щойно почнеться розмова.',
  currentMarker: 'поточна',
  currentTopic: 'Поточна тема',
  currentTopicLine: 'Кілька запитань, щоб краще зрозуміти ваш досвід',
  tipsTitle: 'Поради для відповіді',
  tips: [
    'Наведіть конкретний приклад із власної практики.',
    'Розкажіть, що саме робили ви самі, а не вся команда.',
    'Назвіть інструменти та результат вашої роботи.',
  ],
  llmOff: 'Автоматична оцінка зараз вимкнена: відповіді збережуться, але підсумок буде неповним.',
  pause: 'Призупинити',
  finish: 'Завершити і переглянути результати',
} as const;

/** Every static string the panel renders (plus the count label for 0..MAX_TOPICS). */
export function allPanelStrings(): string[] {
  const { tips, ...rest } = PANEL_TEXT;
  const counts = Array.from({ length: MAX_TOPICS + 1 }, (_, i) => topicsCountLabel(i));
  return [...Object.values(rest), ...tips, ...counts];
}
