# Final Annotation and Adjudication Protocol

## Scope

This document records the procedures actually used for the reported formal
Phase A and unseen-topic analyses. It replaces early planning documents that
contained endpoints and statistical tests not used in the final analysis.
All rater and reviewer identifiers are anonymous role identifiers and are not
linked to natural-person identities in this release.

Two evaluation branches were conducted separately:

1. output-level domain-quality review; and
2. blind learner-profile matching.

The branches were merged only during final statistical analysis. A triplet
could count as a quality-gated full match only when the final profile ordering
was fully correct and all three outputs passed the domain-quality floor.

## Rater and Reviewer Background

All individuals who performed profile matching, adjudication, or
course-specific domain-quality review were computer science undergraduates
with relevant coursework. The role identifiers A, B, C, H1, and H2 are used
throughout the remainder of this protocol without repeating this background.

## Frozen Learner Profiles

The three profiles are stored under `protocols/profiles/`. Only four
knowledge-background fields--math, programming, statistics, and subject-prior
knowledge--vary across P1, P2, and P3. English proficiency and all fields for cognitive style, goals,
weaknesses, pace, resource preferences, and employment skills are held
constant. The labels shown to raters were beginner, intermediate, and
advanced; the P1/P2/P3 mapping was hidden during scoring.

## Blind Triplet Matching

Each row contained three anonymized outputs, X, Y, and Z, generated for the
same course, topic, agent, and repeat. A rater assigned each candidate exactly
once to beginner, intermediate, or advanced and recorded:

- `beginner_candidate`: X, Y, or Z;
- `intermediate_candidate`: X, Y, or Z;
- `advanced_candidate`: X, Y, or Z;
- `confidence`: low, medium, or high;
- `indistinguishable`: yes or no; and
- optional notes.

Even when outputs were marked indistinguishable, the rater supplied the best
available complete ordering. Candidate order was randomized, and raters were
not permitted to view private mappings, other raters' answers, or adjudicated
results for the batch they were scoring.

The principal cues were prerequisite assumptions, terminology support,
scaffolding intensity, cognitive complexity, task openness, explanatory
depth, and engineering or research depth. Agent-specific cues were:

- Doc: conceptual depth, terminology support, abstraction, examples, and
  self-check tasks;
- Quiz: question difficulty, distractor and reasoning complexity, and
  feedback depth;
- Code: implementation complexity, dependencies, boundary handling, tests,
  explanations, templates, and autonomy requirements;
- Reading: resource level, sequence, and recommendation rationale; and
- Path: prerequisites, node-level support, activity difficulty, diagnostic
  work, debugging, and integrative tasks.

Length, code-line count, node count, and candidate label were not sufficient
on their own to establish a learner level.

### Formal Phase A

Raters A and B each completed five training triplets,
with one training item per resource agent. Training records were excluded
from analysis. A and B then independently scored 100 formal triplets each.

A triplet entered adjudication if at least one of the following occurred:

- A and B provided different complete assignments;
- either rater marked the triplet indistinguishable;
- either rater reported low confidence;
- at least one output failed the quality floor; or
- at least one output contained a major domain error.

Fifty-three triplets entered the first adjudication pass under identifier H2.
H2 was the same person as rater A and re-examined the triggered anonymized
triplets using the recorded rationales and quality-gating information. The 11
items that remained low-confidence were escalated to reviewer H1, who had not
performed A/B initial scoring for this batch. Final data
retain 42 H2 decisions and 11 H1 decisions. Adjudication did not overwrite the
original A/B records, which remain the basis of the agreement analysis.

### Unseen-Topic Cross-Model Batches

Raters A, B, and C independently scored 30 triplets per
profiled model batch (ten tasks by three agents). The DeepSeek and Qwen
batches were scored separately under the same criteria. Triggered items were
adjudicated by H1, who had not initially scored the corresponding batch. No
rater or adjudicator accessed the private profile mapping while working on
the relevant batch.

### Profiled-versus-Default-Contract Preference

For each target profile, raters compared an anonymized profiled output with an
anonymized default-contract output for the same task and agent. The latter was
generated from an empty learner profile, which triggered the system's
intermediate-leaning fallback contract; it was not a level-neutral baseline. Each rater
selected candidate A, candidate B, or TIE and recorded confidence and notes.
Preference was based on fit to the disclosed target profile rather than
length or factual quality alone. Initial disagreement was resolved by an
independent blind adjudication. The final analysis applied bilateral quality
gating: a preference pair entered the quality-gated comparison only when both
outputs passed the domain-quality floor.

## Domain-Quality Review

Each course was assigned to one course reviewer. Reviewers did not see profile IDs or
target levels. Each output received the following fields:

- `factual_correctness`: pass, minor_error, or major_error;
- `relevance`: yes or no;
- `answer_consistency`: yes, no, or na;
- `executable_or_structurally_valid`: yes, no, or na;
- `quality_floor_pass`: yes or no;
- a required reason for major errors or quality-floor failures; and
- optional notes.

Code review used sandbox results or local semantic oracles where applicable.
For resources without a unique answer, `answer_consistency` could be `na`.
A major factual error or irrelevance required a failed quality floor. Minor
errors were judged according to whether they compromised the primary learning
objective rather than by automatic field linkage alone.

Reviewers could consult an LLM and reliable public sources to locate or verify
uncertain technical concepts. Textbooks, official documentation, standards,
and original papers were preferred for consequential decisions. The human
reviewer remained responsible for every final label.

## Reported Profile-Matching Measures

- Full match (FM): all three candidates were assigned to their true profiles.
- Pairwise order accuracy (POA): the proportion of the three profile pairs in
  the correct order.
- Extreme correct (EC): P1 and P3 were correctly ordered.
- Extreme reversal (ER): P1 and P3 were reversed.
- Quality-gated full match (QG-FM): FM with all three outputs passing the
  domain-quality floor.
- Agreement: full-assignment agreement and Cohen's kappa for A/B; the
  unseen-topic supplement additionally reports pairwise kappas, three-rater
  unanimity, and Fleiss' kappa.

The released scoring tables contain the de-identified initial and final
records needed to recompute these measures. Private mappings used during live
blind scoring are not released as private operational packets; the completed
post-experiment tables contain the truth fields required for reproducibility.

## Direct-Cue Control and Interface Alignment

A post-hoc sensitivity analysis removed direct profile-level statements from
selected Doc and Path materials. Path raters received only the fields shown in
the student interface. Four role identifiers (R1-R4) were used across the
rerating workflow. Two ratings were collected per formal Path triplet, three
ratings per unseen-topic or contract-retest triplet, and two ratings per
profiled-versus-default-contract pair. Triggered disagreements were resolved
by independent blind adjudication. The released final decisions are the
inferential units; individual rating actions describe workflow and agreement,
not additional samples.

For the formal Phase A sensitivity estimate, only the 20 Path decisions were
replaced. Reading, Quiz, Doc, Code, quality-gate decisions, and the historical
A/B reliability analysis were retained. The resulting hybrid agreement is
descriptive because one fixed pair of individuals did not rate all 100 units.
