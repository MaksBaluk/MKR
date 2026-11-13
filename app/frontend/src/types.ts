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

/** Row of the public vacancy catalogue (`GET /vacancies`). */
export interface CatalogVacancy {
  id: string;
  track: string;
  title: string;
  company: string;
  seniority: string | null;
  location: string;
  work_mode: string | null;
  employment: string | null;
  salary_min: number | null;
  salary_max: number | null;
  currency: string | null;
  summary: string | null;
  stack: string[] | null;
  years_min: number | null;
  years_max: number | null;
  source_label: string | null;
  requirements_count: number;
}

export interface CatalogPage {
  items: CatalogVacancy[];
  total: number;
  page: number;
  page_size: number;
  /** Counts per option, computed with all other filters applied. */
  facets: { track: Record<string, number>; work_mode: Record<string, number>; seniority: Record<string, number> };
}

export interface RequirementGroup {
  id: string;
  kind: 'MANDATORY' | 'DESIRED' | string;
  label: string;
  excerpt: string;
  alternatives: { competency_id: string; name: string; required_level: number }[];
}

/** Full vacancy (`GET /vacancies/{id}`). */
export interface VacancyDetail extends CatalogVacancy {
  description: string | null;
  responsibilities: string[] | null;
  benefits: string[] | null;
  source_type: string | null;
  source_url: string | null;
  fixture_version: string | null;
  requirements: RequirementGroup[];
}

export interface AttemptSummary {
  id: string;
  attempt_no: number;
  status: 'ACTIVE' | 'PAUSED' | 'FINISHED' | string;
  cohort_id: string;
  created_at: string | null;
  topics_used: number;
  answers_count: number;
}
