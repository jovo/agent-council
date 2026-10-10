# Modularization map

`bin/unified-review` is the installed entry point and the process relaunched by
background review, fact-check, upload, and page-server jobs. It must remain the
CLI entry point while the first extractions land.

## Constraints

- Land no extraction until the test-state guard in #20 has merged.
- Make each first extraction a pure move. Preserve names, call signatures,
  command-line behavior, run artifacts, HTTP routes, and environment variables.
- Repoint test patches to the module that owns the patched name. Do not leave
  compatibility copies of mutable globals in the CLI module.
- Resolve module paths from the entry point's real path. `install.sh` installs a
  symlink, and child processes re-run `bin/unified-review` through
  `os.path.abspath(__file__)`.

## Boundaries

```text
CLI entry point
  ├── run store
  ├── document I/O
  ├── review pipeline
  └── local server
        ├── run store
        ├── document I/O
        └── review pipeline
```

The CLI keeps argument parsing, executable-path discovery, and process launch.
The extracted modules keep their current function names during the first move.

| Target module | Current source region | Owned state and behavior | Main callers |
| --- | --- | --- | --- |
| Run store | decisions, versions, run lookup, carry-over | `RUNS_DIR`, `LAST_RUN`, decision and version registries, `runs_for`, page registry, `write_atomic` | CLI, pipeline, server, document conversion |
| Document I/O | document conversion through Word export | PDF and DOCX conversion, PDF inspection, DOCX tracked changes and comments, export, bibliography caches | CLI, server, checks |
| Review pipeline | prompts through foreground and background review | panel preflight, prompts, calls, voting, merge, rendering, fact-checking | CLI, server ask and comment flows |
| Local server | review-page section | HTTP routes, upload and open jobs, SSE, static assets, Finder selection, audio transcription | CLI page and upload modes |

## Shared globals to map before each move

| Name | Current role | First owner |
| --- | --- | --- |
| `RUNS_DIR`, `LAST_RUN` | persisted runs and newest-run pointer | Run store |
| `PANELISTS`, `EFFORT`, `FAILURES`, `READ_FILES`, `DECK` | review execution state | Review pipeline |
| `BIB`, `_BIB_KEYS`, `_REFS_HTML` | bibliography and citation caches | Document I/O |
| `PAGE_DIR`, `FONT_DIR`, `JOBS`, `SEEN` | page assets and live-job state | Local server |
| `CHILD_ENV`, executable path | child-process launch environment | CLI entry point |

## Test migration

The test suite currently patches names on the loaded `ur` module, including
`RUNS_DIR`, `LAST_RUN`, `BIB`, `call`, and `load_rules`. A moved function must
read the patched name from its owner module. Each extraction PR must:

1. Repoint patches for moved names to the owner module.
2. Run the suite with temporary run and state directories from #20.
3. Verify that the real run and state directories remain unchanged.
4. Preserve subprocess tests that set `UNIFIED_REVIEW_RUNS` explicitly.

## Extraction order

1. Merge #20, the suite-wide test-state guard.
2. Extract the run store in #16. It is the smallest shared state boundary and
   gives later modules one stable location for persisted state.
3. Extract document I/O in #18. Keep DOCX export and audio transcription
   behavior unchanged.
4. Extract the review pipeline in #17.
5. Extract the local server in #19.

Explicit dependency injection, redesigning run configuration, and changing
cache invalidation are follow-up work. They do not belong in the pure-move
extractions.
