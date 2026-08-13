# Analysis Reproducibility Package

This package accompanies the manuscript "Quality-Gated Evaluation of Learner-Profile Responsiveness in Retrieval-Augmented Multi-Agent Learning Resource Generation."

## Status and scope

- This local directory is a release candidate and has not yet been published.
- Software is covered by the MIT License, and author-owned research materials are covered by CC BY 4.0. See `LICENSE-SCOPE.md` for the exact mapping and exclusions. The directory must not be represented as a public release until the corresponding author approves the repository and release tag.
- The package performs analysis-level reproduction from de-identified frozen inputs. It does not call an external LLM API and does not reproduce the product-facing Web application.
- The production resource-agent implementations are not included. The package therefore audits the retained generation conditions and outputs but does not claim complete end-to-end regeneration of those outputs.

## Included checks

1. Formal Phase A metric uncertainty, A/B rater reliability, and decision-rule
   sensitivity (A-only, B-only, A/B-consensus-only, and adjudicated-final),
   with task-cluster intervals.
2. Post-hoc interface-aligned sensitivity analysis that replaces only the 20
   formal Path assignments while retaining the other 80 historical decisions.
3. Cue-controlled comparison of profiled outputs with the system's
   intermediate-leaning default contract, including shared-output and task
   cluster analyses.
4. Paired DeepSeek versus Qwen comparison on unseen topics after the same
   Doc/Path cue-control procedure.
5. Internal consistency checks for the E2 quality totals and E3 entry-channel totals.
6. Condition-level E4 verification of 630 final records, including the
   distinction between initial success and repair-affected final coverage.
7. Integrity checks for the frozen profiles, task sets, and normalized generation conditions.
8. A dated threshold-lineage table that distinguishes the engineering title
   gate documented before formal generation from later diagnostic retest criteria.

## Run

Python 3.11 or newer is recommended. The current scripts use only the Python standard library.

```bash
python reproduce.py
python audit_package.py
```

A successful analysis run writes `generated/verification_report.json`. The expected release-candidate result is 12 passing checks, `overall_status: pass`, and `external_api_calls: 0`. The audit command writes a SHA-256 manifest and a sensitive-information scan report under `audit/`; `.git/`, `audit/`, and Python cache directories are excluded from its release-file scope. The expected result is `status: pass` with zero findings.

Run both commands from the repository root. No API key, network connection, package installation, or access to the product application is required.

## Directory layout

- `code/`: frozen analysis modules used by the reproduction script.
- `protocols/`: frozen learner profiles, formal and unseen-topic task lists, normalized generation conditions, and the final annotation/adjudication protocol.
- `protocols/threshold_lineage.csv`: provenance and interpretation of criteria
  documented at different stages; later diagnostic thresholds are not presented
  as confirmatory Phase A thresholds.
- `data/`: de-identified analysis inputs, cue-controlled final decisions,
  anonymous role-identifier ratings needed for agreement sensitivity, and
  final E2/E3 records.
- `expected/`: frozen expected summaries used for regression comparison.
- `generated/`: regenerated analyses and verification report.
- `audit/`: generated SHA-256 manifest and sensitive-information scan report; rerun the audit after any file change.

## Licenses

- `LICENSE-CODE` (MIT) applies to `reproduce.py`, `audit_package.py`, and the Python modules under `code/`.
- `LICENSE-DATA` (CC BY 4.0) applies, to the extent that the authors hold the relevant rights, to the author-created protocols, data selection and arrangement, annotations, adjudication decisions, derived results, audit reports, and documentation identified in `LICENSE-SCOPE.md`.
- Third-party material and excluded project components receive no license through this repository. In particular, the licenses do not cover the manuscript, the product-facing Web application, production agent implementations, course-material full text, raw model reasoning traces, or third-party assets.

When reusing CC BY 4.0 materials, cite the authors and repository, link to CC BY 4.0, and indicate whether changes were made. When redistributing MIT-licensed software, retain the MIT copyright and permission notice.

## Release status

The intended release model is a dedicated repository published before manuscript submission. This draft is limited to analysis-level reproduction plus an auditable record of generation conditions. A repository URL and release tag will be added only after the corresponding author approves the final release package. The copyright holder for each licensed scope is identified in the corresponding license file; the ownership statement must be rechecked if additional jointly authored materials are added before publication.

## Citation

Until a bibliographic record for the manuscript is available, cite the manuscript title, the named manuscript authors, the repository URL, and the exact release tag or commit used. Citation metadata can be added after the repository address and submission record are fixed.

## Interpretation boundary

The historical frozen Phase A analysis remains the primary recorded result.
The interface-aligned result is a post-hoc sensitivity analysis and does not
overwrite the historical files. The default-contract condition was produced
by supplying an empty learner profile to the retained system; the agents then
used their intermediate-leaning fallback contract. It is therefore not a
label-neutral absence-of-profile baseline. R1-R4, A, B, C, H1, and H2 are
anonymous workflow role identifiers and do not imply distinct individuals.

## Not included

- API credentials, authorization headers, account identifiers, or local environment files.
- Natural-person identity mappings for raters and adjudicators.
- Model reasoning traces or `reasoning_content` fields.
- Product-facing frontend/backend, authentication, database, and deployment code.
- Third-party course-material full text or other restricted content.
