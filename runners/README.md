# Runners for models behind an OpenAI-compatible API

These two scripts are the loops used to run models that are reached through a chat-completions endpoint
(for the first results: Qwen 3.8 27B).

- `endpoint_text.py`: one request per text item. If a reply runs out of tokens or holds no answer, the model is asked
  once, with reasoning off, to state its answer from its working.
- `endpoint_agent.py`: one conversation per agentic shard, with seven tools (read and list files, view pages and
  images, run the shard's own tools, write answer files). Options used for the published runs: `--max-steps 120` for
  core shards and `200` for case shards, `--max-tokens 6000`, `--max-images 4`.

Both read the endpoint address and key from an env file (`QANDY_EVAL_ENDPOINT`, `QANDY_EVAL_API_KEY`) and never print
or store the key. They expect a run folder made by the QandyEval harness, which is not part of this repository, so
they are published as a record of how the runs were made rather than as a ready-to-run tool.
