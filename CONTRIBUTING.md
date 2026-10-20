# Contributing to VidSearch

Thanks for your interest! Bug reports, benchmark results on new hardware, and pull requests are all welcome.

## Development setup

Requirements: [uv](https://docs.astral.sh/uv/) and Node 22+. Python 3.12+ is installed by uv automatically.

```bash
# backend
cd backend
uv sync
uv run fastapi dev app/main.py          # http://localhost:8000

# frontend
cd frontend
npm ci
npm run dev                             # http://localhost:5173, proxies /api to the backend
```

To point the frontend dev server at a backend on another port: `VIDSEARCH_API=http://localhost:8001 npm run dev`.

## Before opening a pull request

CI runs these checks, and `main` only accepts changes that pass them:

```bash
cd backend
uv run ruff check .
uv run ruff format --check .
uv run pytest

cd frontend
npm run build
```

The backend tests use generated videos and a fake encoder, so they run in seconds and don't download a model.

## Changes that affect results

Retrieval quality and speed are the point of this project, so claims about them have to be reproducible:

- If a change could affect accuracy (sampling, preprocessing, the model, the Core ML export, scoring, moment grouping), run `uv run python -m eval.msrvtt --limit 100` before and after, and include both outputs in the PR.
- Numbers in the README must come from JSON files in `backend/eval/results/`, produced from **committed** code. Each file records `git describe --dirty`, so results produced from an uncommitted tree show up as `-dirty`. Commit the code first, rerun the eval, then commit the results.
- When you add or change a benchmark, document the exact command to reproduce it.

## Pull requests

- Keep each PR focused on one change, and describe what changed and why.
- Add or update tests for behaviour changes.
- Use clear commit messages: an imperative summary line, then details if needed.
- Don't commit datasets, model weights, or anything under `backend/data/`.

## Reporting bugs and requesting features

Use the [issue templates](https://github.com/daven-c/VidSearch/issues/new/choose). For bugs, include your OS, hardware (e.g. Apple M4 / RTX 2070), the vision backend (`coreml` or `torch`), and steps to reproduce.

Security problems should be reported privately; see [SECURITY.md](SECURITY.md).

By contributing, you agree that your contributions are licensed under the [MIT License](LICENSE), and to follow the [Code of Conduct](CODE_OF_CONDUCT.md).
