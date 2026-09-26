# Issue tracker: GitHub

Issues and specs for this repo live as GitHub issues. Use the `gh` CLI for all operations.

## Conventions

- **Create an issue**: `gh issue create --title "..." --body "..."`. Use a body file for multiline text.
- **Read an issue**: `gh issue view <number> --comments`, including its labels.
- **List issues**: `gh issue list --state open --json number,title,body,labels,comments` with the relevant label and state filters.
- **Comment on an issue**: `gh issue comment <number> --body "..."`.
- **Apply or remove labels**: `gh issue edit <number> --add-label "..."` or `--remove-label "..."`.
- **Close an issue**: `gh issue close <number> --comment "..."`.

Infer the repository from `git remote -v`. A GitHub remote must be configured before these commands can publish changes.

## Pull requests as a triage surface

**PRs as a request surface: no.** Set this to `yes` only if external pull requests should enter the issue triage queue.

GitHub shares one number space across issues and pull requests. Resolve an ambiguous `#42` with `gh pr view 42`, then fall back to `gh issue view 42`.

## Skill meanings

- When a skill says **publish to the issue tracker**, create a GitHub issue.
- When a skill says **fetch the relevant ticket**, run `gh issue view <number> --comments`.

## Wayfinding operations

- A map is one issue labelled `wayfinder:map` containing Notes, Decisions-so-far, and Fog.
- Child tickets are GitHub sub-issues when available. Otherwise, link them from the map task list and start each child with `Part of #<map>`.
- Child labels use `wayfinder:research`, `wayfinder:prototype`, `wayfinder:grilling`, or `wayfinder:task`.
- Represent blockers with GitHub issue dependencies. If unavailable, start the child with `Blocked by: #<n>`.
- The next frontier item is the first open, unassigned child without an open blocker.
- Claim work with `gh issue edit <n> --add-assignee @me`.
- Resolve work by commenting with the answer, closing the issue, and adding its context pointer to the map.
