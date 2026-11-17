# QandyEval

**A benchmark for financial AI agents that have to finish the work, not just answer questions about it.**

QandyEval tests whether a model can do the jobs a personal financial agent is trusted with: fill in the official tax
form, file the insurance claim, close the books, cancel the contract in time, place the order within the rules. It
covers five domains in nine jurisdictions, and every answer is graded against an audited answer key.

It is built by [QANDY](https://qandy.ai), the company behind QANDY SAVE and the QANDY 2.0 model.
Results are also shown at [qandy.ai/qandyeval](https://qandy.ai/qandyeval/).

## Results (17 November 2026)

Overall score, 0 to 100. Higher is better.

| Domain | Claude Fable 5.2 | Claude Opus 5.5 | Qwen 3.8 27B* |
|---|---|---|---|
| Personal tax | 52 | 50 | 4 |
| Corporate tax & accounting | 58 | 42 | 4 |
| Save | 35 | 34 | 4 |
| Trading | 74 | 66 | 7 |
| Insurance | 59 | 34 | 6 |
| **Overall** | **56** | **45** | **5** |

By tier:

| Tier (weight) | Claude Fable 5.2 | Claude Opus 5.5 | Qwen 3.8 27B* |
|---|---|---|---|
| Core (20%) | 90 | 85 | 24 |
| Hard (50%) | 56 | 42 | 0 |
| Expert (30%) | 32 | 24 | 0 |

\* Qwen 3.8 27B has not been run on the rebuilt hard and expert tiers. Its figures are its core tier and its result on
the pilot hard and expert tiers, where it had no item right in all three runs.

The hard and expert tiers were rebuilt on fresh cases and replace the pilot set of the first results (15 November),
on which Claude Fable 5.2 had 67 and Claude Opus 5.5 had 37. Full tables, split into agentic tasks and text questions,
and the first results are in [RESULTS.md](RESULTS.md). Read the [limits of these numbers](#limits-of-these-results)
before quoting them. QANDY 2.0 27B results will follow.

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
hard and expert set has 20 cases (two per domain at each level) and 60 questions (40 hard, 20 expert).

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
| Limits | None beyond the run rules | 120 steps per core shard, 200 per case, 16,000 tokens a step, at most 4 page images per request (a limit of the service); reasoning off, because the service cannot cap it; text questions answered with the working written in the reply |
| Core tier | One run | One run |
| Hard and expert | Three runs on the rebuilt tiers | Three runs on the pilot tiers; not run on the rebuilt tiers |

All 75 hard and expert solver transcripts of each Claude model passed the audit. Both judges gave the same tier scores for
every model (for Qwen 3.8 27B's second run they differ on one core memo, which moves no figure in the tables above).

## Limits of these results

- **The hard and expert tiers are tuned against the two Claude models.** Their cases were hardened on rules that Claude
  Opus 5.5 and Claude Fable 5.2 got wrong in earlier rounds, so they are harder for these two models than a set
  written without looking at any model would be. The cases and questions measured here are on draws no run had seen.
- **Small sample at the top.** Twenty cases decide 60% of the hard and expert tiers. One hard case is worth 3 points of
  the overall score, one expert case about 2. A case missed by a single field counts as missed.
- **The core tier is one run per model.**
- **Same-family effects.** The items were written with the help of a model from the same family as two of the models
  tested, and the judge of record is one of the models tested. A second judge from a different model cross-checked
  every verdict and reached identical tier scores.
- **Known limits of the keys.** Before the rebuilt tiers were frozen, every case and question key was audited again
  against official sources, and what the audit found was corrected or settled by changing the facts. What remains:
  nine Ontario accident-benefit rules behind one insurance question family were read at the official source on 9
  November but could not be read a second time in the last round, because the site refused automated access; one
  Korean corporate-tax point rests on a court ruling, with no tax-authority text on today's wording read; and in three
  cases a convention given to the solver departs from the law on purpose, with the keys following the convention.
- **One core-tier table is out of date.** A table of Hong Kong profits-tax return due dates in the core tier predates
  two circulars of July and October 2026. It is listed for correction; the core scores are left as graded.
- **Qwen 3.8 27B was not run on the rebuilt hard and expert tiers.** Its hard and expert figures (0 and 0) are from the
  pilot tiers, so its overall is not measured on the same hard and expert set as the two Claude models.
- **The first results used a pilot set, and two of its keys were later found at fault.** A notice date in the expert
  Hong Kong shop claim was unsupported, which counted against Claude Fable 5.2; a VAT cut-off in the French year-end
  case was keyed on the wrong return, which counted in its favour. The rebuilt tiers correct both. See the end of
  [RESULTS.md](RESULTS.md).
- **Qwen 3.8 27B was run a second time** on 16 and 17 November, after fixes to the agent loop: the model is now told its
  step limit and which pages left view, and a reply cut at the token limit is recovered. It had 16,000 tokens a step
  instead of 6,000, and wrote its working in the reply for text questions. Its overall went from 2 to 5 and its core
  tier from 10 to 24. It still stopped at its step limit on 18 of 67 core shards and 8 of 30 case shards (27 of 30 the
  first time), saw at most four page images at a time and ran with reasoning off, so its score reflects that setup as
  well as the model. The run was paused for 18 hours; the 18 shards it cut off were restarted from clean copies.
- **Some of Qwen 3.8 27B's text replies were cut.** In its second run a text reply had 6,000 tokens, and a reply that
  was still streaming after about 30 minutes ended without a finish reason (the service was slow; whether the runner's
  or the service's time limit ended it was not determined). 55 of the 369 core text replies and 79 of the 180 hard and
  expert question replies did not reach their own answer this way (12 and 45 of them at the token limit). The runner
  then asks once, in a short second request, for the answer from the working so far. 4 of those 55 core answers were
  fully right, against 87 of the 314 complete ones. No hard or expert question was right in all three runs either way.

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
- Qwen 3.8 27B on the rebuilt hard and expert tiers.
- More case types per domain in the hard and expert tiers.
- Three runs of the core tier for every model.
- Live paper trading.

© 2026 QANDY. All rights reserved unless a licence file says otherwise.
