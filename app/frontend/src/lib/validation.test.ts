import { expect, test } from 'vitest';
import { validateAuth } from '@/lib/validation';

test('login needs a well-formed email and any non-empty password', () => {
  expect(validateAuth('login', { email: '', name: '', password: '' })).toEqual({
    email: 'Вкажіть електронну пошту.',
    password: 'Введіть пароль.',
  });
  expect(validateAuth('login', { email: 'bad@', name: '', password: 'x' }).email).toMatch(/формат/);
  expect(validateAuth('login', { email: ' a@b.ua ', name: '', password: 'short' })).toEqual({});
});

test('registration also checks name and password length', () => {
  const errors = validateAuth('register', { email: 'a@b.ua', name: ' І ', password: '123456789' });
  expect(Object.keys(errors).sort()).toEqual(['name', 'password']);
  expect(validateAuth('register', { email: 'a@b.ua', name: 'Іра', password: '1234567890' })).toEqual({});
});
