# Repository Guidelines

## Project Structure & Module Organization
This repository is currently documentation-first. The root contains investigation and planning files such as `CMFGEN_output_file_investigation_2026-02-08.txt` and `CMFGEN_viewer_implementation_checklist_2026-02-08.txt`.

When adding implementation code, use a predictable layout:
- `src/` for parsers, data models, and viewer logic
- `tests/` for unit and fixture-driven tests
- `fixtures/` for small, sanitized CMFGEN output samples
- `docs/` for format notes and architecture decisions

Do not commit large generated artifacts (for example ad hoc `manifest.json` files) unless they are intentional golden fixtures.

## Build, Test, and Development Commands
No build system is committed yet. Until tooling is added, use lightweight checks:
- `rg --files` to inspect repository contents quickly
- `rg "RVTJ|OBSFLUX|MOD_SUM" src tests` to confirm coverage of core file types
- `wc -w AGENTS.md` to validate documentation length targets

If you introduce Python, Node, or another runtime, add explicit project commands (for example `make test` or `npm test`) in the same PR.

## Coding Style & Naming Conventions
- Use 4-space indentation for Python, and 2 spaces for JSON/YAML/Markdown list nesting.
- Name parser modules after CMFGEN targets, e.g., `rvtj_parser.py`, `mod_sum_parser.py`.
- Mirror module names in tests, e.g., `tests/test_rvtj_parser.py`.
- Use snake_case for manifest/schema fields such as `parse_status` and `core_viewer`.

## Testing Guidelines
Focus on parser correctness and resilience:
- Golden-file parse tests for expected output
- Malformed/truncated input tests
- Missing-section tests with clear warning behavior
- Cross-file consistency checks (for example matching `ND` vector lengths)

## Commit & Pull Request Guidelines
Git is initialized, but there are no commits yet, so no project-specific message pattern exists. Use Conventional Commits from the start: `feat:`, `fix:`, `docs:`, `test:`, `chore:`.

Keep commits small and single-purpose, for example:
- `docs: add parser fixture conventions`
- `feat: add RVTJ manifest scanner`

PRs should include:
- Scope summary
- Fixture/sample files affected
- Before/after behavior notes
- Screenshots for viewer/UI changes

## Security & Configuration Tips
Do not commit proprietary or sensitive CMFGEN outputs. Prefer minimal, anonymized fixtures and document provenance in `docs/`.
