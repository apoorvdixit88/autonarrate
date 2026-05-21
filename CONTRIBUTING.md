# Contributing to AutoNarrate

Thanks for your interest in contributing! This document covers how to get a working development environment, run the project locally, and submit a pull request.

For an overview of what AutoNarrate does, see the [README](README.md).

## Code of Conduct

Be respectful and constructive. Assume good faith. Keep discussion focused on the code and the problem at hand.

## Setting Up the Dev Environment

### Prerequisites

- **Python 3.10+** — check with `python3 --version`
- **FFmpeg** — required for video processing
  - macOS: `brew install ffmpeg`
  - Ubuntu/Debian: `sudo apt update && sudo apt install ffmpeg`
  - Windows (chocolatey): `choco install ffmpeg`
- **An AI vision backend** — pick one and configure it in `.env`. Supported backends: `claude_code`, `opencode`, `openai`, `anthropic`, `ollama`. See the "AI Backend" item under [Prerequisites in the README](README.md#prerequisites) for install steps for each.
- **Git** and a GitHub account

### Option A — Automated setup (recommended)

From the repo root:

```bash
chmod +x setup.sh
./setup.sh
```

`setup.sh` will verify Python and FFmpeg, create `venv/`, install dependencies, copy `.env.example` to `.env`, and pick a vision backend based on what is installed locally.

### Option B — Manual setup

```bash
# 1. Fork apoorvdixit88/autonarrate on GitHub, then clone your fork:
git clone https://github.com/<your-username>/autonarrate.git
cd autonarrate

# 2. Add the upstream remote so you can pull in main:
git remote add upstream https://github.com/apoorvdixit88/autonarrate.git

# 3. Create and activate a virtual environment:
python3 -m venv venv
source venv/bin/activate    # Windows: venv\Scripts\activate

# 4. Install dependencies:
pip install --upgrade pip
pip install -r requirements.txt

# 5. Copy environment config:
cp .env.example .env
# Edit .env to set VISION_BACKEND and any required API keys.
```

## Running the Project Locally

With your virtual environment activated:

```bash
source venv/bin/activate    # if not already active
python run.py
```

The server starts on the host/port from `.env` (defaults: `http://localhost:3005`). With `DEBUG=true` (the default), Uvicorn reloads on source changes, so you can edit Python files in `app/` and your browser will pick up changes after a refresh.

Open `http://localhost:3005` in your browser, upload a short test video, and walk through the pipeline end-to-end to confirm your environment is working.

### Common issues

- **`ffmpeg: command not found`** — install FFmpeg (see Prerequisites) and reopen your shell.
- **Port already in use** — change `PORT` in `.env` and restart.
- **Vision backend errors** — confirm `VISION_BACKEND` in `.env` matches a backend that is actually installed and reachable. The README's [Troubleshooting section](README.md#troubleshooting) has more detail.

## Making Changes

1. **Create a branch from `main`**, named for the kind of change:

   ```bash
   git checkout main
   git pull upstream main
   git checkout -b <type>/<short-description>
   ```

   Use one of these prefixes: `feature/`, `fix/`, `refactor/`, `docs/`, `chore/`. Keep the description short and kebab-case (e.g. `fix/scene-detection-empty-input`).

2. **Make focused commits.** One logical change per commit. Write commit messages in the imperative ("Add Ollama backend support", not "Added…").

3. **Match the existing style.** Python code follows standard PEP 8 conventions. Keep functions small, prefer explicit names, and follow the layering you see in `app/services/`.

4. **Verify your change end-to-end.** AutoNarrate does not yet have an automated test suite, so manual verification is the bar:

   - Start the server with `python run.py`.
   - Exercise the path you changed (upload, processing, edit, render).
   - Confirm the server logs are clean — no new tracebacks or warnings introduced by your change.
   - For backend or pipeline changes, test with at least one short MP4 to confirm the full pipeline still completes.

   If you add a feature that is reasonably testable in isolation, please include tests with your PR — even a single `pytest` file is a great start.

## Opening a Pull Request

1. Push your branch to your fork:

   ```bash
   git push -u origin <your-branch>
   ```

2. Open a PR against `apoorvdixit88/autonarrate:main` from the GitHub UI, or:

   ```bash
   gh pr create --repo apoorvdixit88/autonarrate \
     --base main \
     --title "<type>: <imperative summary>" \
     --body "..."
   ```

3. **PR title** — use [Conventional Commits](https://www.conventionalcommits.org/) style: `feat: …`, `fix: …`, `docs: …`, `refactor: …`, `chore: …`.

4. **PR description** — include:

   - A one-paragraph summary of what changed and why.
   - A `Closes #<issue-number>` line if your PR resolves an open issue (this auto-closes the issue when the PR merges).
   - A short **Test plan** listing the specific things you verified manually (and any automated tests you added).
   - Screenshots or short clips if your change touches the UI.

5. **Keep PRs focused.** One concern per PR. If you spot an unrelated bug while working, file a separate issue rather than bundling the fix into your current PR.

6. **Respond to review.** A reviewer may request changes — push follow-up commits to the same branch and reply in the PR thread. Do not force-push to a PR under review unless asked.

7. **CI and merging.** Once review is approved and any checks are green, a maintainer will merge. Please don't merge your own PRs.

## Reporting Bugs and Requesting Features

Open an issue on [GitHub Issues](https://github.com/apoorvdixit88/autonarrate/issues). For bugs, include:

- Your OS, Python version, and FFmpeg version
- The configured `VISION_BACKEND`
- Steps to reproduce and the actual vs. expected behavior
- Any relevant terminal output or stack trace

Thanks for helping make AutoNarrate better!
