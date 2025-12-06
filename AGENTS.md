# Repository Guidelines

## Project Structure & Module Organization
- `collect_highlights.py`: Main Python CLI with `collect` and `publish` subcommands. Key classes: `LuaTableParser`, `HighlightsCollector`, `KarakeepClient`.
- `highlights.json`: Generated output from `collect` (example artifact).
- `.env`: Local credentials for Karakeep (`KARAKEEP_ID`, `KARAKEEP_PASSWORD`, optional `KARAKEEP_URL`). Do not commit secrets.
- `README.md`: Usage and workflow details. `requirements.txt`: notes stdlib-only.
- Suggested tests location: `tests/` (e.g., `tests/test_lua_parser.py`).

## Build, Test, and Development Commands
- Run help: `python3 collect_highlights.py --help` (and `collect --help`, `publish --help`).
- Collect highlights: `python3 collect_highlights.py collect --base-path ~/syncthing/ebooks-highlights --output highlights.json`.
- Publish (dry run): `python3 collect_highlights.py publish --dry-run`.
- Publish to Karakeep: `python3 collect_highlights.py publish --list-name "Book Quotes"` (reads `.env`).
- Cron example pathing is in `README.md`; keep absolute paths stable.

## Coding Style & Naming Conventions
- Python 3.6+; follow PEP 8 (4-space indents, 100–120 col soft limit).
- Use snake_case for functions/vars, PascalCase for classes, UPPER_SNAKE_CASE for constants.
- Prefer `pathlib.Path` for I/O and add type hints (`typing`) as in current code.
- Keep modules single-purpose; new functionality should be factored into helpers or new classes in the same file (or a `src/` package if size grows).

## Testing Guidelines
- Framework: `pytest` or stdlib `unittest`. Place tests in `tests/` with `test_*.py` naming.
- Priority areas: Lua parsing (`LuaTableParser`), aggregation/dedup ordering in `HighlightsCollector`, and Karakeep API interactions (mock HTTP).
- Example: `python -m pytest -q` or `python -m unittest discover -s tests`.
- Aim to cover common metadata edge cases (missing fields, empty highlights, bookmarks without text).

## Commit & Pull Request Guidelines
- Commit style: Conventional Commits observed in history (e.g., `feat:`, `chore:`). Write imperative, concise messages.
- PRs should include: summary, rationale, screenshots/logs when modifying output, and links to issues (if any).
- Checklist: no secrets in diffs, updated `README.md`/comments as needed, basic run verified (`collect` and/or `publish --dry-run`).

## Security & Configuration Tips
- Keep `.env` local and untracked; never log credentials. Use `--dry-run` when validating changes.
- Network calls use `urllib`; handle exceptions and avoid printing sensitive payloads.
- For local paths, prefer `~` or environment variables; avoid hardcoding device-specific paths in code.
