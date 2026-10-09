"""research.py - STUDENT IMPLEMENTS.  The main script.   Guide: GUIDE.md, part 3.

Usage:  python research.py "survey about world model"
Result: reports/<slug>.md   reports/<slug>.sources.json   reports/<slug>.meta.json
"""
import json  # noqa: F401
import os  # noqa: F401
import re  # noqa: F401
import sys
import tempfile
import time  # noqa: F401
from collections import Counter  # noqa: F401
from collections.abc import Mapping
from pathlib import Path

from agents import FINALIZER_PATH, REPORT_PATH, SOURCES_PATH, VALIDATOR_PATH, WORKDIR, build_lead_agent  # noqa: F401
from model import make_model  # noqa: F401
from sandbox import download, open_sandbox, upload  # noqa: F401

ROOT = Path(__file__).parent
REPORTS = ROOT / "reports"
VALIDATOR_SOURCE = ROOT / "check_citations.py"
FINALIZER_SOURCE = ROOT / "finalize_citations.py"   # provided: uploaded next to your validator


def slugify(topic):
    """Turn a topic into a safe file name: lower case, runs of non-word characters become one "-", max 60 chars,
    never empty (fall back to "topic"). The topic is user input: "../../x" must not escape reports/."""
    slug = re.sub(r"\W+", "-", str(topic).strip().lower(), flags=re.UNICODE).strip("-")
    slug = slug[:60].rstrip("-")
    return slug or "topic"


def build_prompt(topic):
    """The user message sent to the lead agent."""
    return (
        "Conduct a complete deep-research run for the topic below. Follow your system workflow, including "
        "planning, parallel delegation to at least three researcher tasks, source consolidation, report writing, "
        "citation finalization, validation until OK, and a citation-checker spot check.\n\n"
        f"Research topic: {topic.strip()}"
    )


def _value(item, name, default=None):
    """Read a field from either a LangChain object or its dictionary representation."""
    if isinstance(item, Mapping):
        return item.get(name, default)
    return getattr(item, name, default)


def _tool_name(call):
    """Return a tool name from normalized or OpenAI-style tool-call data."""
    name = _value(call, "name")
    if name:
        return str(name)
    function = _value(call, "function", {})
    name = _value(function, "name")
    return str(name) if name else None


def _token_count(usage, *names):
    for name in names:
        value = _value(usage, name)
        if value is not None:
            try:
                return int(value)
            except (TypeError, ValueError):
                return 0
    return 0


def summarize(messages, elapsed, model_name):
    """Return {"model", "elapsed_s", "subagent_calls", "tool_calls": {name: count}, "tokens": {"input", "output"}}.

    PSEUDO-CODE: walk the lead's messages; for every message with tool_calls count call["name"] (subagent_calls = the
    count of "task"); add the input/output token counts from each message's usage_metadata when present.
    (Lead messages only: subagent tokens are not included, so this undercounts the real cost.)
    elapsed_s rounded to 0.1.
    """
    calls = Counter()
    input_tokens = 0
    output_tokens = 0

    for message in messages or []:
        tool_calls = _value(message, "tool_calls")
        if not tool_calls:
            additional = _value(message, "additional_kwargs", {}) or {}
            tool_calls = _value(additional, "tool_calls", []) or tool_calls
        for call in tool_calls or []:
            name = _tool_name(call)
            if name:
                calls[name] += 1

        usage = _value(message, "usage_metadata") or {}
        input_tokens += _token_count(usage, "input_tokens", "prompt_tokens")
        output_tokens += _token_count(usage, "output_tokens", "completion_tokens")

    return {
        "model": str(model_name),
        "elapsed_s": round(float(elapsed), 1),
        "subagent_calls": calls.get("task", 0),
        "tool_calls": dict(sorted(calls.items())),
        "tokens": {"input": input_tokens, "output": output_tokens},
    }


def save_outputs(backend, topic, messages, elapsed, model_name, reports_dir=REPORTS):
    """Download the report from the sandbox and write the three files into reports_dir. Return the report path.

    PSEUDO-CODE:
      files = download(backend, [REPORT_PATH, SOURCES_PATH])
      if the report is missing/empty or sources.json is missing/invalid JSON: raise RuntimeError and WRITE NOTHING
          (a failed run must never leave an empty or half-written report behind)
      write <slug>.sources.json, <slug>.meta.json (topic + summarize(...) + n_sources + source_families: the sorted
      distinct "source" values of sources.json) and <slug>.md
    """
    files = download(backend, [REPORT_PATH, SOURCES_PATH])
    report_data = files.get(REPORT_PATH)
    sources_data = files.get(SOURCES_PATH)

    if isinstance(report_data, str):
        report_data = report_data.encode("utf-8")
    if not report_data:
        raise RuntimeError("the agent did not create a report")
    try:
        report_text = report_data.decode("utf-8-sig")
    except (AttributeError, UnicodeDecodeError) as exc:
        raise RuntimeError("report.md is not valid UTF-8") from exc
    if not report_text.strip():
        raise RuntimeError("the agent created an empty report")

    if isinstance(sources_data, str):
        sources_data = sources_data.encode("utf-8")
    if not sources_data:
        raise RuntimeError("the agent did not create sources.json")
    try:
        sources = json.loads(sources_data.decode("utf-8-sig"))
    except (AttributeError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise RuntimeError("sources.json is not valid UTF-8 JSON") from exc
    if not isinstance(sources, list) or any(not isinstance(source, dict) for source in sources):
        raise RuntimeError("sources.json must contain a JSON array of source objects")

    families = sorted({source["source"] for source in sources
                       if isinstance(source.get("source"), str) and source["source"]})
    meta = {
        "topic": topic,
        **summarize(messages, elapsed, model_name),
        "n_sources": len(sources),
        "source_families": families,
    }
    meta_data = (json.dumps(meta, ensure_ascii=False, indent=2) + "\n").encode("utf-8")

    slug = slugify(topic)
    reports_dir = Path(reports_dir)
    report_path = reports_dir / f"{slug}.md"
    outputs = {
        report_path: report_data,
        reports_dir / f"{slug}.sources.json": sources_data,
        reports_dir / f"{slug}.meta.json": meta_data,
    }

    # Stage every complete file in the destination directory before replacing any published output.
    reports_dir.mkdir(parents=True, exist_ok=True)
    staged = {}
    try:
        for destination, content in outputs.items():
            descriptor, temporary = tempfile.mkstemp(prefix=f".{destination.name}.", suffix=".tmp",
                                                      dir=reports_dir)
            try:
                with os.fdopen(descriptor, "wb") as handle:
                    handle.write(content)
            except Exception:
                try:
                    os.close(descriptor)
                except OSError:
                    pass
                raise
            staged[destination] = Path(temporary)
        for destination, temporary in staged.items():
            os.replace(temporary, destination)
    finally:
        for temporary in staged.values():
            try:
                temporary.unlink(missing_ok=True)
            except OSError:
                pass

    return report_path


def _model_name(model):
    """Extract a useful, non-secret model identifier for metadata."""
    for field in ("model_name", "model"):
        value = getattr(model, field, None)
        if value:
            return str(value)
    return type(model).__name__


def main(topic):
    """Return the process exit code (0 ok, 1 failed run, 2 no topic).

    PSEUDO-CODE:
      empty topic -> print usage to stderr, return 2
      model = make_model(); start = time.monotonic()
      with open_sandbox() as backend:                # the sandbox is always cleaned up, even on errors
          backend.execute("mkdir -p <WORKDIR>/research/notes <WORKDIR>/report")
          upload(backend, {VALIDATOR_PATH: VALIDATOR_SOURCE.read_bytes(), FINALIZER_PATH: FINALIZER_SOURCE.read_bytes()})
          agent = build_lead_agent(backend, model)
          result = agent.invoke({"messages": [{"role": "user", "content": build_prompt(topic)}]},
                                config={"recursion_limit": 1000})
          save_outputs(...); on RuntimeError print "FAILED: ..." to stderr and return 1
      print where the report was saved; return 0
    """
    topic = topic.strip()
    if not topic:
        print('Usage: python research.py "<research topic>"', file=sys.stderr)
        return 2

    start = time.monotonic()
    try:
        model = make_model()
        with open_sandbox() as backend:
            setup = backend.execute(f"mkdir -p {WORKDIR}/research/notes {WORKDIR}/report")
            if getattr(setup, "exit_code", 0) != 0:
                raise RuntimeError(f"could not create sandbox directories: {getattr(setup, 'output', '')}")

            upload(backend, {
                VALIDATOR_PATH: VALIDATOR_SOURCE.read_bytes(),
                FINALIZER_PATH: FINALIZER_SOURCE.read_bytes(),
            })
            agent = build_lead_agent(backend, model)
            result = agent.invoke(
                {"messages": [{"role": "user", "content": build_prompt(topic)}]},
                config={"recursion_limit": 1000},
            )
            messages = _value(result, "messages", [])
            elapsed = time.monotonic() - start
            report_path = save_outputs(backend, topic, messages, elapsed, _model_name(model))
    except Exception as exc:
        print(f"FAILED: {exc}", file=sys.stderr)
        return 1

    print(f"Report saved to {report_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main(" ".join(sys.argv[1:])))
