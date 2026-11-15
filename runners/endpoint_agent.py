#!/usr/bin/env python3
"""Work the agentic shards of a run folder with a model behind an OpenAI-compatible chat endpoint.

    python3 runners/endpoint_agent.py --run RUN_DIR --env-file .env.eval [--shards NAME ...] [--model ID]
                                      [--workers N] [--max-steps N] [--max-tokens N] [--log DIR]

One conversation per shard. The model works in the shard folder only through the tools below, which is how the rules
of the shard's README are kept: there is no shell, no web and no calculator to misuse.

    list_files    the files of the folder (or of one of its sub-folders)
    read_file     a text file, in pages
    view_image    a scanned document (jpg, png): the image is put in front of the model
    view_pdf      a PDF document: its text layer, and its first page as an image
    run_tool      one of the kit's own tools in tools/ (pdf_tool.py, app_tool.py, ledger_tool.py, workspace_tool.py,
                  check_answers.py) with its arguments; these are also the only way to the run's servers
    write_file    a file under answers/ or work/
    append_file   lines added to a file under answers/ or work/

Shards that hold only text items are left to runners/endpoint_text.py. A shard that already has answers/notes.md is
skipped (so an interrupted run can be started again; delete the shard's answers/ and work/ to redo it). Every step is
logged to the log folder (default RUN_DIR + "_endpoint_log"): tool calls, sizes, token counts. The token of the env
file is only ever put into the request header.
"""

import argparse
import base64
import concurrent.futures
import json
import re
import shlex
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from endpoint_text import load_env  # noqa: E402

SYSTEM = """You are taking an evaluation as the model under test. Your whole task is in one folder, the task folder.
You work in it only through the tools you are given; every path is relative to the task folder.

Read `README.md` first with read_file and follow it exactly. It lists the items (`items.jsonl`), the rules, and the
answer format for each kind of item. How its instructions map to your tools:
- Where the README shows a command that runs one of the tools in `tools/`, such as
  `python3 tools/pdf_tool.py list <pdf>` or `uv run --with pypdf python3 tools/pdf_tool.py fill <pdf> <values> <out>`,
  call run_tool with the tool's file name and the arguments as a list of strings, in the same order.
- Where it says to read or open a file, use read_file; for a scanned document or any image, view_image; for a PDF
  document, view_pdf; to see what a folder holds, list_files.
- Where it says to write or append to a file (answers, notes, a values file under work/), use write_file or append_file.

The rules, which the README repeats:
1. Work only inside the task folder. The tools refuse anything else.
2. Do not look for answer keys, expected values, engines, graders, tests or reports.
3. There is no web. The only network access is the simulated systems the README lists, reached through the tools in
   `tools/` at the addresses the items give. Use each address exactly as it is written.
4. Work the answers out yourself, from your own knowledge and the documents in the folder. You have no code and no
   calculator: work every figure out yourself.
5. Answer every item in exactly the format the README gives: in the `answers/` folder, or, for a simulated system, by
   the state you leave it in. A PDF form counts only as the filled PDF file, and a simulated system only as what you
   did in it. A missing or unreadable answer scores 0, so write what you have even when you are unsure.
6. Do not ask questions. Where something is unclear, take the most reasonable reading and say which in your notes.
7. Do not change `items.jsonl`, `README.md` or the tools.

When you have finished, write `answers/notes.md` as the README describes and run the format check
(run_tool with `check_answers.py`). Then reply, without calling a tool, with one line per item: its id and `answered`,
`partly answered` or `not answered`."""


def _fn(name, description, properties, required):
    return {"type": "function", "function": {"name": name, "description": description,
                                             "parameters": {"type": "object", "properties": properties, "required": required}}}


TOOLS = [
    _fn("list_files", "List the files of the task folder, or of one sub-folder of it.",
        {"path": {"type": "string", "description": "a folder, relative to the task folder; default the task folder"}}, []),
    _fn("read_file", "Read a text file of the task folder. Long files come in pages of 400 lines.",
        {"path": {"type": "string"}, "page": {"type": "integer", "description": "1 for the first 400 lines (default), 2 for the next, ..."}}, ["path"]),
    _fn("view_image", "Look at an image of the task folder (a scanned document: jpg or png). Several paths may be given.",
        {"paths": {"type": "array", "items": {"type": "string"}}}, ["paths"]),
    _fn("view_pdf", "Read a PDF document of the task folder: its text, and its first page as an image.",
        {"path": {"type": "string"}}, ["path"]),
    _fn("run_tool", "Run one of the tools in tools/ of the task folder, as the README shows, and get what it prints.",
        {"tool": {"type": "string", "description": "the file name, for example pdf_tool.py"},
         "args": {"type": "array", "items": {"type": "string"}, "description": "the arguments, in order"}}, ["tool", "args"]),
    _fn("write_file", "Write a text file under answers/ or work/ (replaces the file).",
        {"path": {"type": "string"}, "content": {"type": "string"}}, ["path", "content"]),
    _fn("append_file", "Add text to the end of a file under answers/ or work/ (for example one line of answers/answers.jsonl).",
        {"path": {"type": "string"}, "content": {"type": "string"}}, ["path", "content"]),
]
NEEDS_PYPDF = {"pdf_tool.py", "check_answers.py"}


class Refused(Exception):
    pass


class Shard:
    """The tools, bound to one shard folder."""

    def __init__(self, folder):
        self.dir = Path(folder).resolve()

    def path(self, rel, writable=False):
        if not isinstance(rel, str) or not rel.strip():
            raise Refused("a path is needed")
        target = (self.dir / rel).resolve()
        if target != self.dir and self.dir not in target.parents:
            raise Refused(f"{rel} is outside the task folder")
        if writable and (target.relative_to(self.dir).parts[:1] or ("",))[0] not in ("answers", "work"):
            raise Refused("only files under answers/ or work/ may be written")
        return target

    def list_files(self, path="."):
        folder = self.path(path or ".")
        if not folder.is_dir():
            raise Refused(f"{path} is not a folder")
        rows = []
        for p in sorted(folder.rglob("*")):
            if p.is_file() and "__pycache__" not in p.parts:
                rows.append(f"{p.relative_to(self.dir).as_posix()}  ({p.stat().st_size} bytes)")
        return "\n".join(rows[:800]) + (f"\n... {len(rows) - 800} more files" if len(rows) > 800 else "") or "(empty)"

    def read_file(self, path, page=1):
        target = self.path(path)
        if not target.is_file():
            raise Refused(f"{path}: no such file")
        if target.suffix.lower() in (".jpg", ".jpeg", ".png", ".pdf"):
            raise Refused(f"{path} is not a text file: use view_image or view_pdf")
        lines = target.read_text(encoding="utf-8", errors="replace").splitlines()
        page = max(1, int(page or 1))
        part = lines[(page - 1) * 400:page * 400]
        pages = max(1, -(-len(lines) // 400))
        text = "\n".join(part)
        if len(text) > 60000:
            text = text[:60000] + "\n... (line too long: cut)"
        return f"[{path}, page {page} of {pages}]\n{text}"

    def image(self, path):
        target = self.path(path)
        if not target.is_file() or target.suffix.lower() not in (".jpg", ".jpeg", ".png"):
            raise Refused(f"{path}: not an image of the task folder")
        kind = "png" if target.suffix.lower() == ".png" else "jpeg"
        return {"type": "image_url", "image_url": {"url": f"data:image/{kind};base64," + base64.b64encode(target.read_bytes()).decode()}}

    def view_pdf(self, path):
        """(text, image block or None)."""
        target = self.path(path)
        if not target.is_file() or target.suffix.lower() != ".pdf":
            raise Refused(f"{path}: not a PDF of the task folder")
        code = ("import sys, pypdf\nr = pypdf.PdfReader(sys.argv[1])\nprint(f'[{len(r.pages)} pages]')\n"
                "for n, p in enumerate(r.pages, 1):\n    print(f'--- page {n}'); print(p.extract_text() or '(no text layer on this page)')\n")
        out = subprocess.run(["uv", "run", "--quiet", "--with", "pypdf", "python3", "-c", code, str(target)], capture_output=True, text=True, timeout=120)
        text = (out.stdout or out.stderr)[:40000]
        block = None
        try:
            png = self.dir / "work" / (target.stem + ".page1.png")
            png.parent.mkdir(exist_ok=True)
            done = subprocess.run(["sips", "-s", "format", "png", str(target), "--out", str(png)], capture_output=True, text=True, timeout=60)
            if done.returncode == 0 and png.is_file():
                block = {"type": "image_url", "image_url": {"url": "data:image/png;base64," + base64.b64encode(png.read_bytes()).decode()}}
                png.unlink()
        except (OSError, subprocess.SubprocessError):
            pass
        return text, block

    def run_tool(self, tool, args):
        tools = {p.name for p in (self.dir / "tools").glob("*.py")} if (self.dir / "tools").is_dir() else set()
        if isinstance(tool, str):
            tool = tool.strip().split("/")[-1]  # "tools/pdf_tool.py" is the same tool
        if tool in ("write_file", "append_file", "read_file", "list_files", "view_image", "view_pdf"):
            raise Refused(f"{tool} is not a file in tools/: it is one of your own tools, so call {tool} directly")
        if tool not in tools:
            raise Refused(f"no tool {tool} in tools/ (there: {', '.join(sorted(tools)) or 'none'})")
        if isinstance(args, str):  # the list sent as one string: as JSON, or as it would be typed on a command line
            try:
                parsed = json.loads(args)
                args = parsed if isinstance(parsed, list) else shlex.split(args)
            except ValueError:
                try:
                    args = shlex.split(args)
                except ValueError:
                    raise Refused("args could not be read: give a list of strings") from None
        if isinstance(args, list):  # a JSON body given as an object is passed on as its text
            args = [a if isinstance(a, str) else json.dumps(a, ensure_ascii=False) for a in args]
        if not isinstance(args, list):
            raise Refused("args must be a list of strings")
        for a in args:
            if re.match(r"https?://", a):
                if not re.match(r"https?://127\.0\.0\.1[:/]", a):
                    raise Refused(f"{a[:80]}: not one of the run's servers")
            elif ("/" in a or a.startswith("..")) and not a.lstrip().startswith(("{", "[")):
                self.path(a)  # a path argument must stay inside the folder
        head = ["uv", "run", "--quiet", "--with", "pypdf", "python3"] if tool in NEEDS_PYPDF else ["python3"]
        try:
            out = subprocess.run(head + [f"tools/{tool}"] + args, cwd=self.dir, capture_output=True, text=True, timeout=300)
        except subprocess.TimeoutExpired:
            return "the tool did not finish within 300 seconds"
        text = (out.stdout or "") + (("\n[stderr]\n" + out.stderr) if out.stderr.strip() else "")
        if len(text) > 40000:
            text = text[:40000] + f"\n... ({len(text) - 40000} more characters: ask for one part with the tool's own options)"
        return text.strip() or f"(no output, exit code {out.returncode})"

    def write(self, path, content, append=False):
        target = self.path(path, writable=True)
        if not isinstance(content, str):
            raise Refused("content must be text")
        target.parent.mkdir(parents=True, exist_ok=True)
        with open(target, "a" if append else "w", encoding="utf-8") as f:
            f.write(content if (not append or content.endswith("\n")) else content + "\n")
        return f"{'added to' if append else 'written'} {path} ({target.stat().st_size} bytes now)"


def chat(base, token, body, timeout=1800, tries=12):
    """A streamed chat completion, put together: {content, tool_calls, finish_reason, usage}."""
    body = dict(body, stream=True, stream_options={"include_usage": True})
    wait = 5
    for attempt in range(tries):
        try:
            req = urllib.request.Request(base + "/v1/chat/completions", data=json.dumps(body).encode("utf-8"), method="POST")
            req.add_header("Authorization", "Bearer " + token)
            req.add_header("Content-Type", "application/json")
            req.add_header("Accept", "text/event-stream")
            text, calls, finish, usage, provider = [], {}, None, None, None
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                for raw in resp:
                    line = raw.decode("utf-8", "replace").strip()
                    if not line.startswith("data:") or line[5:].strip() == "[DONE]":
                        continue
                    try:
                        chunk = json.loads(line[5:].strip())
                    except json.JSONDecodeError:
                        continue
                    usage = chunk.get("usage") or usage
                    provider = chunk.get("provider") or provider
                    for choice in chunk.get("choices") or []:
                        delta = choice.get("delta") or {}
                        if delta.get("content"):
                            text.append(delta["content"])
                        for call in delta.get("tool_calls") or []:
                            slot = calls.setdefault(call.get("index", 0), {"id": None, "name": "", "arguments": ""})
                            slot["id"] = call.get("id") or slot["id"]
                            fn = call.get("function") or {}
                            slot["name"] += fn.get("name") or ""
                            slot["arguments"] += fn.get("arguments") or ""
                        finish = choice.get("finish_reason") or finish
            if finish is None and not text and not calls:
                raise RuntimeError("the stream ended with nothing in it")
            return {"content": "".join(text), "tool_calls": [calls[k] for k in sorted(calls)], "finish_reason": finish, "usage": usage, "provider": provider}
        except urllib.error.HTTPError as e:
            detail = f"HTTP {e.code}: {e.read().decode('utf-8', 'replace')[:300]}"
            retry = e.code == 429 or e.code >= 500  # 530: the tunnel lost its origin for a while
        except (urllib.error.URLError, TimeoutError, ConnectionError, RuntimeError) as e:
            detail, retry = f"{type(e).__name__}: {getattr(e, 'reason', e)}", True
        if retry and attempt + 1 < tries:
            time.sleep(wait)
            wait = min(wait * 2, 60)
            continue
        raise RuntimeError(detail)


def trim(messages, keep_last=12):
    """Make room: earlier images are taken out (they can be viewed again) and long old tool results are cut."""
    for m in messages[:-keep_last]:
        if m["role"] == "user" and isinstance(m["content"], list):
            m["content"] = "[images shown earlier were removed to save space; view them again if you need them]"
        elif m["role"] == "tool" and isinstance(m["content"], str) and len(m["content"]) > 3000:
            m["content"] = m["content"][:3000] + "\n... (cut to save space; run it again if you need the rest)"


def valid_json(text):
    """Arguments as they go back into the conversation: some services refuse a request whose history holds a tool call
    with broken JSON, so broken arguments are replaced by {} there (the model is told in the tool result)."""
    try:
        json.loads(text or "{}")
        return text or "{}"
    except json.JSONDecodeError:
        return "{}"


def cap_images(messages, cap):
    """Some services take only a few images in one request: keep at most `cap` image blocks in the whole conversation,
    taking out the oldest first (the model can view them again)."""
    def count(m):
        return sum(1 for b in m["content"] if isinstance(b, dict) and b.get("type") == "image_url") \
            if m["role"] == "user" and isinstance(m["content"], list) else 0
    total = sum(count(m) for m in messages)
    for m in messages[:-1]:
        if total <= cap:
            break
        n = count(m)
        if n:
            m["content"] = f"[{n} image(s) shown earlier were taken out: at most {cap} images fit in one request; view them again if you need them]"
            total -= n


def solve(shard_dir, base, token, model, log_dir, max_steps, max_tokens, window, extra=None, max_images=None):
    shard = Shard(shard_dir)
    name = shard.dir.name
    log = open(Path(log_dir) / f"{name}.steps.jsonl", "a", encoding="utf-8")
    messages = [{"role": "system", "content": SYSTEM},
                {"role": "user", "content": "Begin. The task folder holds:\n" + shard.list_files(".")[:6000]
                 + "\n\nStart by calling read_file with path README.md. You know nothing about the task until you have read "
                   "README.md, items.jsonl and the documents of each item, so do not answer before that."}]
    totals = {"shard": name, "steps": 0, "prompt_tokens": 0, "completion_tokens": 0, "tool_calls": 0, "refused": 0, "nudges": 0, "ended": None}
    force = True  # the first turn must be a tool call (if the endpoint takes tool_choice)
    started = time.time()
    for step in range(1, max_steps + 1):
        try:
            body = {"model": model, "messages": messages, "tools": TOOLS, "max_tokens": max_tokens, **(extra or {})}
            if force and step == 1:
                try:
                    reply = chat(base, token, dict(body, tool_choice="required"), tries=1)
                except RuntimeError:
                    force = False
                    reply = chat(base, token, body)
            else:
                reply = chat(base, token, body)
        except RuntimeError as e:
            totals["ended"] = f"endpoint error: {e}"
            break
        usage = reply.get("usage") or {}
        totals["steps"] = step
        totals["prompt_tokens"] += usage.get("prompt_tokens") or 0
        totals["completion_tokens"] += usage.get("completion_tokens") or 0
        record = {"step": step, "usage": usage, "provider": reply.get("provider"), "finish_reason": reply["finish_reason"], "calls": [], "text": reply["content"][:2000]}
        if not reply["tool_calls"]:
            log.write(json.dumps(record, ensure_ascii=False) + "\n")
            if reply["finish_reason"] == "length" and not reply["content"].strip():
                messages.append({"role": "user", "content": "Your last turn ran out of room before you wrote anything. Go on in smaller steps."})
                continue
            # nothing said in a reply is graded: when the work is not there yet, say so (at most three times) and go on
            if not (shard.dir / "answers" / "notes.md").exists() and totals["nudges"] < 3:
                totals["nudges"] += 1
                try:
                    check = shard.run_tool("check_answers.py", [])[:3000]
                except Refused:
                    check = ""
                messages.append({"role": "assistant", "content": reply["content"] or "(no text)"})
                messages.append({"role": "user", "content": "You replied without calling a tool, but the task is not finished: answers/notes.md does not exist yet. "
                                 "Nothing you write in a reply is graded, only the files under answers/ and what you did in the simulated systems. "
                                 "Do not describe answers you have not produced. Continue with the tools: read what you have not read, then produce "
                                 "each answer as the README says." + (f"\n\nThe format check says:\n{check}" if check else "")})
                continue
            totals["ended"], totals["final"] = "finished", reply["content"][:1500]
            break
        messages.append({"role": "assistant", "content": reply["content"] or None,
                         "tool_calls": [{"id": c["id"] or f"call_{step}_{n}", "type": "function", "function": {"name": c["name"], "arguments": valid_json(c["arguments"])}}
                                        for n, c in enumerate(reply["tool_calls"])]})
        images = []
        for n, call in enumerate(reply["tool_calls"]):
            call_id = call["id"] or f"call_{step}_{n}"
            try:
                a = json.loads(call["arguments"] or "{}")
                if not isinstance(a, dict):
                    raise Refused("the arguments must be a JSON object")
                if call["name"] == "list_files":
                    result = shard.list_files(a.get("path", "."))
                elif call["name"] == "read_file":
                    result = shard.read_file(a.get("path"), a.get("page", 1))
                elif call["name"] == "view_image":
                    paths = a.get("paths") if isinstance(a.get("paths"), list) else [a.get("path")]
                    per = min(8, max_images or 8)
                    blocks = [shard.image(p) for p in paths[:per]]
                    images += [{"type": "text", "text": "Images: " + ", ".join(map(str, paths[:per]))}] + blocks
                    result = f"{len(blocks)} image(s) follow in the next message" + (f"; only the first {per} were taken, view the others in another call" if len(paths) > per else "")
                elif call["name"] == "view_pdf":
                    result, block = shard.view_pdf(a.get("path"))
                    if block:
                        images += [{"type": "text", "text": f"First page of {a.get('path')}:"}, block]
                        result += "\n(the first page follows as an image in the next message)"
                elif call["name"] == "run_tool":
                    result = shard.run_tool(a.get("tool"), a.get("args", []))
                elif call["name"] in ("write_file", "append_file"):
                    result = shard.write(a.get("path"), a.get("content"), append=call["name"] == "append_file")
                else:
                    raise Refused(f"there is no tool {call['name']}")
            except Refused as e:
                result = f"refused: {e}"
                totals["refused"] += 1
            except json.JSONDecodeError:
                result = "refused: the arguments were not valid JSON"
                totals["refused"] += 1
            except (OSError, subprocess.SubprocessError, ValueError, TypeError) as e:
                result = f"the tool failed: {type(e).__name__}: {e}"
            totals["tool_calls"] += 1
            record["calls"].append({"name": call["name"], "arguments": call["arguments"][:1500], "result_chars": len(result), "result_start": result[:300]})
            messages.append({"role": "tool", "tool_call_id": call_id, "content": result})
        if images and max_images:  # several viewing calls in one step: keep the first ones that fit
            kept, n = [], 0
            for b in images:
                if b.get("type") == "image_url":
                    n += 1
                    if n > max_images:
                        continue
                kept.append(b)
            if n > max_images:
                kept.append({"type": "text", "text": f"(only {max_images} images fit in one request: view the others in a later step)"})
            images = kept
        if images:
            messages.append({"role": "user", "content": images})
            if max_images:
                cap_images(messages, max_images)
        log.write(json.dumps(record, ensure_ascii=False) + "\n")
        log.flush()
        if (usage.get("prompt_tokens") or 0) > window:
            trim(messages)
    else:
        totals["ended"] = f"stopped after {max_steps} steps"
    totals["seconds"] = round(time.time() - started)
    log.write(json.dumps({"summary": totals}, ensure_ascii=False) + "\n")
    log.close()
    return totals


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--run", required=True)
    ap.add_argument("--env-file", required=True)
    ap.add_argument("--shards", nargs="*", default=[])
    ap.add_argument("--model")
    ap.add_argument("--workers", type=int, default=6)
    ap.add_argument("--max-steps", type=int, default=150)
    ap.add_argument("--max-tokens", type=int, default=16000)
    ap.add_argument("--max-images", type=int, help="the most images a request may hold (some services take only a few)")
    ap.add_argument("--extra-json", help="more request fields as a JSON object, merged into every request")
    ap.add_argument("--thinking-budget", type=int, help="cap on reasoning tokens per step, sent as thinking_token_budget (counts toward --max-tokens)")
    ap.add_argument("--window", type=int, default=190000, help="prompt tokens above which earlier images and long results are cut")
    ap.add_argument("--log")
    args = ap.parse_args()
    env = load_env(args.env_file)
    base = (env.get("QANDY_EVAL_ENDPOINT") or env.get("QANDY_EVAL_HF_ENDPOINT") or "").rstrip("/")
    token = env.get("QANDY_EVAL_API_KEY") or env.get("QANDY_EVAL_HF_TOKEN")
    if not base or not token:
        sys.exit("the env file needs QANDY_EVAL_HF_ENDPOINT and QANDY_EVAL_HF_TOKEN")
    base = base[:-3] if base.endswith("/v1") else base
    model = args.model or "qandy-2.0"
    extra = dict({"thinking_token_budget": args.thinking_budget} if args.thinking_budget else {}, **(json.loads(args.extra_json) if args.extra_json else {}))
    extra = extra or None
    log_dir = Path(args.log or (str(Path(args.run)) + "_endpoint_log"))
    log_dir.mkdir(parents=True, exist_ok=True)
    todo = []
    for shard in sorted((Path(args.run) / "shards").iterdir()):
        if args.shards and shard.name not in args.shards:
            continue
        try:
            items = [json.loads(l) for l in (shard / "items.jsonl").read_text(encoding="utf-8").splitlines() if l.strip()]
        except OSError:
            continue
        text_only = all(i.get("surface") == "answer" and not i.get("attachments") for i in items)
        if (text_only and not args.shards) or (shard / "answers" / "notes.md").exists():
            continue
        todo.append(shard)
    print(f"{len(todo)} shards to work with {model}, {args.workers} at a time", flush=True)
    with concurrent.futures.ThreadPoolExecutor(max_workers=args.workers) as pool:
        futures = [pool.submit(solve, s, base, token, model, log_dir, args.max_steps, args.max_tokens, args.window,
                               extra, args.max_images) for s in todo]
        for f in concurrent.futures.as_completed(futures):
            t = f.result()
            print(json.dumps({k: t[k] for k in ("shard", "steps", "tool_calls", "refused", "nudges", "prompt_tokens", "completion_tokens", "seconds", "ended")}), flush=True)


if __name__ == "__main__":
    main()
