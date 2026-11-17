import { Field, describedBy } from '@/components/ui/field';
import { Input, Select } from '@/components/ui/input';
import { LEVELS, TRACKS, WORK_MODES_PROFILE, type ProfileForm, type ProfileFormErrors } from '@/lib/profiles';

/** The profile fields in one grid: used by the profile page (inline) and by the create/edit dialog. */
export function ProfileFields({ form, errors, onChange, idBase }: {
  form: ProfileForm;
  errors: ProfileFormErrors;
  onChange: (key: keyof ProfileForm, value: string) => void;
  idBase: string;
}) {
  const id = (k: string) => `${idBase}-${k}`;
  const input = (k: keyof ProfileForm) => ({
    id: id(k), value: form[k], 'aria-invalid': errors[k] ? true : undefined,
    'aria-describedby': describedBy(id(k), undefined, errors[k]),
    onChange: (e: { target: { value: string } }) => onChange(k, e.target.value),
  });
  return (
    <div className="grid gap-4 sm:grid-cols-2">
      <Field id={id('name')} label="Назва профілю" error={errors.name} className="sm:col-span-2">
        <Input {...input('name')} maxLength={120} placeholder="Наприклад, Python Backend" autoComplete="off" />
      </Field>
      <Field id={id('track')} label="Напрям" error={errors.track}>
        <Select {...input('track')}>
          <option value="">Оберіть напрям</option>
          {TRACKS.map((t) => <option key={t.value} value={t.value}>{t.label}</option>)}
        </Select>
      </Field>
      <Field id={id('target_level')} label="Рівень, на який претендуєте" error={errors.target_level}>
        <Select {...input('target_level')}>
          <option value="">Оберіть рівень</option>
          {LEVELS.map((l) => <option key={l.value} value={l.value}>{l.label}</option>)}
        </Select>
      </Field>
      <Field id={id('years')} label="Роки досвіду" error={errors.years}>
        <Input {...input('years')} inputMode="numeric" placeholder="Наприклад, 3" />
      </Field>
      <Field id={id('work_mode')} label="Бажаний формат" error={errors.work_mode}>
        <Select {...input('work_mode')}>
          <option value="">Не вказано</option>
          {WORK_MODES_PROFILE.map((m) => <option key={m.value} value={m.value}>{m.label}</option>)}
        </Select>
      </Field>
      <Field id={id('location')} label="Локація" error={errors.location}>
        <Input {...input('location')} maxLength={120} placeholder="Наприклад, Київ" />
      </Field>
      <Field id={id('desired_title')} label="Бажана посада" error={errors.desired_title}>
        <Input {...input('desired_title')} maxLength={160} placeholder="Наприклад, Python Developer" />
      </Field>
    </div>
  );
}
