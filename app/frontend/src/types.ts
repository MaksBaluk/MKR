export interface Profile {
  id: string;
  email: string;
  display_name: string;
  track: string;
  desired_title: string;
  years_experience: number | null;
  location: string;
  self_ratings: { action_id: string; value: number | null; source: 'SELF_REPORT'; editable: true }[];
}

export interface CohortResponse {
  cohort_id: string | null;
  vacancy_count: number;
  sha256: string | null;
  empty: boolean;
}

export interface MarketSkill {
  order: number;
  action_id: string;
  name: string;
}

export interface TurnView {
  id: string;
  sequence: number;
  action_id: string;
  action_name: string;
  created_at: string | null;
  question_text: string;
  question_source: string;
  answer_text: string | null;
  graded: boolean;
}

export interface InterviewState {
  id: string;
  status: 'ACTIVE' | 'PAUSED' | 'FINISHED';
  version: number;
  turns: TurnView[];
  pending_turn: TurnView | null;
  topics_used: number;
}

export interface AssessmentItem {
  interview_id: string;
  action_id: string;
  action_name: string;
  criterion_id: string;
  score: number | null;
  reason: string;
  evidence: { turn_id: string; exact_excerpt: string }[];
  revision: number;
  source: 'LLM_EVALUATOR';
  editable: false;
}

export interface RankedItem {
  vacancy_id: string;
  label: 'RANKED' | 'LOW_INFORMATION' | 'NOT_EVALUABLE';
  z: 0 | 1 | 2;
  x: 0 | 1 | 2;
  l_mandatory: number;
  l_preferred: number;
  w_mandatory: number;
  w_preferred: number;
  has_mandatory: boolean;
  has_preferred: boolean;
  confirmed_share: number;
  strengths: string[];
  gaps: string[];
  unknown_count: number;
  tags: string[];
  /** «Djinni» for original fixtures, «Тестова вакансія» for generated ones; null if the vacancy row is gone. */
  source_label: string | null;
  groups_total: number;
  /** Requirement groups with at least one assessed alternative. */
  groups_assessed: number;
}

export interface ResultVacancy extends RankedItem {
  title: string;
  company: string;
  location: string;
  work_mode: string | null;
  seniority: string | null;
  years_min: number | null;
}

export interface CompetencyResult {
  action_id: string;
  action_name: string;
  score: number | null;
  reason: string;
  evidence: { turn_id: string; exact_excerpt: string }[];
}

export interface ProfileResults {
  has_results: boolean;
  attempt_id: string | null;
  profile_id: string;
  total: number;
  page: number;
  page_size: number;
  items: ResultVacancy[];
  competencies: CompetencyResult[];
  market: MarketSkill[];
  note: string;
}

export interface CandidateProfile {
  id: string;
  name: string;
  track: string;
  desired_title: string;
  years_experience: number | null;
  location: string;
  archived: boolean;
  attempts_count: number;
  latest_finished_attempt_id: string | null;
  created_at: string | null;
}

export interface SelfRatingValue {
  action_id: string;
  value: number | null;
}
