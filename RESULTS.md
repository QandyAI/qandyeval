# QandyEval results, 15 November 2026 (Qwen 3.8 27B: 17 November)

Scores are 0 to 100 on "fully correct". Overall = 0.2 x core + 0.5 x hard + 0.3 x expert. Combined = 0.6 x agentic + 0.4 x text.
A hard or expert item counts only when it is fully correct in all three runs; the core tier is one run.
The hard and expert tiers are a pilot set: see "Limits of these first results" in the [README](README.md).

## Claude Fable 5.2

### Combined (0.6 x agentic + 0.4 x text)

| Domain | Core | Hard | Expert | Overall |
|---|---|---|---|---|
| Personal tax | 92 | 85 | 80 | 85 |
| Corporate tax & accounting | 94 | 90 | 90 | 91 |
| Save | 80 | 15 | 10 | 26 |
| Trading | 98 | 90 | 20 | 70 |
| Insurance | 84 | 85 | 10 | 62 |
| **All** | 90 | 73 | 42 | **67** |

### Agentic tasks only

| Domain | Core | Hard | Expert | Overall |
|---|---|---|---|---|
| Personal tax | 90 | 100 | 100 | 98 |
| Corporate tax & accounting | 94 | 100 | 100 | 99 |
| Save | 74 | 0 | 0 | 15 |
| Trading | 100 | 100 | 0 | 70 |
| Insurance | 86 | 100 | 0 | 67 |
| **All** | 90 | 80 | 40 | **70** |

### Text questions only

| Domain | Core | Hard | Expert | Overall |
|---|---|---|---|---|
| Personal tax | 94 | 62 | 50 | 65 |
| Corporate tax & accounting | 95 | 75 | 75 | 79 |
| Save | 89 | 38 | 25 | 44 |
| Trading | 94 | 75 | 50 | 71 |
| Insurance | 81 | 62 | 25 | 55 |
| **All** | 91 | 62 | 45 | **63** |

## Claude Opus 5.5

### Combined (0.6 x agentic + 0.4 x text)

| Domain | Core | Hard | Expert | Overall |
|---|---|---|---|---|
| Personal tax | 83 | 25 | 20 | 35 |
| Corporate tax & accounting | 89 | 25 | 30 | 39 |
| Save | 77 | 15 | 0 | 23 |
| Trading | 98 | 80 | 10 | 63 |
| Insurance | 78 | 15 | 10 | 26 |
| **All** | 85 | 32 | 14 | **37** |

### Agentic tasks only

| Domain | Core | Hard | Expert | Overall |
|---|---|---|---|---|
| Personal tax | 84 | 0 | 0 | 17 |
| Corporate tax & accounting | 89 | 0 | 0 | 18 |
| Save | 70 | 0 | 0 | 14 |
| Trading | 100 | 100 | 0 | 70 |
| Insurance | 81 | 0 | 0 | 16 |
| **All** | 85 | 20 | 0 | **27** |

### Text questions only

| Domain | Core | Hard | Expert | Overall |
|---|---|---|---|---|
| Personal tax | 82 | 62 | 50 | 63 |
| Corporate tax & accounting | 90 | 62 | 75 | 72 |
| Save | 88 | 38 | 0 | 36 |
| Trading | 96 | 50 | 25 | 52 |
| Insurance | 72 | 38 | 25 | 41 |
| **All** | 85 | 50 | 35 | **52** |

## Qwen 3.8 27B

Second run, 16 and 17 November 2026, after the agent-loop fixes. The first run (15 November: overall 2, core 10) is in
this file's git history.

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

## Counts behind the hard and expert tiers

| | Claude Fable 5.2 | Claude Opus 5.5 | Qwen 3.8 27B |
|---|---|---|---|
| Hard cases right in all three runs (of 5) | 4 | 1 | 0 |
| Expert cases right in all three runs (of 5) | 2 | 0 | 0 |
| Hard questions right in all three runs (of 40) | 25 | 20 | 0 |
| Expert questions right in all three runs (of 20) | 9 | 7 | 0 |

## Run details

- Claude Fable 5.2 and Claude Opus 5.5: one blind solver per shard, extra-high reasoning effort; core tier one run (587 sampled items), hard and expert tiers three runs (15 shards each). All hard and expert transcripts passed the audit.
- Qwen 3.8 27B (second run): hosted OpenAI-compatible API with the agent loop in `runners/`; 120 steps per core shard, 200 per case shard, 16,000 tokens a step, at most 4 page images per request, reasoning off (the service cannot cap it), temperature 0, seeds 1, 2 and 3 for the three hard and expert runs; text questions with the working written in the reply, 6,000 tokens. 18 of its 67 core shards and 8 of its 30 case shards stopped at the step limit (27 of 30 in the first run). The run was paused for 18 hours; the 18 shards it cut off were restarted from clean copies.
- Qwen 3.8 27B (second run), text replies cut before their answer: 55 of 369 in the core tier (12 at the 6,000-token limit, 41 with the stream ended, most after about 30 minutes, 2 stopped without an answer) and 79 of 180 in the three hard and expert runs (45 at the token limit, 34 with the stream ended). For these the runner asks once for the answer in a short second request; 4 of the 55 core answers were fully right, against 87 of the 314 complete ones.
- Letters and advice answers: two independent judges with the same prompt (`docs/JUDGE_PROMPT.md`); both gave the same tier scores for every model. For Qwen 3.8 27B's second run they differ on one core Save memo, which the judge of record (Claude Fable 5.2) did not pass and the second judge (Claude Opus 5.5) did: its core Save score is 20 with the judge of record, as shown, and 23 with the second judge; no tier or overall figure changes.
- 9 live paper-trading items in the core sample are not run yet and are left out of every score.
