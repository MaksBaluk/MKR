import { useState, type FormEvent } from 'react';
import { Check, Lightbulb } from 'lucide-react';
import { uk } from '../i18n/uk';
import type { Profile, Skill, Track } from '../types';
import { Card, Tag2 } from '../components/ui';

export type ProfileDraft = { display_name: string; desired_title: string; years_experience: number | null; location: string; track: Track };

export function ProfileScreen({ profile, skills, busy, onSave, onSkill }: {
  profile: Profile; skills: Skill[]; busy: boolean;
  onSave: (draft: ProfileDraft) => Promise<void>; onSkill: (id: string, level: number | null) => Promise<void>;
}) {
  const [draft, setDraft] = useState<ProfileDraft>({
    display_name: profile.display_name, desired_title: profile.desired_title, years_experience: profile.years_experience,
    location: profile.location, track: profile.track,
  });

  function submit(e: FormEvent) { e.preventDefault(); void onSave(draft); }

  return (
    <>
      <div className="intro-line">
        <div>
          <h2>{uk.profile.subtitle}</h2>
          <p>{uk.profile.intro}</p>
        </div>
        <Tag2><span aria-hidden="true">●</span> Самооцінка</Tag2>
      </div>

      <div className="profile-grid">
        <Card className="profile-card">
          <form onSubmit={submit} className="form-grid">
            <div className="field">
              <label htmlFor="p-name">{uk.profile.name}</label>
              <input id="p-name" required minLength={2} value={draft.display_name} onChange={e => setDraft({ ...draft, display_name: e.target.value })} />
            </div>
            <div className="field">
              <label htmlFor="p-title">{uk.profile.desiredTitle}</label>
              <input id="p-title" value={draft.desired_title} onChange={e => setDraft({ ...draft, desired_title: e.target.value })} />
            </div>
            <div className="field">
              <label htmlFor="p-years">{uk.profile.years}</label>
              <input id="p-years" type="number" min={0} max={70} inputMode="numeric" value={draft.years_experience ?? ''}
                onChange={e => setDraft({ ...draft, years_experience: e.target.value === '' ? null : Number(e.target.value) })} />
            </div>
            <div className="field">
              <label htmlFor="p-location">{uk.profile.location}</label>
              <input id="p-location" value={draft.location} onChange={e => setDraft({ ...draft, location: e.target.value })} />
            </div>
            <div className="field full">
              <label htmlFor="p-track">{uk.profile.track}</label>
              <select id="p-track" value={draft.track} onChange={e => setDraft({ ...draft, track: e.target.value as Track })}>
                {Object.entries(uk.tracks).map(([id, label]) => <option key={id} value={id}>{label}</option>)}
              </select>
              <small className="muted">{uk.profile.trackNote}</small>
            </div>
            <button className="btn primary" disabled={busy} type="submit"><Check size={17} aria-hidden="true" />{uk.profile.save}</button>
          </form>
        </Card>
        <Card className="profile-note">
          <Lightbulb size={24} aria-hidden="true" />
          <h3>{uk.profile.scaleTitle}</h3>
          <p>{uk.profile.scaleText}</p>
        </Card>
      </div>

      <Card className="skills-card">
        <h3>{uk.profile.skills}</h3>
        <p className="muted">{uk.profile.skillsHint}</p>
        <ul className="skills-list">
          {skills.map(s => {
            const id = `skill-${s.id}`;
            const value = profile.levels[s.id];
            return (
              <li key={s.id} className="skill-row">
                <div>
                  <strong>{s.label_uk}</strong>
                  <p className="muted">{s.summary}</p>
                </div>
                <label htmlFor={id} className="sr-only">{`Рівень: ${s.label_uk}`}</label>
                <select id={id} value={value === null || value === undefined ? 'unknown' : String(value)} disabled={busy}
                  onChange={e => void onSkill(s.id, e.target.value === 'unknown' ? null : Number(e.target.value))}>
                  <option value="unknown">{uk.profile.unknown}</option>
                  <option value="0">{uk.profile.l0}</option>
                  <option value="1">{uk.profile.l1}</option>
                  <option value="2">{uk.profile.l2}</option>
                  <option value="3">{uk.profile.l3}</option>
                </select>
              </li>
            );
          })}
        </ul>
      </Card>
    </>
  );
}
