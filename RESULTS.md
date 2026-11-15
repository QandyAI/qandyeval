# QandyEval results, 15 November 2026

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

### Combined (0.6 x agentic + 0.4 x text)

| Domain | Core | Hard | Expert | Overall |
|---|---|---|---|---|
| Personal tax | 8 | 0 | 0 | 2 |
| Corporate tax & accounting | 10 | 0 | 0 | 2 |
| Save | 4 | 0 | 0 | 1 |
| Trading | 9 | 0 | 0 | 2 |
| Insurance | 16 | 0 | 0 | 3 |
| **All** | 10 | 0 | 0 | **2** |

### Agentic tasks only

| Domain | Core | Hard | Expert | Overall |
|---|---|---|---|---|
| Personal tax | 10 | 0 | 0 | 2 |
| Corporate tax & accounting | 12 | 0 | 0 | 2 |
| Save | 0 | 0 | 0 | 0 |
| Trading | 10 | 0 | 0 | 2 |
| Insurance | 21 | 0 | 0 | 4 |
| **All** | 12 | 0 | 0 | **2** |

### Text questions only

| Domain | Core | Hard | Expert | Overall |
|---|---|---|---|---|
| Personal tax | 5 | 0 | 0 | 1 |
| Corporate tax & accounting | 6 | 0 | 0 | 1 |
| Save | 11 | 0 | 0 | 2 |
| Trading | 8 | 0 | 0 | 2 |
| Insurance | 9 | 0 | 0 | 2 |
| **All** | 7 | 0 | 0 | **2** |

## Counts behind the hard and expert tiers

| | Claude Fable 5.2 | Claude Opus 5.5 | Qwen 3.8 27B |
|---|---|---|---|
| Hard cases right in all three runs (of 5) | 4 | 1 | 0 |
| Expert cases right in all three runs (of 5) | 2 | 0 | 0 |
| Hard questions right in all three runs (of 40) | 25 | 20 | 0 |
| Expert questions right in all three runs (of 20) | 9 | 7 | 0 |

## Run details

- Claude Fable 5.2 and Claude Opus 5.5: one blind solver per shard, extra-high reasoning effort; core tier one run (587 sampled items), hard and expert tiers three runs (15 shards each). All hard and expert transcripts passed the audit.
- Qwen 3.8 27B: hosted OpenAI-compatible API with the agent loop in `runners/`; 120 steps per core shard, 200 per case shard, 6,000 tokens a step, at most 4 page images per request. 27 of its 30 case shards stopped at the step limit.
- Letters and advice answers: two independent judges with the same prompt (`docs/JUDGE_PROMPT.md`); both gave the same tier scores for every model.
- 9 live paper-trading items in the core sample are not run yet and are left out of every score.
