export class ApiError extends Error {
  constructor(public status: number, message: string) {
    super(message);
  }
}

const TOKEN_KEY = 'cm_token';

export function getToken(): string | null {
  try {
    return localStorage.getItem(TOKEN_KEY);
  } catch {
    return null;
  }
}

export function setToken(token: string | null): void {
  try {
    if (token) localStorage.setItem(TOKEN_KEY, token);
    else localStorage.removeItem(TOKEN_KEY);
  } catch {
    /* storage unavailable: session lives in memory only */
  }
}

export async function api<T>(path: string, init: RequestInit & { json?: unknown } = {}): Promise<T> {
  const headers: Record<string, string> = { ...(init.headers as Record<string, string> | undefined) };
  const token = getToken();
  if (token) headers.Authorization = `Bearer ${token}`;
  let body = init.body;
  if (init.json !== undefined) {
    headers['Content-Type'] = 'application/json';
    body = JSON.stringify(init.json);
  }
  let response: Response;
  try {
    response = await fetch(`/api/v1${path}`, { ...init, headers, body });
  } catch {
    throw new ApiError(0, 'Немає з’єднання з сервером. Перевірте мережу та спробуйте ще раз.');
  }
  if (!response.ok) {
    let message = 'Сталася помилка. Спробуйте ще раз.';
    try {
      const data = await response.json();
      if (typeof data.detail === 'string') message = data.detail;
    } catch {
      /* keep default message */
    }
    throw new ApiError(response.status, message);
  }
  if (response.status === 204) return undefined as T;
  return (await response.json()) as T;
}
