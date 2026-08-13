# E4 Run-Coverage Records

This directory contains the de-identified condition-level evidence for the
E4 run-coverage check.

- `e4_condition_coverage.csv` contains one row for each of the 630 unique
  batch-condition keys reported in the manuscript.
- `e4_batch_summary.csv` aggregates the same records into nine batches: six
  batches in the 420-condition main evidence chain and three unseen-topic
  batches containing 210 conditions.

`initial_status=ok` means that a successful row for that condition was retained
from the initial batch. `failed_or_missing` means that the condition did not
have a successful initial-batch row. `repair_affected=true` includes both
conditions added after an initial failure and initially successful conditions
later replaced under a frozen quality or execution rule. It must therefore not
be interpreted as the initial failure count.

All 630 rows have `final_status=ok`. This records final normalized coverage,
not 630 first-attempt successes. Full generated content, provider credentials,
raw error messages, account records, and model reasoning traces are excluded.
