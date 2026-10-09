"""check_citations.py - STUDENT IMPLEMENTS `check`.   Runs INSIDE the sandbox (standard library only).

research.py uploads this file to the sandbox and the lead agent runs it with the `execute` tool:
    python3 /tmp/work/research/check_citations.py [report.md] [sources.json]
It must exit 0 and print "OK: ..." when the report is consistent, else print each problem and exit 1.
"""
import json
import re
import sys

REPORT = "/tmp/work/report/report.md"
SOURCES = "/tmp/work/research/sources.json"

_REF_HEADING = re.compile(r"(?m)^##[ \t]+References[ \t]*$")
_CODE = re.compile(r"(```.*?```|~~~.*?~~~|`[^`\n]*`)", re.DOTALL)
_CITATION_GROUP = re.compile(
    r"\[(\d+(?:\s*(?:,|[-–])\s*\d+)*)\](?!\()"
)
_REFERENCE_LINE = re.compile(r"^[ \t]*\[(\d+)\](?!\()")
_URL = re.compile(r"https?://\S+")


def _citation_numbers(group):
    """Expand the contents of a citation group into individual numbers."""
    numbers = []
    for item in re.split(r"\s*,\s*", group):
        span = re.fullmatch(r"(\d+)\s*[-–]\s*(\d+)", item)
        if span:
            start, end = map(int, span.groups())
            if start <= end:
                numbers.extend(range(start, end + 1))
            else:
                # A reversed range is not a meaningful grouped citation.  Keep
                # both endpoints so the normal resolution checks still apply.
                numbers.extend((start, end))
        else:
            numbers.append(int(item))
    return numbers


def _without_code(text):
    """Remove fenced and inline code before looking for citations."""
    return _CODE.sub("", text)


def check(report_text, sources):
    """Return a list of problem strings (empty list = OK).

    PSEUDO-CODE:
      problems = []
      if sources is empty: return ["no sources in sources.json"]
      for each source entry:
          n must be an int                       -> problem if not
          url must start with http:// or https://-> problem if not
          the same url must not appear twice     -> problem if duplicated
      split report_text at the heading "## References":
          body = text before it; if the heading is missing -> problem
      cited = set of numbers found as [n] in the BODY only (not in the reference list; use a regex)
      every number in `cited` must exist in sources -> problem "[n] cited but missing from sources.json"
      every source number must be in `cited`        -> problem "source [n] never cited"
      the lines of the References section that start with "[n]" (regex) are the reference lines:
          every source needs exactly ONE reference line (none missing, no number twice, no number that is not a source)
          each reference line holds exactly ONE http(s) URL and it must equal that source's url
          (a line bundling several sources under one number is a problem)
      return problems
    """
    problems = []

    if not isinstance(sources, list):
        return ["sources.json must be a JSON list"]
    if not sources:
        return ["no sources in sources.json"]

    by_number = {}
    seen_urls = {}
    for index, source in enumerate(sources):
        label = f"source at index {index}"
        if not isinstance(source, dict):
            problems.append(f"{label} must be an object")
            continue

        number = source.get("n")
        url = source.get("url")
        if not isinstance(number, int) or isinstance(number, bool):
            problems.append(f"{label} has non-integer n={number!r}")
        elif number in by_number:
            problems.append(f"source [{number}] appears more than once in sources.json")
        else:
            by_number[number] = source

        if not isinstance(url, str) or not url.startswith(("http://", "https://")):
            problems.append(f"source n={number!r} has invalid url={url!r}")
        elif url in seen_urls:
            problems.append(
                f"source n={number!r} duplicates url from source "
                f"n={seen_urls[url]!r}: {url}"
            )
        else:
            seen_urls[url] = number

    heading = _REF_HEADING.search(report_text)
    if heading is None:
        problems.append("report is missing the '## References' heading")
        body = report_text
        references = ""
    else:
        body = report_text[:heading.start()]
        references = report_text[heading.end():]

    cited = set()
    for match in _CITATION_GROUP.finditer(_without_code(body)):
        cited.update(_citation_numbers(match.group(1)))

    for number in sorted(cited):
        if number not in by_number:
            problems.append(f"[{number}] cited but missing from sources.json")
    for number in sorted(by_number):
        if number not in cited:
            problems.append(f"source [{number}] never cited")

    reference_lines = {}
    for line in references.splitlines():
        match = _REFERENCE_LINE.match(line)
        if match:
            reference_lines.setdefault(int(match.group(1)), []).append(line)

    for number in sorted(reference_lines):
        lines = reference_lines[number]
        if number not in by_number:
            problems.append(f"reference [{number}] has no source in sources.json")
        if len(lines) > 1:
            problems.append(f"reference [{number}] appears more than once")

    for number in sorted(by_number):
        lines = reference_lines.get(number, [])
        if not lines:
            problems.append(f"source [{number}] has no reference line")
            continue

        # Check every duplicate line as well, so validation reports all bad
        # URLs instead of hiding them behind the duplicate-number problem.
        expected_url = by_number[number].get("url")
        for line in lines:
            urls = _URL.findall(line)
            if len(urls) != 1:
                problems.append(
                    f"reference [{number}] must contain exactly one http(s) URL"
                )
            elif urls[0] != expected_url:
                problems.append(
                    f"reference [{number}] URL {urls[0]!r} does not match "
                    f"sources.json URL {expected_url!r}"
                )

    return problems


def main(argv):
    report_path = argv[1] if len(argv) > 1 else REPORT
    sources_path = argv[2] if len(argv) > 2 else SOURCES
    try:
        with open(report_path, encoding="utf-8") as f:
            report = f.read()
        with open(sources_path, encoding="utf-8") as f:
            sources = json.load(f)
    except (OSError, ValueError) as exc:
        print(f"cannot read inputs: {exc}")
        return 1
    problems = check(report, sources)
    if problems:
        print("\n".join(problems))
        return 1
    print(f"OK: {len(sources)} sources, all citations resolve")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
