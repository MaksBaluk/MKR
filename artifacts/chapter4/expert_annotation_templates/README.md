# Expert label templates

**Protocol v2 (chapter 4, 2026-11):** the working annotation files are `../data/annotations/expert_criterion_annotations.csv`, `expert_vacancy_relevance.csv`, `expert_seniority.csv` (header-only; annotator ids `LLM_ANNOTATOR_1/2/3` = pilot, `HUMAN_EXPERT_<n>` = human, final rows `ADJUDICATED`), with inputs and the formal 0–3 scale, level definitions, fixed vacancy pool and adjudication procedure in `../data/annotation_inputs/`. `scripts/chapter4/chapter4_metrics.py` reads them. The two files below are the slots for the product loader `backend/experiments/expert_labels.py` (human experts only, `data_status=EXPERT`); they stay empty.

`relevance_labels.csv` and `criterion_labels.csv` are header-only. They hold no labels; real expert labels must come from independent human annotators and are never invented or generated.

## relevance_labels.csv
- `candidate_id`, `vacancy_id`: the pair being judged.
- `grade`: integer 0..3 (0 irrelevant, 1 weak, 2 relevant, 3 strongly relevant). Relevant means grade >= 2.
- `rationale`: at least 10 characters.
- `annotator_id`: required, stable per person.
- `label_version`: version of the annotation guideline.
- `data_status`: `EXPERT` for real labels, `SYNTHETIC_TEST_DATA` only for test fixtures. Do not mix in one file.
- `review_status`: `PENDING` (default), `REVIEWED`, `ADJUDICATED`.

## criterion_labels.csv
- `candidate_id`, `action_id`, `criterion_id`, `rubric_version`: the graded criterion.
- `expert_score`: number in [0,1], or empty when the answers give no basis (empty is unknown, never 0).
- `evidence_reference`: required (3+ characters) when `expert_score` is set; quote or point to the answer text.
- Other fields as above.

## Protocol
Two annotators label the same keys independently. Each key has at most one label per annotator. A third person, distinct from both annotators, adjudicates disagreements; the final file covers exactly the shared keys, carries the adjudicator as `annotator_id` and `review_status=ADJUDICATED`. Annotator and final files must share one `data_status` and one `label_version` (criterion labels: one `rubric_version` per action). Agreement (exact, quadratic weighted kappa) is reported before adjudication. Results built from synthetic or missing labels do not establish method quality.
