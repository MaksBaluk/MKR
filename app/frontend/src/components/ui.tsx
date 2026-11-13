import type { ReactNode } from 'react';
import { ArrowRight, Sparkles, X, XCircle } from 'lucide-react';

export function Card({ children, className = '', as: Tag = 'section' }: { children: ReactNode; className?: string; as?: 'section' | 'article' | 'div' }) {
  return <Tag className={`card ${className}`}>{children}</Tag>;
}

export function Tag2({ children, tone = 'blue' }: { children: ReactNode; tone?: 'blue' | 'green' | 'orange' | 'grey' | 'red' }) {
  return <span className={`tag tag-${tone}`}>{children}</span>;
}

export function Bar({ value, tone = 'blue', label }: { value: number | null; tone?: 'blue' | 'green' | 'orange'; label: string }) {
  const percent = value === null ? 0 : Math.round(value * 100);
  return (
    <div className="level-track" role="progressbar" aria-label={label} aria-valuemin={0} aria-valuemax={100}
      aria-valuenow={percent} aria-valuetext={value === null ? 'не оцінено' : `${percent}%`}>
      <div className={`level-fill ${tone}`} style={{ width: `${percent}%` }} />
    </div>
  );
}

export function EmptyState({ title, text, action, onAction }: { title: string; text: string; action?: string; onAction?: () => void }) {
  return (
    <Card className="empty">
      <div className="empty-icon" aria-hidden="true"><Sparkles size={29} /></div>
      <h3>{title}</h3>
      <p>{text}</p>
      {action && onAction && <button className="btn primary" onClick={onAction}>{action} <ArrowRight size={16} aria-hidden="true" /></button>}
    </Card>
  );
}

export function ErrorAlert({ message, onDismiss, onRetry }: { message: string; onDismiss: () => void; onRetry?: () => void }) {
  return (
    <div className="alert-error" role="alert">
      <XCircle size={18} aria-hidden="true" />
      <span>{message}</span>
      {onRetry && <button className="btn ghost small" onClick={onRetry}>Спробувати знову</button>}
      <button className="icon-button" aria-label="Закрити повідомлення" onClick={onDismiss}><X size={15} aria-hidden="true" /></button>
    </div>
  );
}

export function Notice({ message, onDismiss }: { message: string; onDismiss: () => void }) {
  return (
    <div className="alert-ok" role="status">
      <span>{message}</span>
      <button className="icon-button" aria-label="Закрити повідомлення" onClick={onDismiss}><X size={15} aria-hidden="true" /></button>
    </div>
  );
}
