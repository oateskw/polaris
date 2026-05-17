# polaris

## Project Layout

- `src/polaris/`: application package (CLI, models, repositories, services)
- `tests/`: pytest test suite
- `alembic/`: database migrations
- `scripts/`: utility and content generation scripts
- `demos/meta_review/`: Meta App Review screencast demos
- `images/`, `videos/`, `fonts/`, `music/`: media assets
- `logs/`: runtime logs

## Common Entry Points

- `python -m polaris ...` for CLI operations
- Root `.bat` and `.vbs` files for Windows task shortcuts

## Demo Scripts

Meta permission review scripts were moved from repo root to:

- `demos/meta_review/`

Run demos from the project root, for example:

- `python demos/meta_review/demo_instagram_manage_messages.py`