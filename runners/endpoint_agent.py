#!/usr/bin/env python3
"""Work the agentic shards of a run folder with a model behind an OpenAI-compatible chat endpoint.

    python3 runners/endpoint_agent.py --run RUN_DIR --env-file .env.eval [--shards NAME ...] [--model ID]
                                      [--workers N] [--max-steps N] [--max-tokens N] [--max-images N] [--log DIR]
                                      [--temperature T] [--seed N] [--extra-json '{...}'] [--no-run-program]

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
    run_program   only in a shard with a code item whose README says "You may run your program on it with the Python
                  standard library": the program the model gave as that item's answer in answers/answers.jsonl, run
                  with the standard library only, confined to the task folder (no network, writes under work/ only),
                  with a time limit. Not offered where the program cannot be confined (see ProgramBox), nor with
                  --no-run-program. Every program run is kept whole in LOG_DIR/<shard>.programs.jsonl.

The loop keeps the model informed of its own limits, in words that say nothing about any item: the step limit (at the
start, then a line in a tool result every 10 steps and at 70% and 90% of the limit); with --max-images, that only so
many page images stay in view, which pages left view, and that what is needed from a page is to be written into
work/notes.md before another page is viewed; and when a reply reached the token limit in the middle of a tool call,
that the call was dropped and that long files are written in parts (at most 3 such recoveries a shard). Every request
carries `temperature` (--temperature, default 0), `seed` when --seed is given, and the fields of --extra-json.

Shards that hold only text items are left to runners/endpoint_text.py. A shard that already has answers/notes.md is
skipped (so an interrupted run can be started again; delete the shard's answers/ and work/ to redo it). Every step is
logged to the log folder (default RUN_DIR + "_endpoint_log"): tool calls, sizes, token counts. The token of the env
file is only ever put into the request header.
"""

import argparse
import base64
import concurrent.futures
import glob
import hashlib
import json
import math
import os
import re
import shlex
import shutil
import signal
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from endpoint_text import load_env, request_fields  # noqa: E402

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


STEPS_NOTE = """

Steps: you have at most {max_steps} steps for the whole folder. One step is one reply of yours, with all the tool calls
in it. From time to time a tool result ends with a line that says how many steps are used and how many are left."""

IMAGES_NOTE = """

Page images: at most {cap} page images stay in view at a time: when a newer image comes in, the oldest leave view, and
a page that left view is no longer in front of you. So before you view another page, write what you need from the pages
in view (figures, names, dates, boxes) into `work/notes.md` with append_file, and answer from your notes. A page can be
viewed again when your notes lack something."""

PROGRAM_NOTE = """

Code items: the README lets you run the program a code item asks for, on its data folder, with the Python standard
library. Use run_program for that. It runs the program that is your answer for that item in `answers/answers.jsonl`
(the last line with the item's id), with the arguments you give, from the task folder; the program can read the task
folder and write under `work/`, and nothing else. It is the only code there is, and it is for that program alone:
every other figure you work out yourself."""

MAX_CUT_RECOVERIES = 3  # a shard: how often a tool call cut at the token limit is dropped and the model told to write in parts
CUT_AT_LIMIT = ("Your last reply reached the token limit of one reply ({max_tokens} tokens) in the middle of a tool call ({what}), so that "
                "call was dropped: nothing of it was written or run.")
CUT_REFUSED = ("A tool call of your last reply ({what}) did not have complete JSON arguments, as happens when a reply is cut at the token "
               "limit of one reply ({max_tokens} tokens), and the service did not go on with it in the conversation, so that call was "
               "dropped: nothing of it was written or run.")
CUT_HOW = (" Make it again in smaller parts. A long file must be written in parts: the first part with write_file, each following part "
           "with append_file, every call well under the limit. append_file adds whole lines, so end each part at the end of a line "
           "(for example one line of answers/answers.jsonl in one call).")


def system_prompt(max_steps, max_images=None, program=False):
    """The system prompt of a shard: the rules, the step limit, and what holds only for this run of this shard (an image
    limit, a program that may be run)."""
    return (SYSTEM + STEPS_NOTE.format(max_steps=max_steps) + (IMAGES_NOTE.format(cap=max_images) if max_images else "")
            + (PROGRAM_NOTE if program else ""))


def left_view(names, cap):
    """The notice for page images that were taken out of the conversation because of the image limit: which pages, and
    the rule in one line."""
    return (f"[Left view: {', '.join(names)}. At most {cap} page images stay in view: write what you need from a page into "
            "work/notes.md before you view another, and answer from your notes.]")


def left_view_mark(names):
    """What stands in the conversation where page images were (the notice itself goes with the newest images)."""
    return f"[page images that left view: {', '.join(names)}]"


def budget_line(step, max_steps, kind):
    """A line about the step budget, put at the end of a tool result. kind 1: the count (every 10 steps); 2: at 70% of
    the limit; 3: at 90%."""
    count = f"steps: {step} of {max_steps} used, {max_steps - step} left"
    if kind == 3:
        return f"[{count}. Write all your answers now, then finish as the README says.]"
    if kind == 2:
        return f"[{count}. Make sure an answer file exists now for every item you have already worked out.]"
    return f"[{count}]"


def budget_kind(step, max_steps):
    """Which budget line is due at this step: 0 none, 1 the count, 2 the 70% line, 3 the 90% line."""
    if step == math.ceil(0.9 * max_steps):
        return 3
    if step == math.ceil(0.7 * max_steps):
        return 2
    return 1 if step % 10 == 0 else 0


def _fn(name, description, properties, required):
    return {"type": "function", "function": {"name": name, "description": description,
                                             "parameters": {"type": "object", "properties": properties, "required": required}}}


TOOLS = [
    _fn("list_files", "List the files of the task folder, or of one sub-folder of it.",
        {"path": {"type": "string", "description": "a folder, relative to the task folder; default the task folder"}}, []),
    _fn("read_file", "Read a text file of the task folder. Long files come in pages of at most 400 lines and 60,000 characters; "
                     "the result says how to get the next page.",
        {"path": {"type": "string"}, "page": {"type": "integer", "description": "1 for the first page (default), 2 for the next, ..."}}, ["path"]),
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
RUN_PROGRAM = _fn("run_program", "Run the program you wrote for a code item, as the README allows: the program that is your answer for that "
                  "item in answers/answers.jsonl (the last line with its id), with the Python standard library, from the task folder. "
                  "It can read the task folder and write under work/ only; it has no network. You get what it prints.",
                  {"item": {"type": "string", "description": "the id of the code item"},
                   "args": {"type": "array", "items": {"type": "string"},
                            "description": "the program's arguments, in order, as the item says the program is run; paths are relative to the task folder"}},
                  ["item"])
NEEDS_PYPDF = {"pdf_tool.py", "check_answers.py"}
PAGE_LINES, PAGE_CHARS = 400, 60000  # read_file: the most lines and the most characters of one page
RUN_SENTENCE = "You may run your program on it with the Python standard library."  # the README sentence run_program rests on
PROGRAM_SECONDS = 60


def text_pages(text):
    """The text in pages of at most PAGE_LINES lines and PAGE_CHARS characters, so that every character of a file is on
    some page. A file of ordinary lines comes in pages of 400 whole lines, as it always did; a page that would be longer
    than PAGE_CHARS ends earlier, and a line longer than a page goes over several pages.
    Each page: {text, first (number of its first line), starts_mid, ends_mid (it begins or stops inside a line)}."""
    pages, cur, size, first, mid = [], [], 0, 1, False

    def close(ends_mid, next_first):
        nonlocal cur, size, first, mid
        pages.append({"text": "\n".join(cur), "first": first, "starts_mid": mid, "ends_mid": ends_mid})
        cur, size, first, mid = [], 0, next_first, ends_mid

    for no, line in enumerate(text.splitlines(), 1):
        while True:
            need = len(line) + (1 if cur else 0)
            if cur and (len(cur) >= PAGE_LINES or size + need > PAGE_CHARS):
                close(False, no)
            elif len(line) > PAGE_CHARS:  # the page is empty here: fill it with the start of the line
                cur, line = [line[:PAGE_CHARS]], line[PAGE_CHARS:]
                close(True, no)
            else:
                cur.append(line)
                size += need
                break
    if cur or not pages:
        close(False, None)
    return pages


class ProgramBox:
    """Where run_program runs a model's program: the interpreter of this runner with `-I -S` (standard library only), an
    empty environment, a time limit, a cap on the size of a file it writes, and a deny-by-default sandbox-exec profile
    (macOS), after the local runner of harness/qandy_eval/trading/sandbox.py: no network, no other program, reads only of
    the task folder, the interpreter's own installation and the system libraries, writes only under the task folder's
    work/. On a machine without sandbox-exec, or where the self-test fails, there is no box and run_program is not
    offered: a model's program is never run unconfined."""

    SYSTEM_READS = ("/System/Library", "/System/Volumes/Preboot/Cryptexes", "/System/Cryptexes", "/usr/lib", "/usr/share/icu",
                    "/private/var/db/dyld", "/Library/Apple/System")

    def __init__(self):
        self.sandbox_exec = shutil.which("sandbox-exec")
        self.python = os.path.realpath(getattr(sys, "_base_executable", None) or sys.executable)
        self.prefix = os.path.realpath(sys.base_prefix)
        self.roots = self._roots()

    def _roots(self):
        """Folders the interpreter reads besides the system libraries: its installation and the folders of the shared
        libraries it and its extension modules link to (otool); without otool, Homebrew's library folders."""
        roots = {self.prefix}
        binaries = [self.python, *glob.glob(os.path.join(self.prefix, "lib", "python*", "lib-dynload", "*.so")),
                    *(b for b in (os.path.join(self.prefix, "Python"),) if os.path.isfile(b))]
        skip = tuple(q + "/" for q in (self.prefix, *self.SYSTEM_READS, "/System"))
        try:
            if not shutil.which("otool") or subprocess.run(["xcode-select", "-p"], capture_output=True, timeout=10).returncode:
                raise OSError("no otool")
            todo = binaries
            for _ in range(4):
                if not todo:
                    break
                out = subprocess.run(["otool", "-L", *todo], capture_output=True, text=True, timeout=60).stdout
                todo = []
                for line in out.splitlines():
                    lib = line.strip().split(" (")[0]
                    if not line.startswith("\t") or not lib.startswith("/") or not os.path.exists(lib):
                        continue
                    real = os.path.realpath(lib)
                    if real.startswith(skip) or os.path.dirname(real) in roots:
                        continue
                    roots.add(os.path.dirname(real))
                    todo.append(real)
        except (OSError, subprocess.SubprocessError):
            for brew in ("/opt/homebrew", "/usr/local"):
                if self.prefix.startswith(brew + "/"):
                    roots.update(q for q in (f"{brew}/Cellar", f"{brew}/opt", f"{brew}/lib") if os.path.isdir(q))
        return tuple(sorted(roots))

    def profile(self, folder):
        def q(path):
            return '"' + str(path).replace("\\", "\\\\").replace('"', '\\"') + '"'
        reads = " ".join(f"(subpath {q(r)})" for r in (folder, *self.roots, *self.SYSTEM_READS))
        return f"""(version 1)
(deny default)
(allow process-exec (literal {q(self.python)}))
(allow process-exec (subpath {q(self.prefix)}))
(allow file-read-metadata)
(allow file-read* {reads} (literal "/") (literal "/dev/null") (literal "/dev/urandom") (literal "/dev/random") (literal "/dev/dtracehelper"))
(allow file-write* (subpath {q(Path(folder) / "work")}) (literal "/dev/null") (literal "/dev/dtracehelper"))
(allow file-ioctl (literal "/dev/dtracehelper"))
(allow sysctl-read)
(allow signal (target self))
"""

    def run(self, folder, script, args, seconds=PROGRAM_SECONDS):
        """Run `script` (a path relative to `folder`) there with `args`: (exit code or None if stopped at the time limit,
        what it printed, what it wrote to stderr, seconds). The output goes to files of this runner, capped like any
        file the program writes (64 MB), and the first 200,000 characters of each are read back."""
        cmd = ["/bin/sh", "-c", 'ulimit -f 131072; ulimit -c 0; exec "$@"', "sh",
               self.sandbox_exec, "-p", self.profile(folder), self.python, "-I", "-S", script, *args]
        started = time.time()
        with tempfile.TemporaryFile() as out, tempfile.TemporaryFile() as err:
            proc = subprocess.Popen(cmd, cwd=folder, env={}, stdin=subprocess.DEVNULL, stdout=out, stderr=err, start_new_session=True)
            try:
                code = proc.wait(timeout=seconds)
            except subprocess.TimeoutExpired:
                code = None
                try:
                    os.killpg(proc.pid, signal.SIGKILL)
                except OSError:
                    proc.kill()
                proc.wait()
            texts = []
            for f in (out, err):
                f.seek(0)
                texts.append(f.read(800000).decode("utf-8", "replace")[:200000])
        return code, texts[0], texts[1], round(time.time() - started, 1)

    @classmethod
    def ready(cls):
        """(a box, "") when a program can be confined on this machine and the self-test shows it, else (None, why)."""
        if sys.platform != "darwin" or not shutil.which("sandbox-exec"):
            return None, "this machine has no sandbox-exec (macOS) to confine a program"
        test = ("import sys, socket\n"
                "print('read', open('inside.txt').read().strip())\n"
                "open('work/out.txt', 'w').write('x'); print('write work ok')\n"
                "for name, act in (('write outside work', lambda: open('made.txt', 'w')), ('read outside', lambda: open(sys.argv[1]).read()),\n"
                "                  ('network', lambda: socket.create_connection(('127.0.0.1', 9), 2)),\n"
                "                  ('other program', lambda: __import__('subprocess').run(['/bin/ls']))):\n"
                "    try:\n        act(); print(name, 'ALLOWED')\n    except Exception as e:\n        print(name, 'refused' if isinstance(e, PermissionError) else type(e).__name__)\n")
        folder = Path(tempfile.mkdtemp(prefix="qandy-run-program-")).resolve()
        try:
            box = cls()
            (folder / "work").mkdir()
            (folder / "inside.txt").write_text("yes\n", encoding="utf-8")
            (folder / "work" / "selftest.py").write_text(test, encoding="utf-8")
            code, out, err, _ = box.run(str(folder), "work/selftest.py", [str(Path(__file__).resolve())], seconds=30)
            want = ["read yes", "write work ok", "write outside work refused", "read outside refused", "network refused", "other program refused"]
            if code == 0 and out.split("\n")[:len(want)] == want and not (folder / "made.txt").exists():
                return box, ""
            return None, f"the sandbox self-test did not pass (exit {code}): {(out + err)[-300:].strip()!r}"
        except (OSError, subprocess.SubprocessError) as e:
            return None, f"the sandbox could not be started ({type(e).__name__}: {e})"
        finally:
            shutil.rmtree(folder, ignore_errors=True)


class Refused(Exception):
    pass


def code_items(folder):
    """The ids of a shard's code items (`env.type: code`), if its README lets the solver run its program (RUN_SENTENCE);
    otherwise none."""
    try:
        readme = " ".join((Path(folder) / "README.md").read_text(encoding="utf-8").split())
        rows = [json.loads(l) for l in (Path(folder) / "items.jsonl").read_text(encoding="utf-8").splitlines() if l.strip()]
    except (OSError, ValueError):
        return set()
    if RUN_SENTENCE not in readme:
        return set()
    return {r["id"] for r in rows if isinstance(r, dict) and isinstance(r.get("id"), str)
            and isinstance(r.get("env"), dict) and r["env"].get("type") == "code"}


class Shard:
    """The tools, bound to one shard folder."""

    def __init__(self, folder, box=None):
        self.dir = Path(folder).resolve()
        self.box = box
        self.code_items = code_items(self.dir) if box else set()  # the items run_program may be used for; empty: no such tool

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
        pages = text_pages(target.read_text(encoding="utf-8", errors="replace"))
        page = max(1, int(page or 1))
        if page > len(pages):
            return f"[{path}, page {page} of {len(pages)}]\n(there is no page {page}: the file has {len(pages)})"
        part = pages[page - 1]
        head = f"[{path}, page {page} of {len(pages)}" + (f": it goes on in the middle of line {part['first']}" if part["starts_mid"] else "") + "]"
        if page == len(pages):
            return f"{head}\n{part['text']}"
        where = f" and stops in the middle of line {pages[page]['first']}" if part["ends_mid"] else ""
        return f"{head}\n{part['text']}\n... (page {page} of {len(pages)} ends here{where}: call read_file with page {page + 1} for what follows)"

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
        if tool in ("write_file", "append_file", "read_file", "list_files", "view_image", "view_pdf") or (tool == "run_program" and self.code_items):
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

    def run_program(self, item, args=None):
        """(what the model gets, a record for the log): the program that is the item's answer, run in the box."""
        if not self.code_items:
            raise Refused("there is no tool run_program")
        if item not in self.code_items:
            raise Refused(f"{item!r} is not a code item of this folder (code items: {', '.join(sorted(self.code_items))}); only the program of a code item can be run")
        args = [] if args is None else args
        if not isinstance(args, list) or not all(isinstance(a, str) for a in args):
            raise Refused("args must be a list of strings")
        for a in args:
            if re.match(r"[a-z][a-z0-9+.-]*://", a, re.I):
                raise Refused(f"{a[:80]}: the program has no network")
            if "/" in a or a.startswith(".."):
                self.path(a)  # a path argument must stay inside the folder
        source, unreadable = None, 0
        try:
            lines = (self.dir / "answers" / "answers.jsonl").read_text(encoding="utf-8").splitlines()
        except OSError:
            lines = []
        for line in lines:
            if not line.strip():
                continue
            try:
                row = json.loads(line)
            except json.JSONDecodeError:
                unreadable += 1
                continue
            if isinstance(row, dict) and row.get("id") == item:
                source = (row.get("answer") or {}).get("program") if isinstance(row.get("answer"), dict) else None
        if not isinstance(source, str) or not source.strip():
            raise Refused(f"answers/answers.jsonl holds no program for {item} yet" + (f" ({unreadable} of its lines are not JSON)" if unreadable else "")
                          + ': first answer the item as the README says, {"id": "<item id>", "answer": {"program": "<the whole source>"}}, then run it')
        folder = self.dir / "work" / ".run_program"
        script = folder / (re.sub(r"[^A-Za-z0-9._-]", "_", item) + ".py")
        folder.mkdir(parents=True, exist_ok=True)
        try:
            script.write_text(source, encoding="utf-8")
            code, out, err, seconds = self.box.run(str(self.dir), script.relative_to(self.dir).as_posix(), args)
        finally:
            shutil.rmtree(folder, ignore_errors=True)
        text = out + (("\n[stderr]\n" + err) if err.strip() else "")
        if len(text) > 40000:
            text = text[:40000] + f"\n... ({len(text) - 40000} more characters: make the program print less)"
        if code is None:
            end = f"[stopped: the program did not finish within {PROGRAM_SECONDS} seconds]"
        else:
            end = f"[exit code {code}, {seconds} s]"
        if "Operation not permitted" in err:
            end += "\n(the program may read the task folder and write under work/ only, and it has no network)"
        record = {"item": item, "args": args, "sha256": hashlib.sha256(source.encode("utf-8")).hexdigest(), "source": source,
                  "exit": code, "seconds": seconds}
        return (text.strip() + "\n" + end).strip(), record

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
            text, calls, finish, usage, provider, thought = [], {}, None, None, None, 0
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
                        piece = delta.get("reasoning_content") or delta.get("reasoning")  # reasoning sent beside the reply: counted, not kept
                        thought += len(piece) if isinstance(piece, str) else 0
                        for call in delta.get("tool_calls") or []:
                            slot = calls.setdefault(call.get("index", 0), {"id": None, "name": "", "arguments": ""})
                            slot["id"] = call.get("id") or slot["id"]
                            fn = call.get("function") or {}
                            slot["name"] += fn.get("name") or ""
                            slot["arguments"] += fn.get("arguments") or ""
                        finish = choice.get("finish_reason") or finish
            if finish is None and not text and not calls:
                raise RuntimeError("the stream ended with nothing in it")
            return {"content": "".join(text), "tool_calls": [calls[k] for k in sorted(calls)], "finish_reason": finish, "usage": usage,
                    "provider": provider, "reasoning_chars": thought}
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


def trim(messages, keep_last=12, shown=None, cap=None):
    """Make room: earlier images are taken out (they can be viewed again) and long old tool results are cut. With an
    image limit (`cap`) the notice is the limit's own: which pages left view, and the rule about notes."""
    for m in messages[:-keep_last]:
        if m["role"] == "user" and isinstance(m["content"], list):
            names = (shown or {}).pop(id(m), None)
            m["content"] = (left_view(names or ["the images shown here"], cap) if cap
                            else "[images shown earlier were removed to save space; view them again if you need them]")
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


def cap_images(messages, cap, shown=None):
    """Some services take only a few images in one request: keep at most `cap` image blocks in the whole conversation,
    taking out the oldest first (the model can view them again). `shown`: {id of a message: the pages its images
    show}. Where the images were, a mark names them; the names of all that left are returned, for the notice."""
    def count(m):
        return sum(1 for b in m["content"] if isinstance(b, dict) and b.get("type") == "image_url") \
            if m["role"] == "user" and isinstance(m["content"], list) else 0
    total, gone = sum(count(m) for m in messages), []
    for m in messages[:-1]:
        if total <= cap:
            break
        n = count(m)
        if n:
            names = (shown or {}).pop(id(m), None) or [f"{n} image(s) shown earlier"]
            m["content"] = left_view_mark(names)
            gone += names
            total -= n
    return gone


def drop_calls(messages, at, ids):
    """Take the tool calls `ids` of the assistant message at index `at`, and their results after it, out of the
    conversation. An assistant message left without a call becomes a plain one."""
    turn = messages[at]
    kept = [c for c in turn.get("tool_calls") or [] if c["id"] not in ids]
    if kept:
        turn["tool_calls"] = kept
    else:
        turn.pop("tool_calls", None)
        turn["content"] = turn.get("content") or "(no text)"
    messages[at + 1:] = [m for m in messages[at + 1:] if not (m.get("role") == "tool" and m.get("tool_call_id") in ids)]


def is_json(text):
    try:
        json.loads(text or "{}")
        return True
    except json.JSONDecodeError:
        return False


def cut_note(calls, max_tokens, at_limit=True):
    """The message after a reply that was cut inside a tool call: which call, and how to go on. `at_limit`: the reply
    is known to have reached the token limit; otherwise the service refused the conversation that held the call."""
    what = []
    for c in calls:
        path = re.search(r'"path"\s*:\s*"((?:[^"\\]|\\.)*)"', c["arguments"] or "")
        what.append((c["name"] or "a tool call") + (f" for {path.group(1)}" if path else ""))
    return (CUT_AT_LIMIT if at_limit else CUT_REFUSED).format(max_tokens=max_tokens, what=", ".join(what) or "a tool call") + CUT_HOW


def say(messages, text):
    """A user message at the end of the conversation, joined to the user message that is already there (images, a
    notice), so that two user messages do not follow each other."""
    last = messages[-1]
    if last["role"] == "user" and isinstance(last["content"], list):
        last["content"].append({"type": "text", "text": text})
    elif last["role"] == "user":
        last["content"] += "\n\n" + text
    else:
        messages.append({"role": "user", "content": text})


def solve(shard_dir, base, token, model, log_dir, max_steps, max_tokens, window, extra=None, max_images=None, box=None):
    shard = Shard(shard_dir, box)
    name = shard.dir.name
    log = open(Path(log_dir) / f"{name}.steps.jsonl", "a", encoding="utf-8")
    tools = TOOLS + ([RUN_PROGRAM] if shard.code_items else [])
    messages = [{"role": "system", "content": system_prompt(max_steps, max_images, bool(shard.code_items))},
                {"role": "user", "content": "Begin. The task folder holds:\n" + shard.list_files(".")[:6000]
                 + "\n\nStart by calling read_file with path README.md. You know nothing about the task until you have read "
                   "README.md, items.jsonl and the documents of each item, so do not answer before that."}]
    totals = {"shard": name, "steps": 0, "prompt_tokens": 0, "completion_tokens": 0, "tool_calls": 0, "refused": 0, "nudges": 0,
              "cut_recoveries": 0, "ended": None}
    force = True  # the first turn must be a tool call (if the endpoint takes tool_choice)
    shown = {}  # id of a message with images -> the pages they show, for the notice when they leave view
    due = 0  # the step-budget line that waits for a tool result to end (budget_kind)
    suspect = None  # (index of the last assistant message, ids of its calls with broken arguments, those calls)
    started = time.time()
    for step in range(1, max_steps + 1):
        due = max(due, budget_kind(step, max_steps))
        try:
            body = {"model": model, "messages": messages, "tools": tools, "max_tokens": max_tokens, **(extra or {})}
            if force and step == 1:
                try:
                    reply = chat(base, token, dict(body, tool_choice="required"), tries=1)
                except RuntimeError:
                    force = False
                    reply = chat(base, token, body)
            else:
                reply = chat(base, token, body)
        except RuntimeError as e:
            if suspect and str(e).startswith("HTTP 400") and totals["cut_recoveries"] < MAX_CUT_RECOVERIES:
                # the service refuses the conversation since a reply whose tool call had broken arguments: that call is
                # taken out, the model is told to make it again in parts, and the shard goes on
                at, ids, calls = suspect
                drop_calls(messages, at, ids)
                say(messages, cut_note(calls, max_tokens, at_limit=False))
                totals["cut_recoveries"] += 1
                totals["steps"] = step
                suspect = None
                log.write(json.dumps({"step": step, "recovered": "HTTP 400 after a tool call with broken arguments: the call was dropped",
                                      "error": str(e)[:300]}, ensure_ascii=False) + "\n")
                log.flush()
                continue
            totals["ended"] = f"endpoint error: {e}"
            break
        suspect = None
        usage = reply.get("usage") or {}
        totals["steps"] = step
        totals["prompt_tokens"] += usage.get("prompt_tokens") or 0
        totals["completion_tokens"] += usage.get("completion_tokens") or 0
        record = {"step": step, "usage": usage, "provider": reply.get("provider"), "finish_reason": reply["finish_reason"], "calls": [], "text": reply["content"][:2000]}
        if reply.get("reasoning_chars"):
            record["reasoning_chars"] = reply["reasoning_chars"]
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
        # A reply that reached the token limit in the middle of a tool call leaves a call whose arguments are not whole
        # JSON. Kept in the conversation it makes some services refuse the next request (HTTP 400), and the model does not
        # learn why the call failed. So that call is dropped and the model is told to make it again in parts. Some
        # services give `tool_calls`, not `length`, as the finish reason of such a reply: the token count shows it too.
        calls = [(c, c["id"] or f"call_{step}_{n}") for n, c in enumerate(reply["tool_calls"])]
        broken = [i for c, i in calls if not is_json(c["arguments"])]
        at_limit = reply["finish_reason"] == "length" or (usage.get("completion_tokens") or 0) >= max_tokens
        cut = broken if at_limit and totals["cut_recoveries"] < MAX_CUT_RECOVERIES else []  # ids of the calls that are dropped
        kept = [(c, i) for c, i in calls if i not in cut]
        if kept:
            messages.append({"role": "assistant", "content": reply["content"] or None,
                             "tool_calls": [{"id": i, "type": "function", "function": {"name": c["name"], "arguments": valid_json(c["arguments"])}}
                                            for c, i in kept]})
        else:
            messages.append({"role": "assistant", "content": reply["content"] or "(no text)"})
        turn = len(messages) - 1
        images, names, last_result = [], [], None
        for call, call_id in calls:
            if call_id in cut:
                record["calls"].append({"name": call["name"], "arguments": call["arguments"][:1500], "result_chars": 0,
                                        "result_start": "dropped: the reply reached the token limit inside this call", "dropped": True})
                continue
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
                    names += [str(p) for p in paths[:per]]
                    result = f"{len(blocks)} image(s) follow in the next message" + (f"; only the first {per} were taken, view the others in another call" if len(paths) > per else "")
                elif call["name"] == "view_pdf":
                    result, block = shard.view_pdf(a.get("path"))
                    if block:
                        images += [{"type": "text", "text": f"First page of {a.get('path')}:"}, block]
                        names.append(f"{a.get('path')} (first page)")
                        result += "\n(the first page follows as an image in the next message)"
                elif call["name"] == "run_tool":
                    result = shard.run_tool(a.get("tool"), a.get("args", []))
                elif call["name"] in ("write_file", "append_file"):
                    result = shard.write(a.get("path"), a.get("content"), append=call["name"] == "append_file")
                elif call["name"] == "run_program" and shard.code_items:
                    result, ran = shard.run_program(a.get("item"), a.get("args"))
                    with open(Path(log_dir) / f"{name}.programs.jsonl", "a", encoding="utf-8") as f:  # every program that was run, whole, for the audit
                        f.write(json.dumps(dict(ran, step=step), ensure_ascii=False) + "\n")
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
            last_result = {"role": "tool", "tool_call_id": call_id, "content": result}
            messages.append(last_result)
        if due and last_result is not None:  # the step budget, at the end of this step's last tool result
            record["budget_line"] = budget_line(step, max_steps, due)
            last_result["content"] += "\n\n" + record["budget_line"]
            due = 0
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
                names = names[:max_images]
            images = kept
        if images:
            message = {"role": "user", "content": images}
            messages.append(message)
            shown[id(message)] = names
            if max_images:
                gone = [g for g in cap_images(messages, max_images, shown) if g not in names]  # not those that have just come in again
                if gone:  # said where the model looks next: with the images that have just come in
                    message["content"].append({"type": "text", "text": left_view(gone, max_images)})
                    record["left_view"] = gone
        if cut:
            say(messages, cut_note([c for c, i in calls if i in cut], max_tokens))
            totals["cut_recoveries"] += 1
            record["recovered"] = "a tool call cut at the token limit was dropped"
        rest = {i for i in broken if i not in cut}  # broken calls that stay in the conversation, with {} as arguments
        if rest:
            suspect = (turn, rest, [c for c, i in calls if i in rest])
        log.write(json.dumps(record, ensure_ascii=False) + "\n")
        log.flush()
        if (usage.get("prompt_tokens") or 0) > window:
            trim(messages, shown=shown, cap=max_images)
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
    ap.add_argument("--temperature", type=float, default=0.0, help="sampling temperature, sent with every request (default 0)")
    ap.add_argument("--seed", type=int, help="sampling seed, sent with every request when given")
    ap.add_argument("--extra-json", help="more request fields as a JSON object, merged into every request")
    ap.add_argument("--thinking-budget", type=int, help="cap on reasoning tokens per step, sent as thinking_token_budget (counts toward --max-tokens)")
    ap.add_argument("--no-run-program", action="store_true", help="do not offer run_program, also where a shard's README lets the solver run the program of a code item")
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
    extra = request_fields(args.temperature, args.seed, args.thinking_budget, args.extra_json)
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
    print(f"request fields: {json.dumps(extra, ensure_ascii=False)}; max_tokens {args.max_tokens}; max_steps {args.max_steps}; "
          f"max_images {args.max_images or 'no limit'}", flush=True)
    box, with_code = None, [s.name for s in todo if code_items(s)]
    if with_code:  # shards whose README lets the solver run the program of a code item
        box, why = (None, "--no-run-program") if args.no_run_program else ProgramBox.ready()
        print(f"run_program in {', '.join(with_code)}: " + ("offered (the sandbox self-test passed)" if box else f"not offered: {why}"), flush=True)
    with concurrent.futures.ThreadPoolExecutor(max_workers=args.workers) as pool:
        futures = [pool.submit(solve, s, base, token, model, log_dir, args.max_steps, args.max_tokens, args.window,
                               extra, args.max_images, box) for s in todo]
        for f in concurrent.futures.as_completed(futures):
            t = f.result()
            print(json.dumps({k: t[k] for k in ("shard", "steps", "tool_calls", "refused", "nudges", "cut_recoveries", "prompt_tokens",
                                                "completion_tokens", "seconds", "ended")}), flush=True)


if __name__ == "__main__":
    main()
