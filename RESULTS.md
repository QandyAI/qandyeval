# QandyEval results, 17 November 2026

Scores are 0 to 100 on "fully correct". Overall = 0.2 x core + 0.5 x hard + 0.3 x expert. Combined = 0.6 x agentic + 0.4 x text.
A hard or expert item counts only when it is fully correct in all three runs; the core tier is one run.

The hard and expert tiers below are the rebuilt set: 20 cases (two per domain at each level) and 60 questions, on cases
and questions no run had seen. They replace the pilot set of the first results (15 November), which are kept at the end
of this file. Read "Limits of these results" in the [README](README.md) before quoting any figure.

## Claude Fable 5.2

### Combined (0.6 x agentic + 0.4 x text)

| Domain | Core | Hard | Expert | Overall |
|---|---|---|---|---|
| Personal tax | 92 | 55 | 20 | 52 |
| Corporate tax & accounting | 94 | 60 | 30 | 58 |
| Save | 80 | 20 | 30 | 35 |
| Trading | 98 | 90 | 30 | 74 |
| Insurance | 84 | 55 | 50 | 59 |
| **All** | 90 | 56 | 32 | **56** |

### Agentic tasks only

| Domain | Core | Hard | Expert | Overall |
|---|---|---|---|---|
| Personal tax | 90 | 50 | 0 | 43 |
| Corporate tax & accounting | 94 | 50 | 0 | 44 |
| Save | 74 | 0 | 50 | 30 |
| Trading | 100 | 100 | 0 | 70 |
| Insurance | 86 | 50 | 50 | 57 |
| **All** | 90 | 50 | 20 | **49** |

### Text questions only

| Domain | Core | Hard | Expert | Overall |
|---|---|---|---|---|
| Personal tax | 94 | 62 | 50 | 65 |
| Corporate tax & accounting | 95 | 75 | 75 | 79 |
| Save | 89 | 50 | 0 | 43 |
| Trading | 94 | 75 | 75 | 79 |
| Insurance | 81 | 62 | 50 | 62 |
| **All** | 91 | 65 | 50 | **66** |

## Claude Opus 5.5

### Combined (0.6 x agentic + 0.4 x text)

| Domain | Core | Hard | Expert | Overall |
|---|---|---|---|---|
| Personal tax | 83 | 55 | 20 | 50 |
| Corporate tax & accounting | 89 | 30 | 30 | 42 |
| Save | 77 | 20 | 30 | 34 |
| Trading | 98 | 80 | 20 | 66 |
| Insurance | 78 | 25 | 20 | 34 |
| **All** | 85 | 42 | 24 | **45** |

### Agentic tasks only

| Domain | Core | Hard | Expert | Overall |
|---|---|---|---|---|
| Personal tax | 84 | 50 | 0 | 42 |
| Corporate tax & accounting | 89 | 0 | 0 | 18 |
| Save | 70 | 0 | 50 | 29 |
| Trading | 100 | 100 | 0 | 70 |
| Insurance | 81 | 0 | 0 | 16 |
| **All** | 85 | 30 | 10 | **35** |

### Text questions only

| Domain | Core | Hard | Expert | Overall |
|---|---|---|---|---|
| Personal tax | 82 | 62 | 50 | 63 |
| Corporate tax & accounting | 90 | 75 | 75 | 78 |
| Save | 88 | 50 | 0 | 42 |
| Trading | 96 | 50 | 50 | 59 |
| Insurance | 72 | 62 | 50 | 61 |
| **All** | 85 | 60 | 45 | **60** |

## Counts behind the rebuilt hard and expert tiers

| | Claude Fable 5.2 | Claude Opus 5.5 |
|---|---|---|
| Hard cases right in all three runs (of 10) | 5 | 3 |
| Expert cases right in all three runs (of 10) | 2 | 1 |
| Hard questions right in all three runs (of 40) | 26 | 24 |
| Expert questions right in all three runs (of 20) | 10 | 9 |
| Share of answer fields right in hard cases (partial credit, not the score) | 96 | 92 |
| Share of answer fields right in expert cases (partial credit, not the score) | 94 | 86 |

A case counts only when every deliverable is right in all three runs, so a case missed by one field counts as missed.

## Qwen 3.8 27B (core tier, and the pilot hard and expert tiers)

**Not run on the rebuilt hard and expert tiers.** The tables below are its core tier and its result on the pilot hard
and expert tiers (second run, 16 and 17 November 2026, after the agent-loop fixes), where it had no hard or expert item
right in all three runs. The first run (15 November: overall 2, core 10) is in this file's git history.

### Combined (0.6 x agentic + 0.4 x text)

| Domain | Core | Hard | Expert | Overall |
|---|---|---|---|---|
| Personal tax | 18 | 0 | 0 | 4 |
| Corporate tax & accounting | 19 | 0 | 0 | 4 |
| Save | 20 | 0 | 0 | 4 |
| Trading | 36 | 0 | 0 | 7 |
| Insurance | 29 | 0 | 0 | 6 |
| **All** | 24 | 0 | 0 | **5** |

### Agentic tasks only

| Domain | Core | Hard | Expert | Overall |
|---|---|---|---|---|
| Personal tax | 19 | 0 | 0 | 4 |
| Corporate tax & accounting | 18 | 0 | 0 | 4 |
| Save | 0 | 0 | 0 | 0 |
| Trading | 45 | 0 | 0 | 9 |
| Insurance | 35 | 0 | 0 | 7 |
| **All** | 23 | 0 | 0 | **5** |

### Text questions only

| Domain | Core | Hard | Expert | Overall |
|---|---|---|---|---|
| Personal tax | 16 | 0 | 0 | 3 |
| Corporate tax & accounting | 20 | 0 | 0 | 4 |
| Save | 50 | 0 | 0 | 10 |
| Trading | 23 | 0 | 0 | 5 |
| Insurance | 20 | 0 | 0 | 4 |
| **All** | 25 | 0 | 0 | **5** |

## Run details

- Claude Fable 5.2 and Claude Opus 5.5: one blind solver per shard, extra-high reasoning effort; core tier one run (587 sampled items), hard and expert tiers three runs of 25 shards each. All 75 hard and expert transcripts of each model passed the audit.
- Letters and advice answers: two independent judges with the same prompt (`docs/JUDGE_PROMPT.md`), Claude Fable 5.2 as judge of record and Claude Opus 5.5 as cross-check; both gave identical tier scores for both models on the rebuilt tiers.
- Qwen 3.8 27B (second run, core tier and pilot tiers): hosted OpenAI-compatible API with the agent loop in `runners/`; 120 steps per core shard, 200 per case shard, 16,000 tokens a step, at most 4 page images per request, reasoning off (the service cannot cap it), temperature 0, seeds 1, 2 and 3 for the three hard and expert runs; text questions with the working written in the reply, 6,000 tokens. 18 of its 67 core shards and 8 of its 30 case shards stopped at the step limit (27 of 30 in the first run). The run was paused for 18 hours; the 18 shards it cut off were restarted from clean copies.
- Qwen 3.8 27B (second run), text replies cut before their answer: 55 of 369 in the core tier (12 at the 6,000-token limit, 41 with the stream ended, most after about 30 minutes, 2 stopped without an answer) and 79 of 180 in the three hard and expert runs (45 at the token limit, 34 with the stream ended). For these the runner asks once for the answer in a short second request; 4 of the 55 core answers were fully right, against 87 of the 314 complete ones.
- For Qwen 3.8 27B's second run the two judges differ on one core Save memo, which the judge of record did not pass and the second judge did: its core Save score is 20 with the judge of record, as shown, and 23 with the second judge; no tier or overall figure changes.
- 9 live paper-trading items in the core sample are not run yet and are left out of every score.

## First results on the pilot hard and expert tiers (15 November 2026)

The pilot set had 10 cases (one per domain at each level) and 60 questions, tuned over several rounds on the answers of
both Claude models. It is replaced by the rebuilt set above; these figures are kept for the record. The full pilot
tables are in this file's git history.

### Claude Fable 5.2, pilot tiers

Combined (0.6 x agentic + 0.4 x text):

| Domain | Core | Hard | Expert | Overall |
|---|---|---|---|---|
| Personal tax | 92 | 85 | 80 | 85 |
| Corporate tax & accounting | 94 | 90 | 90 | 91 |
| Save | 80 | 15 | 10 | 26 |
| Trading | 98 | 90 | 20 | 70 |
| Insurance | 84 | 85 | 10 | 62 |
| **All** | 90 | 73 | 42 | **67** |

### Claude Opus 5.5, pilot tiers

Combined (0.6 x agentic + 0.4 x text):

| Domain | Core | Hard | Expert | Overall |
|---|---|---|---|---|
| Personal tax | 83 | 25 | 20 | 35 |
| Corporate tax & accounting | 89 | 25 | 30 | 39 |
| Save | 77 | 15 | 0 | 23 |
| Trading | 98 | 80 | 10 | 63 |
| Insurance | 78 | 15 | 10 | 26 |
| **All** | 85 | 32 | 14 | **37** |

On the pilot set Claude Fable 5.2 had 4 of 5 hard cases and 2 of 5 expert cases right in all three runs, Claude Opus 5.5
1 and 0. Two keys of the pilot were found at fault after publication, and the figures above are left as graded:

- A notice date in the expert Hong Kong shop claim was unsupported. Claude Fable 5.2 missed only that date; without it
  its pilot overall would have been about 70.
- The VAT cut-off in the French year-end case put a deduction on the January return; the official guidance puts it on
  the December return. Claude Fable 5.2 answered as the key at both levels; with the key corrected its pilot overall
  would have been about 58 (worked out by arithmetic, not regraded).

The rebuilt tiers drop the date and correct the cut-off.
