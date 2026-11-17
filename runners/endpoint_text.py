#!/usr/bin/env python3
"""Answer the text items of a run folder with a model behind an OpenAI-compatible chat endpoint, one request per item.

    python3 runners/endpoint_text.py --run RUN_DIR --env-file .env.eval [--shards NAME ...] [--model ID]
                                     [--max-tokens N] [--workers N] [--limit N] [--log DIR]
                                     [--temperature T] [--seed N] [--extra-json '{...}'] [--working-in-reply]

For every text shard of RUN_DIR/shards (a shard whose items all have `surface: answer` and no attachments) it sends
each item on its own, with the rules of the shard's README that apply to a text item, and writes the reply to
`answers/answers.jsonl` in the format the README asks for. It is not an agent: the model gets no tools, no files and
no second turn, so there is nothing for a transcript audit to look at. Items that already have an answer line are
skipped, so an interrupted run can be started again.

Every request carries `temperature` (--temperature, default 0), `seed` when --seed is given, and the fields of
--extra-json (for example '{"enable_thinking": true}' where a service switches reasoning on that way). With
--working-in-reply the model is told to write its working in the reply and to end with the answer as one JSON object,
and the last JSON object of the reply is taken; without it the prompt and the reading of the reply are as they were.

The endpoint address and the token come from the env file (QANDY_EVAL_HF_ENDPOINT, QANDY_EVAL_HF_TOKEN). The token is
only ever put into the request header: it is never printed, logged or written to a file. Raw replies and token counts
go to the log folder (default RUN_DIR + "_endpoint_log"), outside the shards.
"""

import argparse
import concurrent.futures
import json
import re
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

RULES = """You are taking an evaluation as the model under test. You are given one item at a time.

Rules:
- Answer from your own knowledge and from what the item says. `as_of` is the date whose law applies. `mode: open_book`
  means the prompt holds the rules you need.
- The people, companies and reference numbers in the item are simulated. Identification numbers (tax, company,
  national ID, bank, card) are made to fail their official check digits on purpose: take each number as it is written
  and as valid and registered, unless the item asks you to check one.
- Work every figure out yourself.
- Do not ask questions. Where something is unclear, take the most reasonable reading.
- Give the item an answer in the format asked. A missing or unreadable answer scores 0; a partial one can earn part
  of the credit."""

OBJECT_FORMAT = """Answer format: an object with exactly these field names: {fields}.
A `number` is a JSON number (no currency sign, no thousands separator), a `label` is one of the options the prompt or
the format gives, a `list` is a JSON array.
Do your working in your reasoning, not in the reply. Reply with the answer as one JSON object and nothing else:
no working, no explanation, no text before or after it."""

# --working-in-reply: the same format lines, with the working asked for in the reply and the answer at its end
WORKING_OBJECT_FORMAT = """Answer format: an object with exactly these field names: {fields}.
A `number` is a JSON number (no currency sign, no thousands separator), a `label` is one of the options the prompt or
the format gives, a `list` is a JSON array.
Work step by step in your reply before you answer: state the rule that applies, list the inputs, and compute each
figure by hand. Then end your reply with the answer as one JSON object on its own, with nothing after it. Only the
last JSON object of your reply is read as your answer."""

TEXT_FORMAT = """Answer format: free text. Write the whole answer for the person who asked, in their language. Your reply is the
answer as it will be read: do not add a preface about the evaluation."""

OTHER_FORMAT = """Answer format: {fmt}
Follow it and the prompt. Reply with the answer as JSON and nothing else."""

WORKING_OTHER_FORMAT = """Answer format: {fmt}
Follow it and the prompt. Work step by step in your reply before you answer: state the rule that applies, list the
inputs, and compute each figure by hand. Then end your reply with the answer as JSON on its own, with nothing after
it. Only the last JSON value of your reply is read as your answer."""


def load_env(path):
    out = {}
    for line in Path(path).read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            key, value = line.split("=", 1)
            out[key.strip()] = value.strip().strip('"').strip("'")
    return out


class Endpoint:
    def __init__(self, base, token, timeout=600):
        base = base.rstrip("/")
        self.base, self._token, self.timeout = (base[:-3] if base.endswith("/v1") else base), token, timeout

    def _request(self, path, body=None):
        data = None if body is None else json.dumps(body).encode("utf-8")
        req = urllib.request.Request(self.base + path, data=data, method="GET" if body is None else "POST")
        req.add_header("Authorization", "Bearer " + self._token)
        req.add_header("Content-Type", "application/json")
        with urllib.request.urlopen(req, timeout=self.timeout) as resp:
            return json.loads(resp.read().decode("utf-8"))

    def call(self, path, body=None, tries=12):
        """The JSON reply, or raises RuntimeError with the status and the start of the body (never a header)."""
        wait = 5
        for attempt in range(tries):
            try:
                return self._request(path, body)
            except urllib.error.HTTPError as e:
                text = e.read().decode("utf-8", "replace")[:400]
                if (e.code == 429 or e.code >= 500) and attempt + 1 < tries:  # 530: the tunnel lost its origin for a while
                    time.sleep(wait)
                    wait = min(wait * 2, 120)
                    continue
                raise RuntimeError(f"HTTP {e.code}: {text}") from None
            except (urllib.error.URLError, TimeoutError, ConnectionError) as e:
                if attempt + 1 < tries:
                    time.sleep(wait)
                    wait = min(wait * 2, 120)
                    continue
                raise RuntimeError(f"no answer from the endpoint: {type(e).__name__}: {getattr(e, 'reason', e)}") from None

    def models(self):
        return [m.get("id") for m in (self.call("/v1/models").get("data") or [])]

    def chat(self, model, messages, max_tokens, stream=True, tries=12, extra=None):
        """The reply in the shape of a non-streamed chat completion. Streamed by default: a tunnel or gateway that
        gives up on a silent connection (HTTP 524) then sees bytes all the way."""
        body = {"model": model, "messages": messages, "max_tokens": max_tokens, **(extra or {})}
        if not stream:
            return self.call("/v1/chat/completions", body)
        body.update(stream=True, stream_options={"include_usage": True})
        wait = 5
        for attempt in range(tries):
            try:
                req = urllib.request.Request(self.base + "/v1/chat/completions", data=json.dumps(body).encode("utf-8"), method="POST")
                req.add_header("Authorization", "Bearer " + self._token)
                req.add_header("Content-Type", "application/json")
                req.add_header("Accept", "text/event-stream")
                text, thought, finish, usage = [], [], None, None
                with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                    for raw in resp:
                        line = raw.decode("utf-8", "replace").strip()
                        if not line.startswith("data:"):
                            continue
                        data = line[5:].strip()
                        if data == "[DONE]":
                            break
                        try:
                            chunk = json.loads(data)
                        except json.JSONDecodeError:
                            continue
                        usage = chunk.get("usage") or usage
                        for choice in chunk.get("choices") or []:
                            delta = choice.get("delta") or {}
                            piece = delta.get("content")
                            if piece:
                                text.append(piece)
                            piece = delta.get("reasoning_content") or delta.get("reasoning")  # reasoning sent beside the reply
                            if piece and isinstance(piece, str):
                                thought.append(piece)
                            finish = choice.get("finish_reason") or finish
                if not text and finish is None:
                    raise RuntimeError("the stream ended with no content")
                message = {"content": "".join(text)}
                if thought:
                    message["reasoning_content"] = "".join(thought)
                return {"choices": [{"message": message, "finish_reason": finish}], "usage": usage}
            except urllib.error.HTTPError as e:
                detail = f"HTTP {e.code}: {e.read().decode('utf-8', 'replace')[:300]}"
                retry = e.code == 429 or e.code >= 500
            except (urllib.error.URLError, TimeoutError, ConnectionError, RuntimeError) as e:
                detail, retry = f"{type(e).__name__}: {getattr(e, 'reason', e)}", True
            if retry and attempt + 1 < tries:
                time.sleep(wait)
                wait = min(wait * 2, 60)
                continue
            raise RuntimeError(detail)


def user_message(item, working=False):
    """The request for one item. `working` (--working-in-reply): the working is asked for in the reply, before the
    answer. A free-text answer is the reply itself, so its request is the same either way."""
    fmt = item.get("answer_format") or {}
    head = {k: item.get(k) for k in ("id", "jurisdiction", "domain", "family", "as_of", "language", "mode")}
    if fmt.get("type") == "object":
        how = (WORKING_OBJECT_FORMAT if working else OBJECT_FORMAT).format(fields=json.dumps(fmt.get("fields"), ensure_ascii=False))
    elif fmt.get("type") == "text":
        how = TEXT_FORMAT
    else:
        how = (WORKING_OTHER_FORMAT if working else OTHER_FORMAT).format(fmt=json.dumps(fmt, ensure_ascii=False))
    return f"Item: {json.dumps(head, ensure_ascii=False)}\n\n{item['prompt']}\n\n{how}"


def visible(text):
    """The reply without a reasoning block some models print before the answer."""
    text = re.sub(r"<think>.*?</think>", "", text or "", flags=re.S)
    return text.split("</think>")[-1].strip()


def last_json(text, fields=None):
    """The last JSON value in the text: with `fields`, the last object that has most of those names."""
    text = re.sub(r"```(?:json)?", "", text)
    decoder, best, best_hits = json.JSONDecoder(), None, -1
    for m in re.finditer(r"[\[{]", text):
        try:
            value, _ = decoder.raw_decode(text[m.start():])
        except json.JSONDecodeError:
            continue
        if fields is None:
            best = value
        elif isinstance(value, dict):
            hits = len(set(value) & set(fields))
            if hits >= best_hits and hits > 0:
                best, best_hits = value, hits
    return best


def last_whole_json(text, fields=None):
    """For a reply that holds working before its answer (--working-in-reply): the last JSON value that stands on its
    own in the text, not a part of another value, whatever JSON the working before it holds. With `fields` it must be
    an object with at least one of those names, or hold one (an answer wrapped in something); if it is neither, the
    reply has no answer."""
    text = re.sub(r"```(?:json)?", "", text)
    decoder, opening, found, at = json.JSONDecoder(), re.compile(r"[\[{]"), [], 0
    while True:
        m = opening.search(text, at)
        if m is None:
            break
        try:
            value, at = decoder.raw_decode(text, m.start())  # go on after the value: what it holds is not looked at again
        except json.JSONDecodeError:
            at = m.start() + 1
            continue
        found.append(value)
    if not found:
        return None
    last = found[-1]
    if fields is None or (isinstance(last, dict) and set(last) & set(fields)):
        return last
    return last_json(json.dumps(last, ensure_ascii=False), fields)


def answer_of(item, reply, working=False):
    """(answer, problem): what goes into answers.jsonl for this reply. `working`: the reply may hold working with JSON
    in it before the answer, so the last JSON object is taken, whatever came before it."""
    fmt = item.get("answer_format") or {}
    text = visible(reply)
    if fmt.get("type") == "text":
        return (text, None) if text else (None, "empty reply")
    fields = list((fmt.get("fields") or {})) if fmt.get("type") == "object" else None
    value = (last_whole_json if working else last_json)(text, fields)
    if value is None:
        return None, "no JSON answer found in the reply"
    return value, None


def request_fields(temperature, seed=None, thinking_budget=None, extra_json=None):
    """The fields every request carries besides the model, the messages and max_tokens: the temperature, the seed if
    one is given, the thinking budget if one is given, then the fields of --extra-json (which win over the others)."""
    fields = {"temperature": temperature}
    if seed is not None:
        fields["seed"] = seed
    if thinking_budget:
        fields["thinking_token_budget"] = thinking_budget
    if extra_json:
        try:
            more = json.loads(extra_json)
        except json.JSONDecodeError as e:
            sys.exit(f"--extra-json is not JSON: {e}")
        if not isinstance(more, dict):
            sys.exit("--extra-json must be a JSON object")
        fields.update(more)
    return fields


def reasoning_off(fields):
    """The fields of the finalization request: those of every request, with reasoning switched off (it asks only for
    the answer to be stated). `reasoning_effort: none` as before; a switch that the fields themselves turned on
    (enable_thinking, also inside chat_template_kwargs) is turned off, and a thinking budget is left out."""
    out = {k: v for k, v in (fields or {}).items() if k != "thinking_token_budget"}
    if "enable_thinking" in out:
        out["enable_thinking"] = False
    if isinstance(out.get("chat_template_kwargs"), dict) and "enable_thinking" in out["chat_template_kwargs"]:
        out["chat_template_kwargs"] = dict(out["chat_template_kwargs"], enable_thinking=False)
    out["reasoning_effort"] = "none"
    return out


def text_shards(run_dir, names):
    out = []
    for shard in sorted((Path(run_dir) / "shards").iterdir()):
        if names and shard.name not in names:
            continue
        try:
            items = [json.loads(l) for l in (shard / "items.jsonl").read_text(encoding="utf-8").splitlines() if l.strip()]
        except OSError:
            continue
        if items and all(i.get("surface") == "answer" and not i.get("attachments") for i in items):
            out.append((shard, items))
    return out


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--run", required=True)
    ap.add_argument("--env-file", required=True)
    ap.add_argument("--shards", nargs="*", default=[])
    ap.add_argument("--model")
    ap.add_argument("--max-tokens", type=int, default=6000)
    ap.add_argument("--workers", type=int, default=4)
    ap.add_argument("--thinking-budget", type=int, help="cap on reasoning tokens, sent as thinking_token_budget (counts toward --max-tokens)")
    ap.add_argument("--temperature", type=float, default=0.0, help="sampling temperature, sent with every request (default 0)")
    ap.add_argument("--seed", type=int, help="sampling seed, sent with every request when given")
    ap.add_argument("--extra-json", help="more request fields as a JSON object, merged into every request")
    ap.add_argument("--working-in-reply", action="store_true",
                    help="ask for the working in the reply, then the answer as one JSON object at its end; the last JSON object of the reply is taken")
    ap.add_argument("--limit", type=int, help="answer at most this many items (a trial)")
    ap.add_argument("--log")
    ap.add_argument("--probe", action="store_true", help="only say which models the endpoint serves")
    args = ap.parse_args()

    env = load_env(args.env_file)
    base = env.get("QANDY_EVAL_ENDPOINT") or env.get("QANDY_EVAL_HF_ENDPOINT")
    token = env.get("QANDY_EVAL_API_KEY") or env.get("QANDY_EVAL_HF_TOKEN")
    if not base or not token:
        sys.exit("the env file needs QANDY_EVAL_HF_ENDPOINT and QANDY_EVAL_HF_TOKEN")
    endpoint = Endpoint(base, token, timeout=1800)
    try:
        served = endpoint.models()
    except RuntimeError as e:
        sys.exit(f"the endpoint did not answer /v1/models: {e}")
    print("models served:", served)
    if args.probe:
        return
    model = args.model or (served[0] if served else None)
    if not model:
        sys.exit("no model named and the endpoint lists none: pass --model")

    log_dir = Path(args.log or (str(Path(args.run)) + "_endpoint_log"))
    log_dir.mkdir(parents=True, exist_ok=True)
    jobs = []
    for shard, items in text_shards(args.run, set(args.shards)):
        answers = shard / "answers" / "answers.jsonl"
        done = set()
        if answers.is_file():
            for line in answers.read_text(encoding="utf-8").splitlines():
                try:
                    done.add(json.loads(line)["id"])
                except (json.JSONDecodeError, KeyError, TypeError):
                    pass
        jobs += [(shard, item) for item in items if item["id"] not in done]
    if args.limit:
        jobs = jobs[:args.limit]
    print(f"{len(jobs)} items to answer with {model}, {args.workers} at a time")
    extra = request_fields(args.temperature, args.seed, args.thinking_budget, args.extra_json)
    print(f"request fields: {json.dumps(extra, ensure_ascii=False)}; max_tokens {args.max_tokens}; working in reply: {'yes' if args.working_in_reply else 'no'}")

    def one(job):
        shard, item = job
        started = time.time()
        try:
            messages = [{"role": "system", "content": RULES}, {"role": "user", "content": user_message(item, args.working_in_reply)}]
            reply = endpoint.chat(model, messages, args.max_tokens, extra=extra)
            choice = (reply.get("choices") or [{}])[0]
            text = (choice.get("message") or {}).get("content") or ""
            thought = (choice.get("message") or {}).get("reasoning_content") or ""
            answer, problem = answer_of(item, text, args.working_in_reply)
            record = {"id": item["id"], "finish_reason": choice.get("finish_reason"), "usage": reply.get("usage"), "reply": text}
            if thought:
                record["reasoning_chars"] = len(thought)
            # When its reasoning budget runs out this model goes on reasoning in the reply and can reach the token limit
            # without an answer. Then it is asked once, with reasoning off, to state its answer from the working it wrote.
            if answer is None or choice.get("finish_reason") == "length":
                as_text = (item.get("answer_format") or {}).get("type") == "text"
                ask = ("Stop working now. From your working above, " + (
                    "write your final answer for the person who asked, in their language, as it will be read: no working, no preface."
                    if as_text else "give your final answer as the JSON object in the format asked, and nothing else."))
                # the working it wrote: its reply, or, when the limit was reached before any reply, the reasoning the service sent beside it
                second = endpoint.chat(model, messages + [{"role": "assistant", "content": visible(text)[-30000:] or thought[-30000:] or "(nothing written yet)"},
                                                          {"role": "user", "content": ask}], 4000 if as_text else 1500, extra=reasoning_off(extra))
                final = ((second.get("choices") or [{}])[0].get("message") or {}).get("content") or ""
                again, why = answer_of(item, final, args.working_in_reply)
                record.update(finalized=True, usage_final=second.get("usage"), reply_final=final)
                if again is not None:
                    answer, problem = again, None
                else:
                    answer, problem = (None, why) if not as_text else (answer, problem)
            record.update(seconds=round(time.time() - started, 1), problem=problem)
        except RuntimeError as e:
            answer, problem, record = None, str(e), {"id": item["id"], "seconds": round(time.time() - started, 1), "problem": str(e)}
        return shard, item, answer, problem, record

    totals = {"answered": 0, "problems": 0, "finalized": 0, "prompt_tokens": 0, "completion_tokens": 0}
    with concurrent.futures.ThreadPoolExecutor(max_workers=args.workers) as pool:
        for n, (shard, item, answer, problem, record) in enumerate(pool.map(one, jobs), 1):
            (shard / "answers").mkdir(exist_ok=True)
            with open(log_dir / f"{shard.name}.jsonl", "a", encoding="utf-8") as f:
                f.write(json.dumps(record, ensure_ascii=False) + "\n")
            usage = record.get("usage") or {}
            totals["prompt_tokens"] += usage.get("prompt_tokens") or 0
            totals["completion_tokens"] += usage.get("completion_tokens") or 0
            totals["completion_tokens"] += (record.get("usage_final") or {}).get("completion_tokens") or 0
            totals["finalized"] += bool(record.get("finalized"))
            if answer is None:
                totals["problems"] += 1
                print(f"  {item['id']}: no answer written ({problem})")
            else:
                with open(shard / "answers" / "answers.jsonl", "a", encoding="utf-8") as f:
                    f.write(json.dumps({"id": item["id"], "answer": answer}, ensure_ascii=False) + "\n")
                totals["answered"] += 1
            if n % 25 == 0:
                print(f"  {n} of {len(jobs)} done")
    for shard, _ in text_shards(args.run, set(args.shards)):
        notes = shard / "answers" / "notes.md"
        if (shard / "answers").is_dir() and not notes.exists():
            notes.write_text("Answered through runners/endpoint_text.py: one request per item, no tools, no notes from the model.\n", encoding="utf-8")
    print(json.dumps(totals))


if __name__ == "__main__":
    main()
