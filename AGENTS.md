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

Benchmarks use optimized builds and run without concurrent build or test load.
See corpus/README.md, corpus/upstream/README.md and benchmarks/README.md.

# Agents

Two roles. Coordination state lives in GitHub issues and CI, never in repository
files: no ownership manifests, landing scripts or evidence archives.

## Goal agent

Driven by a person, ad hoc. It states goals and turns them into tickets, and it
runs audits that produce tickets (for example a CI waste audit or a
migration-scope review). Introspection about improving the codebase or this
workflow happens here. Large goals get a `kind:goal` issue that links its
children. It may reprioritise or close any ticket.

## Executor agents

Interchangeable and disposable: no special environment, authentication or setup
beyond a checkout, `gh` with `GH_TOKEN`, and the toolchain. Prefer cloud
environments to one shared machine. Each executor loops:

1. Claim the highest-priority, oldest `status:ready` issue (see Tickets).
2. Branch from `main`, commit. The pre-commit hook runs quick checks (~15s);
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
   prints, `python3 tools/ci.py wait --commit <merge sha>`.
6. Validate the change where it lands, comment what was checked on the issue,
   and close it.
7. File follow-ups as `status:ready` issues with a priority and
   `follow-up of #n`. Executor follow-ups usually find real issues; they are not
   gated behind the goal agent.
8. Repeat.

Don't stop to ask before routine next steps (merge on green, close, file
follow-ups). Stop only for destructive or genuinely ambiguous decisions.

## Tickets

GitHub issues. Exactly one status label per open issue:

| Label | Meaning |
| --- | --- |
| `status:ready` | Claimable |
| `status:claimed` | An executor owns it; see the latest `claim` comment |
| `status:review` | PR open |
| `status:blocked` | Waiting on another issue; see the `blocked by #n` comment |

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

Three tiers: the pre-commit hook (~15s), the PR tier (`pr.yml`, under 3 minutes
warm) and the merge tier (`merge.yml`, on `main`). Keep them cached and audit
them regularly for waste and duplicate steps; slow or flaky CI is a ticket.
