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
  /** Requirement groups met / failed, uncapped (same numbers as the vacancy detail summary). */
  met_count: number;
  gap_count: number;
  tags: string[];
  /** Provenance label; currently «Djinni» for every catalog vacancy (owner statement); null if the vacancy row is gone. */
  source_label: string | null;
  /** true for vacancies that are not imported postings: shown with a «приклад» note. */
  source_example?: boolean;
  groups_total: number;
  /** Requirement groups with at least one assessed alternative. */
  groups_assessed: number;
  /** True when no mandatory group failed and the confirmed share is enough (server rule). */
  fits: boolean;
  /** Short Ukrainian explanations, strengths first. */
  reasons: string[];
}

/** Display label over the unchanged percent-first order (server rule); never a new ranking. */
export type ResultSection = 'DESIRED_LEVEL' | 'OTHER_FITTING' | 'UNRESOLVED_OR_GAPS';
export type LevelName = 'JUNIOR' | 'MIDDLE' | 'SENIOR' | 'UNKNOWN';

export interface LevelCriterion {
  id: string;
  /** Ukrainian criterion title (falls back to the id on the server when no title is known). */
  title: string;
  kind: 'PRACTICE' | 'COMPETENCY';
}

/** One critical capability of a pooled level policy (v2-v4): any of its criteria can confirm it. */
export interface LevelPool {
  id: string;
  /** Ukrainian capability name. */
  title: string;
}

export interface LevelCoverage {
  status: 'SUPPORTED' | 'GAP' | 'UNVERIFIED';
  critical_total: number;
  assessed_count: number;
  confirmed_count: number;
  gap_count: number;
  confirmed: LevelCriterion[];
  gaps: LevelCriterion[];
  unassessed: LevelCriterion[];
  /** Pooled policies only (v2-v4). DECLINED exists only from v4. */
  pools?: (LevelPool & { status: 'CONFIRMED' | 'GAP' | 'UNRESOLVED' | 'UNASSESSED' | 'DECLINED'; criteria: LevelCriterion[] })[];
  /** Capability policies (v4) only. */
  technical_confirmed_count?: number;
  practice_confirmed_count?: number;
  /** Gaps reported but not blocking the level (v4: at most one, never in a hard capability). */
  tolerated_gaps?: LevelCriterion[];
  /** Tools the candidate said they never worked with, while an alternative tool was never asked (v4). */
  declined?: LevelCriterion[];
}

/** Assessed professional level of one finished attempt: evidence-based, never an input of the vacancy order. */
export interface AssessedLevel {
  interview_id: string;
  /** Profile value copied when the attempt started (attempts before 2026-11-19: at finish): junior | middle | senior | lead, or null. */
  desired_level: string | null;
  assessed_level: LevelName;
  highest_supported_level: LevelName;
  assessment_status: 'ASSESSED' | 'INSUFFICIENT_DATA' | 'GAPS_AT_JUNIOR' | 'POLICY_UNAVAILABLE';
  policy: { id: string | null; version: string | null; status: string | null };
  coverage_by_level: Record<string, LevelCoverage>;
  confirmed_strengths: LevelCriterion[];
  critical_gaps: LevelCriterion[];
  unassessed_criteria: LevelCriterion[];
  /** Capabilities with no evidence at all (pooled policies v2-v4); empty or absent for per-criterion policies (v1). */
  unassessed_pools?: LevelPool[];
  /** Capabilities with evidence that decided nothing: borderline or untraced scores. Absent in older responses. */
  unresolved_pools?: LevelPool[];
  /** Capabilities shown only through a tool the candidate never worked with (v4). Absent in older responses. */
  declined_pools?: LevelPool[];
  evidence_references: (LevelCriterion & { turn_ids: string[] })[];
  /** Ukrainian lines; criterion ids are already replaced by titles on the server. */
  explanation: string[];
  /** Policy note (e.g. «Потребує експертної валідації») or null. */
  note: string | null;
  created_at: string | null;
}

export interface ResultVacancy extends RankedItem {
  /** Optional for older API responses; a missing value is shown in the last section. */
  section?: ResultSection;
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
  /** Same value as interview_score; kept for compatibility. */
  score: number | null;
  /** LLM interview grade, read-only. */
  interview_score: number | null;
  /** Editable self-rating of this profile, null if not rated. */
  self_rating: number | null;
  /** Short explanation of the grade (at most two distinct sentences). */
  reason: string;
  /** The evaluator judged the answers sufficient to grade every criterion; false means the grade is rough. */
  sufficient_evidence: boolean;
  /** Share of rubric weight with a known grade (E_c); optional, absent on older API responses. */
  coverage?: number | null;
  /** False when coverage is below the overall-level threshold; show criteria, not one summary level. */
  overall_level_allowed?: boolean;
  evidence: { turn_id: string; exact_excerpt: string }[];
}

export interface ProfileResults {
  has_results: boolean;
  attempt_id: string | null;
  profile_id: string;
  total: number;
  fitting_total: number;
  all_total: number;
  page: number;
  page_size: number;
  items: ResultVacancy[];
  competencies: CompetencyResult[];
  /** null when there is no finished attempt or the level could not be determined; absent on older responses. */
  level?: AssessedLevel | null;
  market: MarketSkill[];
  note: string;
}

export interface CandidateProfile {
  id: string;
  name: string;
  /** Chosen by the candidate; null until then (no default direction). */
  track: string | null;
  desired_title: string;
  target_level: string | null;
  work_mode: string | null;
  years_experience: number | null;
  location: string;
  archived: boolean;
  attempts_count: number;
  latest_finished_attempt_id: string | null;
  /** Unfinished attempt (active or paused), if any. */
  open_attempt: { id: string; cohort_id: string; status: string } | null;
  latest_finished_attempt: { id: string; cohort_id: string } | null;
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
  /** true for vacancies that are not imported postings: shown with a «приклад» note. */
  source_example?: boolean;
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

/** `GET /profiles/{id}/results/{vacancy_id}`: where the candidate fits one vacancy and why. */
export type FitState = 'MET' | 'BORDERLINE' | 'GAP' | 'UNKNOWN';
export type FitGroupStatus = 'SATISFIED' | 'FAILED' | 'UNRESOLVED';

export interface FitAlternative {
  competency_id: string;
  name: string;
  required_level: 1 | 2 | 3;
  required_label: 'базовий' | 'робочий' | 'просунутий';
  /** Needed score on the 0..1 interview scale. */
  threshold: number;
  /** Interview grade 0..1, null when not assessed. */
  candidate_score: number | null;
  /** Share (0..1) of the alternative's required criteria that were graded; below 1 the state stays UNKNOWN. */
  coverage?: number | null;
  state: FitState;
}

export interface FitGroup {
  id: string;
  kind: 'MANDATORY' | 'DESIRED';
  label: string;
  excerpt: string;
  status: FitGroupStatus;
  alternatives: FitAlternative[];
}

export interface VacancyFitBreakdown {
  vacancy_id: string;
  title: string;
  company: string;
  confirmed_share: number;
  fits: boolean;
  label: 'RANKED' | 'LOW_INFORMATION' | 'NOT_EVALUABLE';
  z: 0 | 1 | 2;
  summary: { met: number; gap: number; unknown: number };
  groups: FitGroup[];
}
