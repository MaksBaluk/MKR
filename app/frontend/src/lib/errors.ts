/** True when a lazily loaded chunk failed to download (offline, or a new deploy removed the old file). */
export function isChunkLoadError(err: unknown): boolean {
  if (!(err instanceof Error)) return false;
  if (err.name === 'ChunkLoadError') return true;
  return /dynamically imported module|importing a module script failed/i.test(err.message);
}
