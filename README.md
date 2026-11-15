# QandyEval

**A benchmark for financial AI agents that have to finish the work, not just answer questions about it.**

QandyEval tests whether a model can do the jobs a personal financial agent is trusted with: fill in the official tax
form, file the insurance claim, close the books, cancel the contract in time, place the order within the rules. It
covers five domains in nine jurisdictions, and every answer is graded against an audited answer key.

It is built by [QANDY](https://qandy.ai), the company behind QANDY SAVE and the QANDY 2.0 model.
Results are also shown at [qandy.ai/qandyeval](https://qandy.ai/qandyeval/).

## First results (15 November 2026)

Overall score, 0 to 100. Higher is better.

| Domain | Claude Fable 5.2 | Claude Opus 5.5 | Qwen 3.8 27B |
|---|---|---|---|
| Personal tax | 85 | 35 | 2 |
| Corporate tax & accounting | 91 | 39 | 2 |
| Save | 26 | 23 | 1 |
| Trading | 70 | 63 | 2 |
| Insurance | 62 | 26 | 3 |
| **Overall** | **67** | **37** | **2** |

By tier:

| Tier (weight) | Claude Fable 5.2 | Claude Opus 5.5 | Qwen 3.8 27B |
|---|---|---|---|
| Core (20%) | 90 | 85 | 10 |
| Hard (50%) | 73 | 32 | 0 |
| Expert (30%) | 42 | 14 | 0 |

Full tables, split into agentic tasks and text questions, are in [RESULTS.md](RESULTS.md). Read the
[limits of these numbers](#limits-of-these-first-results) before quoting them. QANDY 2.0 27B results will follow.

## What is tested

**Five domains**, always reported separately:

| Domain | Examples of the work |
|---|---|
| Personal tax | Payroll withholding, annual returns, residency, investment income, pensions, filling the official return |
| Corporate tax & accounting | Taxable-income bridges, VAT and sales tax returns, withholding and treaties, incentives, bookkeeping and period close |
| Save | Finding recurring charges, comparing offers, cancellation rights and deadlines, refunds and compensation, switching providers |
| Trading | Order and market rules, costs and after-tax profit, product access, margin and risk, crypto regimes, strategy code |
| Insurance | Applications, coverage decisions, claim forms and settlements, premium rating, public health reimbursement |

**Nine jurisdictions**: United States, European Union (Germany, France, Spain, the Netherlands and Italy in depth),
United Kingdom, Mainland China, Japan, South Korea, Hong Kong SAR, Taiwan and Canada. Items are written in the local
language where the work is done in it.

**Two kinds of item**, scored apart and then combined:

- **Agentic tasks (60% of a tier).** The model works as an agent in a folder of documents and simulated systems:
  official PDF forms to fill field by field, mock web portals and desktop filing programs, a simulated ledger, a
  simulated workspace with mail and files, scanned invoices and statements to read, and programs to write.
- **Text questions (40% of a tier).** One question, one structured answer, plus advice answers marked by judges
  against fixed criteria.

**Three tiers**, with weights fixed in advance:

| Tier | Weight | What it is |
|---|---|---|
| Core | 20% | 5,932 frozen items (4,169 in the test split). A run answers a sample of 587: 369 text items and 209 agentic items; 9 live paper-trading items are not yet run. |
| Hard | 50% | Closed-book client cases and tricky questions. A case is one client's whole file: 25 to 120 documents, several linked deliverables, traps, and a letter to the client. |
| Expert | 30% | The same form as hard, with harder rules, more traps and cross-border facts. |

In the hard and expert tiers the model gets figures and conventions only: no rule notes and no calculator. The current
hard and expert set is a pilot of 10 cases (one per domain at each level) and 60 questions.

## How answers are scored

- **Fully correct or not.** An item counts only when every answer field is right. A case counts only when every one of
  its deliverables is right, including the letter. Partial credit is reported in the detailed reports but is not the
  headline score.
- **Right every time.** A hard or expert item counts only when it is fully correct in all three runs.
- **Tier score** = 0.6 × agentic + 0.4 × text.
- **Overall** = 0.2 × core + 0.5 × hard + 0.3 × expert.
- Scores are 0 to 100. Per-tier tables carry a 95% range; the weighted overall does not.

## Where the answer keys come from

No answer key is written by a language model. Each key is computed by a deterministic calculation engine built from
primary sources (statutes, regulations, official forms, tables and worked examples published by tax authorities,
regulators and insurers' standard-terms bodies). Every engine is then audited by an independent agent that recomputes
a sample of keys from the primary sources without using the engine. Where a source does not settle a point, such as a
rounding rule, items are generated so that the point never decides an answer.

Every item states the date whose law applies. Forms and portals are unbranded mock versions of the real ones, and all
accounts, people, companies and reference numbers are simulated. Nothing is submitted to a real authority or insurer.

## How a run works

1. **Freeze.** The item set and the harness code are hashed. A run refuses a set whose data or code has changed.
2. **Blind solving.** The run is split into shards. One solver works on each shard, inside that shard's folder only,
   under the rules in [docs/SOLVER_PROMPT.md](docs/SOLVER_PROMPT.md): no web, no code, no calculator, no reading
   outside the folder. The only network access is the run's own simulated systems on localhost.
3. **Transcript audit.** Every command a solver ran is checked afterwards. A shard whose solver left its folder, used
   the web, or ran code or a calculator is invalid.
4. **Grading.** Forms, system states and structured answers are graded by code against the keys. Letters and advice
   answers go to two independent judges with the prompt in [docs/JUDGE_PROMPT.md](docs/JUDGE_PROMPT.md); the judges
   see the answer and the criteria only.
5. **Report.** Scores by domain, by tier, and by agentic and text items.

How each model was run for the results above:

| | Claude Fable 5.2, Claude Opus 5.5 | Qwen 3.8 27B |
|---|---|---|
| Access | Agent with file and shell tools, extra-high reasoning effort | Hosted OpenAI-compatible API, driven by the agent loop in [`runners/`](runners/) |
| Limits | None beyond the run rules | 120 steps per core shard, 200 per case, 6,000 tokens a step, at most 4 page images per request (a limit of the service) |
| Core tier | One run | One run |
| Hard and expert | Three runs | Three runs |

All 45 hard and expert solver transcripts of each Claude model passed the audit. Both judges gave the same tier scores for every model.

## Limits of these first results

- **The hard and expert tiers are a pilot.** Their cases and questions were tuned on the answers of Claude Opus 5.5 and
  Claude Fable 5.2 over several rounds, with five cases at each level. They will be measured again on fresh cases that no
  calibration run has seen. Expect the numbers to move.
- **Small sample at the top.** Ten cases decide 60% of the hard and expert tiers. One case is worth several points of
  the overall score.
- **The core tier is one run per model.**
- **Same-family effects.** The items were written with the help of a model from the same family as two of the models
  tested, and the judge of record is one of the models tested. A second judge from a different model cross-checked
  every verdict and reached identical tier scores.
- **Qwen 3.8 27B hit its step limit** on 27 of 30 case shards and saw at most four page images at a time. Its score
  reflects that setup as well as the model.

## What is in this repository, and what is not

| Here | Held back |
|---|---|
| This description of the benchmark and its scoring | The frozen test items and their answer keys |
| [RESULTS.md](RESULTS.md): the result tables | The calculation engines and item generators |
| [samples/](samples/): ten example items with answers, from the non-test split | The hard and expert cases |
| [docs/](docs/): the exact solver and judge prompts | Solver transcripts and judge verdicts |
| [runners/](runners/): the agent loop used for models behind an OpenAI-compatible API | The grading harness |

The test items stay private so that they do not end up in training data. If you build models for financial work and
want yours evaluated, write to hello@qandy.ai.

## Roadmap

- QANDY 2.0 27B on the same tests.
- The hard and expert tiers rebuilt on fresh cases, with more case types per domain.
- Three runs of the core tier for every model.
- Live paper trading.

© 2026 QANDY. All rights reserved unless a licence file says otherwise.
