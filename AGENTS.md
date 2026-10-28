# Working rules

Complexity is the devil, and simplicity is human. Before starting, consider what
can be deleted. Aim for a net negative LoC delta where the task permits it.

Never edit target/upstream/src. It is the pinned reference. Hybrid changes belong
in migration/patches/<module>/ and are edited with `tools/patches.py`.

Preserve upstream test assertions and expected outputs. Never mark unsupported,
SKIP or XFAIL as passed, or weaken capability probes to hide behavior failures.
Run original PHPT tests with PHP's official runner through corpus/upstream/run.py,
not upstream's tests/start.sh: its cleanup can kill unrelated processes.
Keep module tests under tests/modules/<module>/.

Rust lint levels live only in the root `Cargo.toml` (`[workspace.lints]`) and
`clippy.toml`. Never lower one in a PR that also changes code; lowering one needs
`needs:decision`. Suppress with `#[expect(lint, reason = "...")]`, never `#[allow]`,
and give a reason a reviewer can judge. Deny a lint once its count reaches zero.
The one per-crate exception: each `lib.rs` denies `undocumented_unsafe_blocks` and
`multiple_unsafe_ops_per_block` under `cfg_attr(not(test), ...)`. Every non-test
unsafe block states its invariant in a `// SAFETY:` comment and does one operation;
test code is exempt.

Benchmarks use optimized builds and run without concurrent build or test load.
Build, profile and benchmark output goes under the worktree's `target/` (a second
checkout is `git worktree add target/worktrees/<sha>`), never in a session scratch
directory; `dev.py prune` clears what a day leaves untouched.
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

Interchangeable and disposable: a checkout, `gh` with `GH_TOKEN` and the
toolchain are all you need. Executors run in cloud environments by default
(`.devcontainer/`; see docs/development.md). For Linux-only phases elsewhere, use
`python3 tools/dev.py docker -- <lane> …` rather than `docker` directly.

You own the ticket you claim, end to end, and you're trusted to use your
judgment: choose the approach, size each PR, fix what you trip over on the way,
and file what you find. Decisions on an issue are the goal agent's best guess; when
the code says otherwise, do what's right and explain it in the PR. Be bold. The
migration moves fastest when a PR moves a group of state together with the
operations over it and deletes their upstream bodies, and it only ever moves into
Rust.

1. Claim the first issue `python3 tools/ci.py next` prints (see Tickets).
2. Branch from `main` and commit; `git config core.hooksPath .githooks` enables
   the quick pre-commit checks.
3. Push, open a PR whose body says `Closes #n`, and run
   `gh pr merge --auto --squash <pr>`. GitHub merges it once `rust` and `tooling`
   pass. `hybrid`, `gates` and the merge tier keep running: watch them in the
   background with `python3 tools/ci.py wait --pr <pr>` and start on the next
   issue meanwhile. If they show you broke something, fixing it comes next.
4. Close the issue with a note of what you checked, file follow-ups as
   `status:ready` sub-issues of the same goal, and repeat.

Nobody needs to approve your next step, so keep the loop going on your own. When
a question comes up, gather the data (read upstream, reproduce, measure) and make
the call yourself; you're trusted to choose well, and the PR is where you explain
the choice. `needs:decision` is only for exceptional cases: changing project policy,
or a choice that's hard to undo and that the data can't settle. Then add your
recommendation and work on something else until it's answered.

**Upstream security bugs stay private.** This repo is public. A memory-safety bug
or other likely vulnerability in upstream Swoole (or any dependency) never goes in
an issue, PR, commit message or code comment here. File it as an issue in the
private `loks0n/swoole-rs-security` repository with the upstream location, cause
and impact (the reproducer stays local), then carry on; a person handles
disclosure. Public code, comments and test exclusions don't mark where upstream
misbehaves either.

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
  unblocked by GitHub the moment the last one closes. Claimable issues, in claim
  order: `python3 tools/ci.py next`.
- **Waiting on a decision:** rare (see Executor agents). Add `needs:decision`
  with the evidence and a recommendation; the goal agent or a person answers on
  the issue and removes the label.
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

`tools/ci.py` (`wait`, `status`; see `--help`) is the only way agents watch
CI; GitHub's auto-merge does the merging. It needs a checkout, `gh` and Python, so it works in every session.
The pre-commit and pre-push hooks remind you of the next command. Agents
improve it: add a subcommand when an agent would otherwise improvise (polling,
ad-hoc scripts, `gh run watch`).

## CI

Three tiers: the pre-commit hook (~5s warm), the PR tier (`pr.yml`, under 3 minutes
warm) and the merge tier (`merge.yml`, on `main`). `main`'s ruleset requires a
pull request and the PR tier's `rust` and `tooling` checks, so renaming those jobs
means updating the ruleset in the same PR. `hybrid` (all-modules build, about 20
minutes) and `gates` are informative, so merging stays fast; breakage they miss
is caught by the merge tier and the red-main rule. Keep them cached and audit
them regularly for waste and duplicate steps; slow or flaky CI is a ticket.

The merge tier runs one at a time, latest wins: while a run is in progress, each
push to `main` replaces the pending run, so the next run covers `main`'s head.
Its result therefore describes the commit it names, which may be several merges
old: at most one run (about 15-30 minutes) behind `main`. Every job has a
`timeout-minutes` cap, so a hung run can't stall the queue.

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
