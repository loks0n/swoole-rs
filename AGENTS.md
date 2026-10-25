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

Work tickets from GitHub issues labelled `status:ready`: comment `claim <id>`, re-read
the comments (the earliest claim wins), then move the label to `status:claimed`.
Open a PR with `Closes #n`, then call `pr_merge_when_green` from the repository MCP
server (`.mcp.json`) for that PR, one call per PR, so each merges as soon as it
passes. File follow-ups as `status:ready` issues.
