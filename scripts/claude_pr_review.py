#!/usr/bin/env python3
"""Claude-powered PR review agent.

Runs in GitHub Actions on every pull request. Reads CLAUDE.md and docs/SPEC.md
as cached prompt blocks (so repeated PRs pay the cache-write cost only once per
cache TTL), fetches the git diff, and posts a structured review as a PR comment.
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


def get_pr_diff(base_sha: str, head_sha: str) -> str:
    result = subprocess.run(
        ["git", "diff", f"{base_sha}...{head_sha}"],
        capture_output=True,
        text=True,
        cwd=REPO_ROOT,
    )
    diff = result.stdout
    if len(diff) > MAX_DIFF_CHARS:
        diff = diff[:MAX_DIFF_CHARS] + "\n\n[diff truncated — showing first 80,000 characters]"
    return diff


def build_review_prompt(pr_title: str, pr_body: str, diff: str) -> str:
    return f"""You are reviewing a pull request for the Lumina Capital Transactions Platform.

PR Title: {pr_title}
PR Description: {pr_body or "(none)"}

Git diff:
```diff
{diff}
```

Provide a structured review with these exact sections:

## Summary
One paragraph overview of what this PR does.

## Spec Alignment
Does the implementation match docs/SPEC.md? Call out any deviations, missing pieces, \
or additions beyond scope.

## Code Quality
- Naming, structure, and style against CLAUDE.md conventions
- Async/await usage (all routes must be `async def`, CPU-bound work via `asyncio.to_thread`)
- SQL safety: parameterised queries only, no string interpolation
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
    required = ["ANTHROPIC_API_KEY", "GITHUB_TOKEN", "PR_NUMBER", "PR_TITLE", "BASE_SHA", "HEAD_SHA", "REPO"]
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
    diff = get_pr_diff(base_sha, head_sha)

    if not diff.strip():
        print("No diff found — skipping review.")
        return

    print(f"Reviewing PR #{pr_number}: {pr_title}")
    print(f"Diff size: {len(diff):,} characters")

    client = anthropic.Anthropic(api_key=anthropic_key)

    # Stream the response to avoid HTTP timeouts on large diffs
    with client.messages.stream(
        model=MODEL,
        max_tokens=2048,
        system=[
            # CLAUDE.md and SPEC.md are stable across PRs — cache them so
            # subsequent reviews in the same cache window are cheaper
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

    review_text = message.content[0].text
    usage = message.usage
    cache_read = getattr(usage, "cache_read_input_tokens", 0)
    cache_write = getattr(usage, "cache_creation_input_tokens", 0)

    print(
        f"Tokens — input: {usage.input_tokens:,} "
        f"(cache read: {cache_read:,}, cache write: {cache_write:,}), "
        f"output: {usage.output_tokens:,}"
    )

    footer = (
        f"\n\n---\n"
        f"*Claude PR Review · `{MODEL}` · "
        f"input {usage.input_tokens:,} tok "
        f"(cache hit {cache_read:,} / write {cache_write:,}) · "
        f"output {usage.output_tokens:,} tok*"
    )

    comment = f"## Claude Code Review\n\n{review_text}{footer}"
    post_github_comment(repo, pr_number, comment, github_token)
    print("Review posted successfully.")


if __name__ == "__main__":
    main()
