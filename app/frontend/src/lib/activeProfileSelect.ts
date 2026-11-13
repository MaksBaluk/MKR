/** Remembered profile if it still exists, otherwise the first (oldest) profile, otherwise none. */
export function pickActiveId(profiles: readonly { id: string }[], storedId: string | null): string | null {
  if (storedId && profiles.some((p) => p.id === storedId)) return storedId;
  return profiles[0]?.id ?? null;
}
