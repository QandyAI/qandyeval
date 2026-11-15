# Judge prompt (rubric items)

`qandy-eval grade-run` writes one queue per run, `queue_<digest>.json`, holding every advice answer and workspace memo of
that run that awaits a judge (the command prints which file belongs to which run). The queues go to `REPORT_DIR/judge/`,
or with `--judge-dir DIR` to a folder of your choice: name one that holds nothing else, away from the report. Give a
judge the text below the line with `{QUEUE}` replaced by that file's absolute path and `{OUT}` by where its verdicts go.
Then grade again with `--judgments` naming those files in the order of `--answers`.

For the person or agent launching the judge:
- The judge is a separate agent from every solver, and gets the queue file only: no kit, no repository, no report. The
  report folder holds expected values, so use `--judge-dir`, or copy the queue out of the report folder before you hand
  it over.
- Never tell it which model wrote the answers or what any other judge decided. The queue names no model; keep model
  names out of the file paths you give it and out of run ids as well (the queue carries the run id, k1 or k2, so that
  the verdicts can be tied to their run).
- Use the same judge model and this same prompt for every model under test, so the scores compare.
- A verdicts file is bound to one run: it has to repeat the queue's `run` and `digest`. `grade-run` refuses a file that
  belongs to another run, and a file whose answers have changed since they were judged. So one file per run, in the
  order of `--answers`.
- The total is worked out by `grade-run` from the judge's marks (met weight plus penalties, over the total weight). An item
  passes at 0.8 and only if no core criterion scored 0. The judge is not told the weights.
- A verdict is used only if it is complete: an object with a mark of 0, 0.5 or 1 (a number) for every criterion and
  `true` or `false` for every penalty. Anything else (a criterion or a penalty left out, a mark of 2, a mark or a
  penalty written as text, a bare score) is listed in the report with its reason, and the item stays in the queue.
- An item that still awaits a judge in any one run is left out of every score for all runs, and listed. Judge every run
  before you quote a score that includes advice.
- When grading is repeated, the new queue holds only the entries still without a usable verdict, under the same `run`
  and `digest`: add the judge's new verdicts to that run's file.

---

You are grading written answers to finance questions against fixed criteria. Read the file

    {QUEUE}

and nothing else. It is one JSON object: `run` and `digest` (copy both into your output exactly as they are) and
`entries`, a list. Each entry has:
- `id`
- `question`: what the person asked (for a memo: the task its writer was given)
- `as_of`: the date whose law applies, and `language`
- `answer`: the answer to grade
- `criteria`: a list of `{id, text}`
- `penalties`: a list of `{id, text}`, which may be empty

For each entry:

1. Give every criterion one mark, from the answer alone:
   - `1`: the answer states the point correctly, with the figure, date, name or condition the criterion gives;
   - `0.5`: the answer has the right point, but a figure or condition the criterion states is missing or imprecise;
   - `0`: the point is not stated, or is stated wrongly.
   No other marks.
2. Credit only what the answer says. Give nothing for what the writer probably meant, for something true that is left
   unsaid, or for length, confidence or style. A figure counts when it matches after ordinary rounding. Where a criterion
   offers alternatives ("or"), any one of them meets it.
3. The criteria are the standard. Do not add to them or correct them from your own knowledge. If you think a criterion is
   wrong, still mark the answer against it as written, and say so in `note`.
4. For every penalty, decide whether the answer does what the penalty describes: `true` or `false`.
5. Judge each entry on its own. You are not told who wrote the answers. Do not guess, and do not let one entry's quality
   colour another.

Write `{OUT}` as one JSON object and nothing else:

    {"run": "<the queue's run>",
     "digest": "<the queue's digest>",
     "verdicts": {"<id>": {"criteria": {"c1": 1, "c2": 0.5, "c3": 0},
                           "penalties": {"p1": false},
                           "note": "one or two sentences: what was missing or wrong"},
                  "<next id>": {...}}}

Every criterion id and every penalty id of every entry must appear, marks as numbers (`1`, `0.5`, `0`) and penalties as
`true` or `false`; an entry with no penalties gets `"penalties": {}`. Do not work out a total. When the file is written,
reply only with the number of entries you judged.
