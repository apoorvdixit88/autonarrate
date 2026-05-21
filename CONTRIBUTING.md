# Contributing to AutoNarrate

Thanks for your interest in contributing! This guide will get you from a fresh clone to your first pull request.

## Table of Contents

- [Setting up the dev environment](#setting-up-the-dev-environment)
- [Running the project locally](#running-the-project-locally)
- [Opening a pull request](#opening-a-pull-request)
- [Reporting bugs and requesting features](#reporting-bugs-and-requesting-features)

## Setting up the dev environment

### Prerequisites

You'll need the following installed on your machine:

- **Python 3.10 or newer** — check with `python3 --version`
- **FFmpeg** — required for all video processing
  - macOS: `brew install ffmpeg`
  - Ubuntu/Debian: `sudo apt update && sudo apt install ffmpeg`
  - Windows: `choco install ffmpeg`
- **Git** — for cloning and submitting changes
- **An AI backend** — at least one of: Claude Code CLI, OpenCode CLI, OpenAI API key, Anthropic API key, or a local Ollama install. See the [Quick Start](README.md#quick-start) in the README for setup details.

### Fork and clone

1. Fork the repository on GitHub: <https://github.com/apoorvdixit88/autonarrate>
2. Clone your fork locally:

   ```bash
   git clone https://github.com/<your-username>/autonarrate.git
   cd autonarrate
   ```

3. Add the upstream remote so you can pull in changes from `main`:

   ```bash
   git remote add upstream https://github.com/apoorvdixit88/autonarrate.git
   ```

### Install dependencies

Create a virtual environment and install the Python dependencies:

```bash
python3 -m venv venv
source venv/bin/activate          # Windows: venv\Scripts\activate
pip install -r requirements.txt
```

### Configure environment variables

Copy the example environment file and edit it for your local setup:

```bash
cp .env.example .env
```

At minimum, pick a `VISION_BACKEND` (one of `claude_code`, `opencode`, `ollama`, `openai`, `anthropic`) and provide any matching API keys. See the [Configuration](README.md#configuration) section of the README for the full list of variables.

## Running the project locally

With the virtual environment activated:

```bash
python run.py
```

By default, the server listens on `http://localhost:3005`. Open that URL in your browser to use the upload page and editor.

If port 3005 is already in use, change `PORT` in `.env` to a free port.

### Quick sanity check

Once the server is running, confirm the basics:

1. Upload a short test video on the home page.
2. Watch the terminal logs for the processing pipeline (scene detection → frame analysis → narration → TTS).
3. Open the editor view and preview a segment.

If any step fails, check the [Troubleshooting](README.md#troubleshooting) section of the README before opening an issue.

## Opening a pull request

We follow a standard GitHub fork-and-PR workflow.

### Before you start coding

- For non-trivial changes, open an issue first to discuss the approach. This avoids wasted work if a different design is preferred.
- For small fixes (typos, docs, obvious bugs), feel free to skip straight to a PR.

### Branch from an up-to-date `main`

```bash
git checkout main
git pull upstream main
git checkout -b <type>/<short-description>
```

Use one of these branch prefixes:

- `feature/` — new functionality
- `fix/` — bug fixes
- `refactor/` — internal restructuring without behavior change
- `docs/` — documentation only
- `chore/` — tooling, dependencies, build

Example: `fix/freeze-frame-audio-drift`.

### Make focused commits

- Keep each commit small and self-contained.
- Write commit messages in the imperative mood ("Add freeze-frame fallback" not "Added freeze-frame fallback").
- Follow [Conventional Commits](https://www.conventionalcommits.org/) where reasonable (e.g. `fix: handle empty narration segments`).

### Test your change

Before pushing:

- Run the server locally and exercise the affected code path end-to-end.
- If you touched the processing pipeline, run it on at least one short video to confirm the output looks right.
- If the project has automated tests, run them with `pytest` (or the project's documented command) and make sure everything passes.
- Verify no secrets, large binaries, or generated files have been staged accidentally.

### Push and open the PR

```bash
git push -u origin <your-branch>
```

Then open a pull request against `apoorvdixit88/autonarrate:main`. Your PR description should include:

- **What** changed — one short paragraph.
- **Why** — link the related issue with `Closes #<issue-number>` if applicable.
- **How you tested it** — the steps you ran locally, including any edge cases you verified.
- **Screenshots or recordings** — for UI changes, attach a before/after.

### Review

A maintainer will review your PR and may request changes. Push additional commits to the same branch to address feedback. Once CI is green and the review is approved, a maintainer will merge.

## Reporting bugs and requesting features

- **Bugs**: open a GitHub issue with steps to reproduce, expected vs. actual behavior, and your environment (OS, Python version, FFmpeg version, vision backend).
- **Feature requests**: describe the use case first, then the proposed solution. Use cases are easier to evaluate than implementations.

Thanks again for contributing!
