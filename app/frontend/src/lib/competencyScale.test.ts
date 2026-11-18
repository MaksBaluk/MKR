import { describe, expect, it } from 'vitest';
import { diffChip, rowSummary } from './competencyScale';

describe('diffChip', () => {
  it('signs the difference with real minus', () => {
    expect(diffChip(10)).toEqual({ text: 'вище за LLM на 10%', hint: 'Ваша самооцінка вища за оцінку LLM' });
    expect(diffChip(-15)).toEqual({ text: 'нижче за LLM на 15%', hint: 'Ваша самооцінка нижча за оцінку LLM' });
    expect(diffChip(0)).toEqual({ text: 'збігається з LLM', hint: 'Самооцінка дорівнює оцінці LLM' });
  });
});

describe('rowSummary', () => {
  it('describes both values for assistive tech', () => {
    expect(rowSummary(0.8, 0.6)).toBe('Оцінка LLM 80%, самооцінка 60%');
    expect(rowSummary(null, null)).toBe('Оцінка LLM відсутня, самооцінка не вказана');
  });
});
