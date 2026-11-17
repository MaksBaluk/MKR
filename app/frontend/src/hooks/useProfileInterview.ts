import { useActiveProfile } from '@/lib/activeProfile';
import { interviewFromProfile } from '@/lib/profileInterview';
import type { SessionInterview } from '@/lib/navigation';

/** Interview state of the active candidate profile (not of the account): drives banners, locks and the stepper. */
export function useProfileInterview(): SessionInterview | null {
  const { active } = useActiveProfile();
  return interviewFromProfile(active);
}
