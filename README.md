# Code Explainer — Plain-English Codebase Guide

Small, zero-dependency app that explains any codebase in simple terms. Point it at a folder and it tells you **what each file does**, **tech stack**, **where to start reading**, and **how files connect**.

No API key needed. Explanations are heuristic (no LLM) — offline and free.

## Local-only by design
- **Stdlib only** — `ast`, `http.server`, `pathlib`, etc. No `pip install`, no accounts, no keys.
- **Loopback only** — the server binds `127.0.0.1`, so it's reachable from your machine and nothing else (not even your LAN).
- **No outside calls** — no CDNs, fonts, analytics, or APIs. The browser page talks only to your own local server. Your code never leaves the machine.
- **Works offline** — disconnect from the internet and everything still runs.

## Features
- **Scans many languages**: Python, JavaScript/TypeScript, Java, Go, PHP, Ruby, C#, C/C++, Rust + config/docs
- **Per-file plain English**: e.g. *“Handles login — 2 functions, small and focused. Works with: flask.”*
- **Per-function one-liners**: signature + docstring/comment or humanized name (e.g. `login(user, password) — Check credentials and return a token.`)
- **🔍 In-depth explanations**: click any function for a deep dive — purpose, parameters (required/optional), step-by-step logic walkthrough, returns, errors it can raise, calls, and called-by. AST-precise for Python, heuristic for Java/C#/C++/etc.
- **Call graph**: who calls whom (AST-precise for Python, heuristic for Java/C#/C++), shown in CLI, web “Who calls whom” card, and Markdown export
- **Project overview**: size, languages, stack detected (`package.json` → Node, `requirements.txt` → Python, etc.), suggested reading order
- **Entry points**: files nothing else imports — where to start
- **Imports graph**: which files depend on which
- **Search + filters**: by name / language / role
- **Preview / Export**: view file snippet, download `CODE_EXPLAINED.md` or JSON
- **Pick folders two ways**: 🪟 Windows… (native folder popup) or 📁 Browse (in-page list, Windows drives supported)

## Quick Start

### Web UI (recommended)
```bash
python code_explainer.py --web
# opens http://127.0.0.1:8000
python code_explainer.py --web --port 9000
python code_explainer.py --web "C:\MyProject"
```

### CLI
```bash
python code_explainer.py "C:\path\to\any-project"
python code_explainer.py "C:\path\to\any-project" --deep login   # deep dive one function
python code_explainer.py .
```

## How it works
1. `find_code_files()` walks the folder, skipping `.git`, `node_modules`, `venv`, etc.
2. `parse_python_file()` uses `ast` for Python; `parse_generic_file()` uses regex for JS/TS/Java/Go/PHP/etc.
3. `explain_file()` maps filename/directory + symbols + imports + docstring to a plain-English sentence (heuristic, no LLM).
4. `project_summary()` detects stack and writes a one-paragraph overview.

Single file, stdlib only (`ast`, `http.server`, `pathlib`).

## Tips
- **Read order**: config → entry points → files they import → `utils/helpers` last.
- Use **Markdown export** for sharing with teammates or feeding to an LLM.
- Large repos (>100 files): use the filter bar (e.g. `api`, `auth`, `.py`).

## Extending
- Add more `FILENAME_HINTS` / `DIR_HINTS` at the top for your domain.
- Heuristic-only by design (offline, zero-cost). If you want LLM summaries later, add a separate `llm_explain()` that falls back to `explain_file()`.
