const pct = (v: number) => Math.round(v * 100);

/** Small signed chip for self minus LLM; the sign is in the text, never colour only. */
export function diffChip(diff: number): { text: string; hint: string } {
  if (diff === 0) return { text: 'збігається з LLM', hint: 'Самооцінка дорівнює оцінці LLM' };
  return diff > 0
    ? { text: `вище за LLM на ${diff}%`, hint: 'Ваша самооцінка вища за оцінку LLM' }
    : { text: `нижче за LLM на ${Math.abs(diff)}%`, hint: 'Ваша самооцінка нижча за оцінку LLM' };
}

export function rowSummary(llm: number | null, self: number | null): string {
  return `${llm === null ? 'Оцінка LLM відсутня' : `Оцінка LLM ${pct(llm)}%`}, ${self === null ? 'самооцінка не вказана' : `самооцінка ${pct(self)}%`}`;
}
