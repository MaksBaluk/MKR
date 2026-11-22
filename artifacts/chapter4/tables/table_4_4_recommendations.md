# Таблиця 4.4. Якість рекомендацій (P@5/NDCG@10 — лише за незалежними мітками; інакше NO_GROUND_TRUTH)

| mode | budget | candidates | precision_at_5 | ndcg_at_10 | status | share_top10_unresolved_mandatory | share_top10_failed_mandatory | top5_overlap_vs_A |
|---|---|---|---|---|---|---|---|---|
| A_INITIAL_PROFILE | — | 18 |  |  | NO_GROUND_TRUTH | 1.0 | 0.0 | 1.0 |
| B_STATIC | 10 | 18 |  |  | NO_GROUND_TRUTH | 1.0 | 0.0 | 0.1555 |
| B_STATIC | 20 | 18 |  |  | NO_GROUND_TRUTH | 0.8833 | 0.3333 | 0.2889 |
| B_STATIC | 30 | 18 |  |  | NO_GROUND_TRUTH | 0.8833 | 0.3333 | 0.2889 |
| B_STATIC | 50 | 18 |  |  | NO_GROUND_TRUTH | 0.8833 | 0.3333 | 0.2889 |
| C_ADAPTIVE_NO_MARKET | 10 | 18 |  |  | NO_GROUND_TRUTH | 0.9889 | 0.0 | 0.1407 |
| C_ADAPTIVE_NO_MARKET | 20 | 18 |  |  | NO_GROUND_TRUTH | 0.9889 | 0.0278 | 0.0852 |
| C_ADAPTIVE_NO_MARKET | 30 | 18 |  |  | NO_GROUND_TRUTH | 0.9796 | 0.0278 | 0.1185 |
| C_ADAPTIVE_NO_MARKET | 50 | 18 |  |  | NO_GROUND_TRUTH | 0.9796 | 0.1241 | 0.1111 |
| D_FULL_COMPETENCEMATCH | 10 | 18 |  |  | NO_GROUND_TRUTH | 0.9908 | 0.0 | 0.2111 |
| D_FULL_COMPETENCEMATCH | 20 | 18 |  |  | NO_GROUND_TRUTH | 0.9722 | 0.0333 | 0.1185 |
| D_FULL_COMPETENCEMATCH | 30 | 18 |  |  | NO_GROUND_TRUTH | 0.9556 | 0.0352 | 0.1482 |
| D_FULL_COMPETENCEMATCH | 50 | 18 |  |  | NO_GROUND_TRUTH | 0.95 | 0.1741 | 0.1704 |
