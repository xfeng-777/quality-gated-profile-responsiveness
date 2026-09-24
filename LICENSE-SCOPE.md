# License Scope

Copyright (c) 2026 Yixin Tian.

This repository uses separate licenses for software and research materials.

## MIT License

`LICENSE-CODE` applies to the following software files:

- `reproduce.py`
- `audit_package.py`
- all `.py` files under `code/`

## CC BY 4.0

`LICENSE-DATA` applies, to the extent that the authors hold the relevant
rights, to the author-created selection, arrangement, annotations, labels,
adjudication decisions, derived statistics, and documentation in:

- `README.md`
- all release files under `protocols/`
- all release files under `data/`
- all release files under `expected/`
- all release files under `generated/`
- the audit reports under `audit/`

The source code remains under the MIT License even when it is stored next to
CC BY 4.0 materials.

The `data/cue_control/` directory contains de-identified role-identifier
ratings and final adjudicated decisions. It does not contain natural-person
role mappings, candidate-to-condition blinding maps, or model reasoning
traces.

The `data/revision_doc_cue_control/` directory contains anonymized D1/D2 role
ratings, final Doc decisions, and derived sensitivity statistics. It excludes
candidate texts, private truth/randomization mappings, pre-recovery files, and
natural-person role mappings. The `data/revision_surface_cues/` directory
contains derived feature tables and exploratory analysis summaries; it does
not contain the source model-output texts.

## Administrative Files

`.gitignore`, `LICENSE-CODE`, `LICENSE-DATA`, and this scope notice are
repository-administration files. The license texts retain their own terms.

## Exclusions and Third-Party Material

The licenses in this repository do not apply to material that is not included
in the repository. In particular, they do not license the manuscript or its
published version, the product-facing Web application, production agent
implementations, credentials, identity mappings, model reasoning traces,
course-material full text, or other third-party licensed assets.

Some records contain factual metadata or outputs returned by third-party
services, including URLs, bibliographic facts, OCR topics, and ASR
transcriptions. CC BY 4.0 applies to the authors' selection, arrangement,
annotation, and derived analysis of those records only to the extent the
authors have rights to license them. No additional rights in third-party
content, platform output, trademarks, privacy rights, or database rights are
granted by this repository.

No raw audio, image, course-material full text, or model reasoning trace is
included in the current release package.
