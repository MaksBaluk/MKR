export type AuthMode = 'login' | 'register';
export interface AuthFields {
  email: string;
  name: string;
  password: string;
}
export type AuthErrors = Partial<Record<keyof AuthFields, string>>;

const EMAIL = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;
export const MIN_PASSWORD = 10;

/** Client-side checks mirroring the API limits; the server stays the authority. */
export function validateAuth(mode: AuthMode, f: AuthFields): AuthErrors {
  const errors: AuthErrors = {};
  const email = f.email.trim();
  if (!email) errors.email = 'Вкажіть електронну пошту.';
  else if (!EMAIL.test(email)) errors.email = 'Перевірте формат пошти, наприклад name@example.com.';
  if (!f.password) errors.password = 'Введіть пароль.';
  else if (mode === 'register' && f.password.length < MIN_PASSWORD)
    errors.password = `Пароль має містити щонайменше ${MIN_PASSWORD} символів.`;
  if (mode === 'register' && f.name.trim().length < 2) errors.name = 'Ім’я має містити щонайменше 2 символи.';
  return errors;
}
