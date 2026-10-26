# Working rules

Complexity is the devil, and simplicity is human. Before starting, consider what
can be deleted. Aim for a net negative LoC delta where the task permits it.

Never edit target/upstream/src. It is the pinned reference. Hybrid changes belong
in migration/patches/<module>/ and must declare their upstream destinations in
migration/modules.json. Run `python3 tools/check_migration.py` after changing it.

Preserve upstream test assertions and expected outputs. Never mark unsupported,
SKIP or XFAIL as passed, or weaken capability probes to hide behavior failures.
Run original PHPT tests with PHP's official runner through corpus/upstream/run.py,
not upstream's tests/start.sh: its cleanup can kill unrelated processes.
Keep module tests under tests/modules/<module>/.

Rust lint levels live only in the root `Cargo.toml` (`[workspace.lints]`) and
`clippy.toml`. Never lower one in a PR that also changes code; lowering one needs
`needs:decision`. Suppress with `#[expect(lint, reason = "...")]`, never `#[allow]`,
and give a reason a reviewer can judge. Deny a lint once its count reaches zero.

Benchmarks use optimized builds and run without concurrent build or test load.
See corpus/README.md, corpus/upstream/README.md and benchmarks/README.md.

# Agents

Three roles. Coordination state lives in GitHub issues and CI, never in repository
files: no ownership manifests, landing scripts or evidence archives.

## Goal agent

Driven by a person, ad hoc. It states goals and turns them into tickets, and it
runs audits that produce tickets (for example a CI waste audit or a
migration-scope review). Introspection about improving the codebase or this
workflow happens here. Large goals get a `kind:goal` issue whose children are
its sub-issues. It may reprioritise or close any ticket.

## Executor agents

Interchangeable and disposable: no special environment, authentication or setup
beyond a checkout, `gh` with `GH_TOKEN`, and the toolchain. Prefer cloud
environments to one shared machine. Each executor loops:

1. Claim the highest-priority, oldest unblocked `status:ready` issue without
   `needs:decision` (see
   Tickets).
2. Branch from `main`, commit. The pre-commit hook runs quick checks (~5s warm);
   enable the hooks with `git config core.hooksPath .githooks`.
3. Push and open a PR whose body says `Closes #n`. The PR tier runs unit and
   integration CI (target: under 3 minutes).
4. Run `python3 tools/ci.py merge <pr>` (in the background; it can take a few
   minutes). It waits for the PR tier on the current head, follows the head if
   you push, and squash-merges when it passes. On failure it prints the failing
   jobs and their log tails: fix, push and run it again. If the PR conflicts,
   merge `origin/main`, push and run it again.
5. The merge tier runs on `main`: everything above plus every gate, application
   and original PHPT for all modules. Watch it with the command `ci.py merge`
   prints, `python3 tools/ci.py wait --commit <merge sha>`. If that run was
   cancelled (exit 3), a later run covers your commit; nothing to do. If it
   failed, handle its **new failures** as described under *Red main* (CI), and
   move on.
6. Validate the change where it lands, comment what was checked on the issue,
   and close it. If it delivers only part of what an issue it blocks needs,
   make the follow-up block that issue too.
7. File follow-ups as `status:ready` issues with a priority and
   `follow-up of #n`, as sub-issues of the same goal. Executor follow-ups usually find real issues; they are not
   gated behind the goal agent.
8. Repeat.

Don't stop to ask before routine next steps (merge on green, close, file
follow-ups). Stop only for destructive or genuinely ambiguous decisions.

## Reviewer agents

Interchangeable and disposable, like executors, but they change no code. Each
picks an area (a module, a tool, a CI tier, recently merged PRs) and checks that
the work already there is right: bugs, inconsistencies between code, tests and
docs, and gaps inside work that claims to be complete.

Judge work against what it set out to do: the issue, the PR description, the
module's entry in `migration/modules.json`. Work that is explicitly not done,
out of scope, or already tracked by an open issue is not a finding.

Verify each finding before filing it: a failing test, a command and its output,
or the exact lines that disagree. Search open and closed issues for duplicates,
then file it as a `status:ready` issue with a priority, a kind and the evidence.
Executors fix it.

## Tickets

GitHub issues. Exactly one status label per open issue:

| Label | Meaning |
| --- | --- |
| `status:ready` | Claimable unless blocked |
| `status:claimed` | An executor owns it; see the latest `claim` comment |
| `status:review` | PR open |

Use GitHub's own relationships, not comments or labels:

- **Blocked:** mark the blocking issue in the issue's *Relationships* (`gh api -X
  POST repos/{owner}/{repo}/issues/<n>/dependencies/blocked_by -F issue_id=<id
  of the blocker>`). An issue is blocked while any blocker is open and is
  unblocked by GitHub the moment the last one closes. Claimable issues:
  `gh issue list --search "is:open label:status:ready -is:blocked -label:needs:decision sort:created-asc"`.
- **Waiting on a decision:** add `needs:decision` and comment the question (a
  policy change, an open design choice). Whoever decides, the goal agent or a
  person, answers on the issue and removes the label.
- **Waiting on a CI run or measurement:** make the issue that produces it the
  blocker, or file one.
- **Goals:** a `kind:goal` issue's children are its sub-issues (`gh api -X POST
  repos/{owner}/{repo}/issues/<goal>/sub_issues -F sub_issue_id=<id of the child>`).

Closed means done. Priority: `p0` (breaks agents or `main`), `p1` (next up),
`p2` (when convenient). Kind: `kind:bug`, `kind:ci`, `kind:migration`,
`kind:goal`.

Claiming (all agents may share one GitHub account, and GitHub has no
compare-and-swap):

1. Comment `claim <agent-id>` and re-read the comments. The earliest `claim`
   after the last `release` wins; a loser deletes its comment and picks another.
2. The winner moves the label from `status:ready` to `status:claimed`.
3. Comment `heartbeat <agent-id>` at least every 30 minutes, with progress. A
   claim with no heartbeat or PR activity for 2 hours returns to `status:ready`.
4. Comment `release <agent-id>` and restore `status:ready` to give a ticket up.

## CI CLI

`tools/ci.py` (`merge`, `wait`, `status`; see `--help`) is the only way agents
watch CI. It needs a checkout, `gh` and Python, so it works in every session.
The pre-commit and pre-push hooks remind you of the next command. Agents
improve it: add a subcommand when an agent would otherwise improvise (polling,
ad-hoc scripts, `gh run watch`).

## CI

Three tiers: the pre-commit hook (~5s warm), the PR tier (`pr.yml`, under 3 minutes
warm) and the merge tier (`merge.yml`, on `main`). Keep them cached and audit
them regularly for waste and duplicate steps; slow or flaky CI is a ticket.

The merge tier runs one at a time, latest wins: while a run is in progress, each
push to `main` replaces the pending run, so the next run covers `main`'s head.
Its result therefore describes the commit it names, which may be several merges
old. How recent that is depends on run length, which #7 is
reducing.

### Red main

`main` is often red, and that's tolerable; never stop other work because of it.
What must not slip through is a **new** failure: a phase that passed in the
previous completed merge-tier run, or one that didn't exist then. `ci.py status`
and `wait` list them as `new failures` for merge-tier runs.

For each new failure, search open issues for the phase name. If none mentions
it, file a `p0` `kind:bug` issue with the run link, the phase and its log path,
and the commit range since the previous run (group phases of one module into one
issue), as a sub-issue of the Phase 1 goal. Then carry on with your own ticket.
`p0` sorts first, so the next free executor picks it up. Failures that already
have an issue keep that issue's priority.
