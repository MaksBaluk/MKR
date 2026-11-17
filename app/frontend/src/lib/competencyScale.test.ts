import { describe, expect, it } from 'vitest';
import { diffChip, rowSummary } from './competencyScale';

describe('diffChip', () => {
  it('signs the difference with real minus', () => {
    expect(diffChip(10)).toEqual({ text: '+10 в.п.', hint: 'Самооцінка вища за оцінку LLM' });
    expect(diffChip(-15)).toEqual({ text: '−15 в.п.', hint: 'Самооцінка нижча за оцінку LLM' });
    expect(diffChip(0)).toEqual({ text: '0 в.п.', hint: 'Оцінки збігаються' });
  });
});

describe('rowSummary', () => {
  it('describes both values for assistive tech', () => {
    expect(rowSummary(0.8, 0.6)).toBe('Оцінка LLM 80%, самооцінка 60%');
    expect(rowSummary(null, null)).toBe('Оцінка LLM відсутня, самооцінка не вказана');
  });
});
