# Solver prompt (blind run)

One solver per shard. Start the run first:

    qandy-eval run-servers start --frozen DIR --kit KIT_DIR --run RUN_DIR --run-id R

Every run needs a **new folder** of its own and a run id of its own (k1, k2, k3): a run folder serves one run id and one
kit for good, and `run-servers start` refuses a folder that already holds another run. Start every run this way, also
when the kit needs no servers: it makes the run folder and writes each item's own address into its shard. Then give each
solver the text below the line with `{SHARD_DIR}` replaced by the absolute path of its shard (`RUN_DIR/shards/<shard>`).

For the person or agent launching solvers:
- Send the text below and nothing else. Do not say which model is being tested or compared, what the scores are for, where
  the repository or the frozen set is, or how other shards went. Keep model names out of the run id and out of the path
  of the run folder as well: a solver sees both.
- Give the solver no web search or web fetch tool, and start it with the shard as its working folder.
- The same shard goes to a fresh solver in each run (k1, k2, k3): a solver never sees another run's answers.
- Do not answer a solver's questions about an item, and do not fix its answers. What it wrote is what is graded.
- A solver is never told a run id and never picks one: each item's `env` holds its full address, and the servers answer
  nothing else.
- While solvers work, run no command that names the frozen set (`grade-run --frozen ...`, `make-run-kit`): a command line
  can be listed by any process on the machine. The servers themselves do not show it.
- Before the first run, run `uv run --with pypdf python3 -c "import pypdf"` once, so the PDF tool finds the package on the
  machine and never needs the network.
- Check the servers before and after the solvers work: `qandy-eval run-servers status --run RUN_DIR`. If they died, the
  run of the shards that were still open does not count: start those shards again in a new run folder.
- When the solvers are done, audit their transcripts: `qandy-eval audit-transcripts --run RUN_DIR --transcripts DIR`.
  It lists every shard whose solver read or wrote outside its shard, used the web or the network, or ran code or a
  calculator (also when the code only formatted, filtered or checked output; the audit says which flags are of that
  kind, and they count all the same): that run of the shard does not count. The same holds if a solver reports that it
  saw a key or anything outside its shard: note the shard and tell the user.
- Write the report (`grade-run --out`) outside every run folder: a report holds expected values.

---

You are taking an evaluation as the model under test. Your whole task is in one folder:

    {SHARD_DIR}

Read `README.md` in that folder first and follow it exactly. It lists the items (`items.jsonl`), the rules, and the answer
format for each kind of item.

The rules, which the README repeats:

1. Work only inside that folder. Do not read, list or search anything outside it: no repository, no other shard, no earlier
   run, no home folder.
2. Do not look for answer keys, expected values, engines, graders, tests or reports. If you come across something that
   looks like one, stop reading it and say so in your notes.
3. No web search and no web fetch. The only network access allowed is the simulated systems on 127.0.0.1 that the README
   lists, if it lists any, at the addresses the items give. Use each address exactly as it is written.
4. Work the answers out yourself, from your own knowledge and the documents in the folder. No code and no calculator, for
   anything: do not run an interpreter, a calculator or an expression evaluator of any kind (python, node, jq, awk, bc,
   expr, shell arithmetic, a spreadsheet), not to compute and not to format, filter or check output. Allowed, and nothing
   else: reading files in the folder (`cat`, `head`, `tail`, `ls`, `find`, `grep`, `sort`, `wc`, `sed -n`, your
   file-reading tool); the tools in `tools/`, run as the README shows (they print what you need as plain text, and
   `python3 tools/check_answers.py` checks the format of your answer files: run it before you finish); requests to the
   servers the README lists, made through those tools; writing your answer files; and, for a `code` item, the program the
   item asks you to write. Working files go under `work/` in that folder and nowhere else. Every command you run is
   audited afterwards, and code or a calculator in any form makes your whole shard invalid.
5. Answer every item in exactly the format the README gives: in the `answers/` folder, or, for a simulated system, by the
   state you leave it in. A PDF form counts only as the filled PDF file, and a simulated system only as what you did in
   it: writing those answers down somewhere else scores nothing. A missing or unreadable answer scores 0, so write what
   you have even when you are unsure.
6. Do not ask questions. Where something is unclear, take the most reasonable reading and say which in your notes.
7. Do not change `items.jsonl`, `README.md` or the tools.

When you have finished, write `answers/notes.md` as the README describes. Then reply with one line per item: its id and
`answered`, `partly answered` or `not answered`. Do not repeat your answers in the reply.
