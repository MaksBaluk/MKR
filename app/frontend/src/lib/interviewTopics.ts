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

/** True when text would reveal an LLM score or level to the candidate during the interview. */
export function containsScoreLeak(text: string): boolean {
  return /\d[.,]\d|\d\s*%|оцінен|оцінк\S*\s*[:—-]?\s*\d|рівень|рівня|високий|середній|низький/i.test(text);
}

export const INTERVIEW_PANEL_STRINGS: readonly string[] = [
  'Про розмову',
  'Теми розмови',
  'Кожна тема — від 1 до 5 запитань.',
  'поточна',
  'Поточна тема',
  'Кілька запитань, щоб краще зрозуміти ваш досвід',
  'Поради для відповіді',
  'Наведіть конкретний приклад із власної практики.',
  'Розкажіть, що саме робили ви самі, а не вся команда.',
  'Назвіть інструменти та результат вашої роботи.',
  'Автоматична оцінка зараз вимкнена: відповіді збережуться, але підсумок буде неповним.',
  'Призупинити',
  'Завершити і переглянути результати',
];
