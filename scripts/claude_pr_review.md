# `claude_pr_review.py`

Claude-powered PR review agent. Invoked by `.github/workflows/ci.yml` on
every pull request once `lint` and `test` pass. Reads project context,
fetches the diff, calls the Anthropic API, and posts a structured review
as a PR comment.

## How it runs

GitHub Actions only — never invoked locally. The workflow injects:

- `ANTHROPIC_API_KEY` (repo secret)
- `GITHUB_TOKEN` (auto)
- `PR_NUMBER`, `BASE_SHA`, `HEAD_SHA` (from `github.event.pull_request.*`)

## What it does

1. Loads four context files as cached prompt blocks (so repeated PRs pay
   the cache-write cost only once per cache TTL):
   `CLAUDE.md`, `docs/SPEC.md`, `assignment/Final_Assignment.md`,
   `docs/SCORE.md`.
2. Runs `git diff base...head` (truncated to 500 KB).
3. Sends one Anthropic API call (model: `claude-sonnet-4-6`) asking for
   correctness / security / spec-alignment / hygiene findings.
4. Posts the response as a single PR comment via the GitHub REST API.

## Why this exists

The agent is treated as **advisory, not authoritative** — every comment
gets human-triaged accept-or-reject before any change lands. Across the
project's PRs it caught real bugs (ownership filter, race condition,
missing null check) the conversational review missed, and raised ~17
points that didn't hold up after investigation. The triage record lives
in [`AI_USAGE.md`](../AI_USAGE.md) under *Who Caught What*.
