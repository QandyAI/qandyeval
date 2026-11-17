# Runners for models behind an OpenAI-compatible API

These two scripts are the loops used to run models that are reached through a chat-completions endpoint
(for the first results: Qwen 3.8 27B).

- `endpoint_text.py`: one request per text item. If a reply runs out of tokens or holds no answer, the model is asked
  once, with reasoning off, to state its answer from its working. Options used for the published Qwen 3.8 27B run of
  17 November: `--max-tokens 6000 --working-in-reply` (the working is written in the reply and the last JSON object of
  the reply is the answer), temperature 0, `--seed` 1, 2 and 3 for the three hard and expert runs.
- `endpoint_agent.py`: one conversation per agentic shard, with tools to read and list files, view pages and images,
  run the shard's own tools, write answer files and, where a code item's README allows it, run the model's own program
  in a confined folder. The loop tells the model its step limit and, with an image limit, which pages left view; a
  reply cut at the token limit in the middle of a tool call is dropped and the model told to write in parts. Options
  used for the run of 17 November: `--max-steps 120` for core shards and `200` for case shards, `--max-tokens 16000`,
  `--max-images 4`, temperature 0, `--seed` 1, 2 and 3. The first run of 15 November used the version in this
  repository's first commit, with `--max-tokens 6000`.

Both read the endpoint address and key from an env file (`QANDY_EVAL_ENDPOINT`, `QANDY_EVAL_API_KEY`) and never print
or store the key. They expect a run folder made by the QandyEval harness, which is not part of this repository, so
they are published as a record of how the runs were made rather than as a ready-to-run tool.
