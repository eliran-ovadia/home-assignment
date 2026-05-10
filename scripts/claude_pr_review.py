#!/usr/bin/env python3
"""Claude-powered PR review agent.

Runs in GitHub Actions on every pull request. Reads CLAUDE.md, docs/SPEC.md,
assignment/Final_Assignment.md, and docs/SCORE.md as cached prompt blocks (so
repeated PRs pay the cache-write cost only once per cache TTL), fetches the git
diff, and posts a structured review as a PR comment.
"""
import os
import subprocess
import sys
from pathlib import Path

import anthropic
import httpx

REPO_ROOT = Path(__file__).parent.parent
MAX_DIFF_CHARS = 80_000
MODEL = "claude-sonnet-4-6"


def load_file(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except FileNotFoundError:
        return f"[file not found: {path}]"


def get_pr_diff(base_sha: str, head_sha: str) -> tuple[str, bool]:
    result = subprocess.run(
        ["git", "diff", f"{base_sha}...{head_sha}"],
        capture_output=True,
        text=True,
        cwd=REPO_ROOT,
    )
    try:
        result.check_returncode()
    except subprocess.CalledProcessError as exc:
        print(
            f"git diff failed (exit {result.returncode}):\n{result.stderr}",
            file=sys.stderr,
        )
        raise SystemExit(1) from exc

    diff = result.stdout
    truncated = len(diff) > MAX_DIFF_CHARS
    if truncated:
        diff = diff[:MAX_DIFF_CHARS] + "\n\n[diff truncated — showing first 80,000 characters]"
    return diff, truncated


def build_review_prompt(pr_title: str, pr_body: str, diff: str) -> str:
    # Wrap the PR body in XML tags so adversarial content cannot escape into
    # the instruction context (prompt-injection mitigation).
    safe_body = f"<pr_body>\n{pr_body or '(none)'}\n</pr_body>"

    return f"""You are reviewing a pull request for the Lumina Capital Transactions Platform.

PR Title: {pr_title}
PR Description: {safe_body}

Git diff:
```diff
{diff}
```

Provide a structured review with these exact sections:

## Assignment Coverage
Which Part(s) of the assignment (A–H) does this PR address?
- Part A: Data Ingestion & Validation
- Part B: Backend API endpoints
- Part C: Business Logic (FIFO cost basis, realised/unrealised P&L)
- Part D: Rule Violations (day trading, risk concentration, sell-before-buy, invalid values)
- Part E: Storage (ORM models, Alembic migrations, repositories)
- Part F: Analytics (top ISINs, average holding time, most volatile client, ISIN concentration)
- Part G: Frontend (file upload, positions table, violations table, analytics section)
- Part H: Testing (API endpoint tests, business-logic unit tests)
State for each touched part whether its requirements are fully satisfied, partially addressed, \
or missing, and be specific about what is absent.

## Summary
One paragraph overview of what this PR does.

## Spec Alignment
Does the implementation match docs/SPEC.md and the assignment requirements? Call out any \
deviations, missing pieces, or additions beyond scope.

## Score Assessment
docs/SCORE.md tracks project scores (1–10) across ten evaluation criteria. \
For each criterion this diff materially affects, produce one row:

| Criterion | Current | Verdict | Evidence | Suggested |
|-----------|---------|---------|----------|-----------|

Verdict must be one of **Agree**, **Disagree**, or **Cannot assess from diff alone**.
Evidence must reference a specific diff line or file. Suggested is the score you would \
assign given this diff (leave unchanged or propose a new value with a one-clause reason).

Criteria and their current scores for reference:
- System Design: 9.5 (Spec phase)
- AI Usage: 9.0 (Spec phase)
- Problem Solving: 9.0 (Spec phase)
- Documentation: 9.0 (Spec phase)
- DevOps & Tooling: 9.5 (Spec phase)
- Bonus Coverage: 9.5 (Spec phase)
- Code Quality: — (not yet scored — propose a score only if this diff introduces \
enough implementation to judge)
- Test Coverage: — (not yet scored — propose a score only if tests are present)
- Execution: 9.0 (Spec phase)
- Assignment Compliance: 9.5 (Spec phase)

Do not list criteria this diff does not touch. \
End with a single line: **Overall: current 9.3 → suggested X.X** and one sentence on \
whether the aggregate should move and why.

## Security
- Input boundary validation: Excel/file upload handling — flag zip-bomb risk, \
formula injection via openpyxl, and missing file-type or size guards.
- SQL safety: parameterised queries only — flag any f-string or %-format SQL concatenation.
- Authentication & authorisation: can a request without a valid X-Session-Token header \
access or mutate another user's data? Check every route that reads from the DB.
- Information disclosure: are internal errors, stack traces, or raw DB primary keys \
exposed in API error responses?
- Session token generation: are UUIDs produced with a cryptographically secure source \
(e.g. `secrets` module or `uuid4`)?
- Prompt injection: if any AI-facing feature is touched, is user-supplied text ever \
embedded in a prompt without sanitisation or XML-tag isolation?

## Code Quality
- Naming, structure, and style against CLAUDE.md conventions
- Async/await usage (all routes must be `async def`; CPU-bound work via `asyncio.to_thread`)
- Type annotation coverage

## Correctness
- Logic errors and edge cases (reference diff line numbers)
- FIFO algorithm correctness if `domain/fifo.py` is touched
- Violation detection accuracy if `domain/violations.py` is touched
- Migration reversibility if Alembic files are changed

## Verdict
Exactly one of **APPROVE**, **REQUEST CHANGES**, or **COMMENT** — and one sentence why."""


def post_github_comment(repo: str, pr_number: str, body: str, token: str) -> None:
    url = f"https://api.github.com/repos/{repo}/issues/{pr_number}/comments"
    headers = {
        "Authorization": f"Bearer {token}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }
    response = httpx.post(url, json={"body": body}, headers=headers, timeout=30)
    response.raise_for_status()


def main() -> None:
    required = [
        "ANTHROPIC_API_KEY",
        "GITHUB_TOKEN",
        "PR_NUMBER",
        "PR_TITLE",
        "BASE_SHA",
        "HEAD_SHA",
        "REPO",
    ]
    missing = [v for v in required if not os.environ.get(v)]
    if missing:
        print(f"Missing required env vars: {', '.join(missing)}", file=sys.stderr)
        sys.exit(1)

    anthropic_key = os.environ["ANTHROPIC_API_KEY"]
    github_token = os.environ["GITHUB_TOKEN"]
    pr_number = os.environ["PR_NUMBER"]
    pr_title = os.environ["PR_TITLE"]
    pr_body = os.environ.get("PR_BODY", "")
    base_sha = os.environ["BASE_SHA"]
    head_sha = os.environ["HEAD_SHA"]
    repo = os.environ["REPO"]

    claude_md = load_file(REPO_ROOT / "CLAUDE.md")
    spec_md = load_file(REPO_ROOT / "docs" / "SPEC.md")
    assignment_md = load_file(REPO_ROOT / "assignment" / "Final_Assignment.md")
    score_md = load_file(REPO_ROOT / "docs" / "SCORE.md")
    diff, truncated = get_pr_diff(base_sha, head_sha)

    if not diff.strip():
        print("No diff found — skipping review.")
        return

    print(f"Reviewing PR #{pr_number}: {pr_title}")
    print(f"Diff size: {len(diff):,} characters{' (truncated)' if truncated else ''}")

    client = anthropic.Anthropic(api_key=anthropic_key)

    # Stream the response to avoid HTTP timeouts on large diffs.
    with client.messages.stream(
        model=MODEL,
        max_tokens=6000,
        system=[
            # CLAUDE.md, SPEC.md, the assignment, and SCORE.md are stable across PRs
            # — cache them so subsequent reviews in the same cache window are cheaper.
            # The Anthropic API supports up to 4 cache breakpoints; all four are used here.
            {
                "type": "text",
                "text": claude_md,
                "cache_control": {"type": "ephemeral"},
            },
            {
                "type": "text",
                "text": f"# Technical Specification\n\n{spec_md}",
                "cache_control": {"type": "ephemeral"},
            },
            {
                "type": "text",
                "text": f"# Assignment Requirements\n\n{assignment_md}",
                "cache_control": {"type": "ephemeral"},
            },
            {
                "type": "text",
                "text": f"# Project Score Tracker\n\n{score_md}",
                "cache_control": {"type": "ephemeral"},
            },
            {
                "type": "text",
                "text": (
                    "You are a senior engineer performing code review. "
                    "Be specific and actionable. Reference diff line numbers where possible. "
                    "Do not praise obvious things."
                ),
            },
        ],
        messages=[
            {
                "role": "user",
                "content": build_review_prompt(pr_title, pr_body, diff),
            }
        ],
    ) as stream:
        message = stream.get_final_message()

    if not message.content or message.content[0].type != "text":
        print(
            f"Unexpected API response: content={message.content!r}, "
            f"stop_reason={message.stop_reason!r}",
            file=sys.stderr,
        )
        sys.exit(1)

    review_text = message.content[0].text
    usage = message.usage
    cache_read = getattr(usage, "cache_read_input_tokens", 0)
    cache_write = getattr(usage, "cache_creation_input_tokens", 0)

    print(
        f"Tokens — input: {usage.input_tokens:,} "
        f"(cache read: {cache_read:,}, cache write: {cache_write:,}), "
        f"output: {usage.output_tokens:,}"
    )

    truncation_banner = (
        "\n> [!WARNING]\n"
        "> **Diff truncated.** This PR exceeded 80,000 diff characters. "
        "The review below covers only the first 80,000 characters — "
        "later hunks were not visible to the model.\n\n"
        if truncated
        else ""
    )

    footer = (
        f"\n\n---\n"
        f"*Claude PR Review · `{MODEL}` · "
        f"input {usage.input_tokens:,} tok "
        f"(cache hit {cache_read:,} / write {cache_write:,}) · "
        f"output {usage.output_tokens:,} tok*"
    )

    comment = f"## Claude Code Review\n\n{truncation_banner}{review_text}{footer}"
    post_github_comment(repo, pr_number, comment, github_token)
    print("Review posted successfully.")


if __name__ == "__main__":
    main()