const BASE = import.meta.env.VITE_API_BASE_URL || '/api/v1';
const TOKEN_KEY = 'cm_token';

export function token(): string | null {
  try { return localStorage.getItem(TOKEN_KEY); } catch { return null; }
}

export function setToken(value: string | null) {
  try {
    if (value) localStorage.setItem(TOKEN_KEY, value);
    else localStorage.removeItem(TOKEN_KEY);
  } catch { /* storage unavailable: the session lives only in memory */ }
}

/** Backend detail strings that users may see, mapped to Ukrainian. Anything unknown gets a generic message. */
const knownDetails: Record<string, string> = {
  'Snapshot track differs from candidate profile track': 'Трек набору не збігається з треком вашого профілю. Оновіть рекомендації.',
  'Snapshot not found': 'Набір вакансій не знайдено.',
  'Interview not found': 'Інтервю не знайдено.',
  'Turn not found': 'Питання не знайдено.',
  'Match run not found': 'Результат не знайдено.',
  'Evidence not found': 'Доказ не знайдено.',
  'Interview is not paused': 'Інтервю не на паузі.',
  'Interview is not ready for a new question': 'Інтервю зараз не готове до нового питання.',
  'A question is already outstanding': 'Питання вже очікує відповіді.',
  'No matching outstanding question': 'Це питання вже неактуальне. Оновлюю інтервю.',
  'Open-ended question requires answer_text only': 'Для відкритого питання потрібна текстова відповідь.',
  'Choose a valid option ID': 'Оберіть варіант зі списку.',
  'Provide an option or answer_text': 'Напишіть відповідь.',
  'Interview completed; review before finishing': 'Інтервю завершено. Перегляд можливий лише до завершення.',
  'Interview completed; grading is no longer possible': 'Інтервю завершено. Оцінка більше недоступна.',
  'Evidence already reviewed': 'Пропозицію вже розглянуто.',
  'LLM provider not enabled; configure .env first': 'Допоміжний LLM-сервіс не налаштовано. Оцінка за рубрикою недоступна.',
  'Немає вакансій за цими умовами': 'За цими умовами вакансій немає. Змініть фільтри.',
  'Unknown track': 'Невідомий трек.',
  'Invalid credentials': 'Невірна пошта або пароль.',
  'Email already registered': 'Ця пошта вже зареєстрована. Спробуйте увійти.',
};

export class ApiError extends Error {
  status: number;
  code?: string;
  constructor(message: string, status: number, code?: string) {
    super(message);
    this.status = status;
    this.code = code;
  }
}

export async function request<T = any>(path: string, method = 'GET', body?: unknown): Promise<T> {
  const headers: Record<string, string> = {};
  if (body !== undefined) headers['Content-Type'] = 'application/json';
  const current = token();
  if (current) headers.Authorization = `Bearer ${current}`;
  let response: Response;
  try {
    response = await fetch(`${BASE}${path}`, { method, headers, body: body === undefined ? undefined : JSON.stringify(body) });
  } catch {
    throw new ApiError('Немає зв\'язку з сервером. Перевірте, чи запущені API і база даних.', 0);
  }
  if (!response.ok) {
    let message = 'Сталася помилка. Спробуйте ще раз.';
    let code: string | undefined;
    try {
      const data = await response.json();
      const detail = data?.detail;
      if (detail && typeof detail === 'object' && 'code' in detail) {
        code = String(detail.code);
        if (code === 'STALE_SESSION_VERSION') message = 'Інтервю змінилося в іншій вкладці. Дані оновлено.';
      } else if (typeof detail === 'string') {
        message = knownDetails[detail] ?? message;
      }
    } catch { /* keep the generic message */ }
    if (response.status === 401) message = 'Сесія завершилася. Увійдіть знову.';
    throw new ApiError(message, response.status, code);
  }
  if (response.status === 204) return null as T;
  return response.json() as Promise<T>;
}
