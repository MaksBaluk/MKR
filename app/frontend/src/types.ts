export type Track = 'python' | 'marketing' | 'design';

export type Requirement = {
  id: string; kind: 'MANDATORY' | 'DESIRED'; label: string; excerpt: string;
  alternatives: { competency_id: string; required_level: number; normalization_status: string }[];
};

export type Vacancy = {
  id: string; track: Track; title: string; company: string; seniority: string; years_min: number;
  years_max: number | null; location: string; work_mode: string; salary_min: number | null; salary_max: number | null;
  currency: string; summary: string; description: string; responsibilities: string[]; benefits: string[];
  stack: string[]; source_type: string; groups?: Requirement[]; requirements_count?: number;
};

export type Skill = { id: string; label: string; label_uk: string; track: string; summary: string };

export type Profile = {
  id: string; email: string; display_name: string; track: Track; desired_title: string;
  years_experience: number | null; location: string; levels: Record<string, number | null>;
  skills: { competency_id: string; level: number | null; context: string }[];
};

export type LLMInfo = {
  provider: string; configured: boolean; model: string | null; question_generation: boolean;
  question_rephrasing?: boolean; question_strategy: string; answer_assessment_policy: string;
};

export type Turn = {
  id: string; sequence: number; competency_id: string; question_text: string; question_kind: string;
  question_format: 'OPEN' | 'OPTIONAL_CHECK'; question_source: string;
  question_options: { id: string; text: string }[]; status: string;
  answer_option: string | null; answer_text: string | null; assessment_status: string | null;
};

export type Interview = {
  id: string; snapshot_id: string; status: string; mode: string; question_budget: number;
  used_questions: number; state_version: number; current_question: Turn | null; turns: Turn[];
  effective_profile: { levels: Record<string, number | null> }; provider_mode: string;
  llm_warning?: string | null;
};

export type Evidence = {
  id: string; turn_id: string; competency_id: string; level: number | null; provenance: string;
  status: 'PROPOSED' | 'CONFIRMED' | 'REJECTED'; evidence_quote: string; confidence: string; uncertainty: string;
};

export type Snapshot = {
  id: string; name: string; vacancy_count: number; vacancy_ids: string[]; status: string; track: string;
  cohort_policy: { policy: string; cap: number; dropped_count: number } | null; sha256: string;
  baseline_match_id?: string;
};

export type MatchItem = {
  vacancy_id: string; vacancy: Vacancy; required_class: number; match: number | null; coverage: number | null;
  r_score: number | null; s: number; f: number; u: number; rank_position: number | null;
  years_eligibility: boolean | null;
  groups: (Requirement & { state: 'S' | 'F' | 'U'; alternatives: (Requirement['alternatives'][number] & { candidate_level: number | null })[] })[];
};

export type MatchRun = {
  id: string; snapshot_id: string; interview_id: string | null; total: number; items: MatchItem[];
  profile: { source: 'SELF_REPORT_BASELINE' | 'POST_INTERVIEW'; provenance?: Record<string, unknown> };
  profile_version_id: string | null; unchanged_reason: string | null;
};

export type Recommendations = {
  items: MatchItem[]; total: number; track: Track; profile_source: string;
  evidence_quality: { assessed_competencies: number; total_competencies: number };
};
