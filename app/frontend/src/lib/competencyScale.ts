const pct = (v: number) => Math.round(v * 100);

/** Small signed chip for self minus LLM; the sign is in the text, never colour only. */
export function diffChip(diff: number): { text: string; hint: string } {
  if (diff === 0) return { text: '0 в.п.', hint: 'Оцінки збігаються' };
  return diff > 0
    ? { text: `+${diff} в.п.`, hint: 'Самооцінка вища за оцінку LLM' }
    : { text: `−${Math.abs(diff)} в.п.`, hint: 'Самооцінка нижча за оцінку LLM' };
}

export function rowSummary(llm: number | null, self: number | null): string {
  return `${llm === null ? 'Оцінка LLM відсутня' : `Оцінка LLM ${pct(llm)}%`}, ${self === null ? 'самооцінка не вказана' : `самооцінка ${pct(self)}%`}`;
}
