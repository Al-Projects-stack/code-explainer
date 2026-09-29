#!/usr/bin/env python3
"""
Code Explainer — describe any codebase in plain English.

- Scans a folder for many languages (Python, JS/TS, Java, Go, PHP, etc.)
- For each file explains in simple terms what it does
- Shows project overview, tech stack, entry points, dependencies
- CLI + Web UI (stdlib only, no pip install)
- Heuristic explanations only (no API key, no LLM — by design)

Usage:
  CLI:  python code_explainer.py <path>
  Web:  python code_explainer.py --web [path] [--port 8000]
"""

import ast
import re
import json
import os
import sys
import webbrowser
import urllib.parse
from dataclasses import dataclass, field
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------
IGNORE_DIRS = {".git", "__pycache__", "venv", ".venv", ".mypy_cache", ".pytest_cache",
               "node_modules", ".repoatlas", "dist", "build", ".next", ".nuxt",
               "target", "bin", "obj", "__MACOSX", ".idea", ".vscode"}

# Map extension -> language label
EXT_LANG = {
    ".py": "Python", ".js": "JavaScript", ".jsx": "JavaScript", ".ts": "TypeScript",
    ".tsx": "TypeScript", ".mjs": "JavaScript", ".cjs": "JavaScript",
    ".java": "Java", ".go": "Go", ".php": "PHP", ".rb": "Ruby",
    ".cs": "C#", ".cpp": "C++", ".c": "C", ".h": "C++", ".hpp": "C++",
    ".rs": "Rust", ".kt": "Kotlin", ".swift": "Swift", ".dart": "Dart",
    ".sql": "SQL", ".sh": "Shell", ".ps1": "PowerShell",
    ".html": "HTML", ".css": "CSS", ".scss": "SCSS", ".json": "JSON",
    ".yaml": "YAML", ".yml": "YAML", ".toml": "TOML", ".md": "Markdown",
    ".vue": "Vue", ".svelte": "Svelte",
}

# Which extensions we treat as "code" for deep scan vs just listing
CODE_EXTS = {".py",".js",".jsx",".ts",".tsx",".mjs",".cjs",".java",".go",".php",".rb",".cs",".cpp",".c",".h",".hpp",".rs",".kt",".swift",".dart",".vue",".svelte",".sh",".ps1",".sql"}
CONFIG_FILES = {"package.json","requirements.txt","pyproject.toml","Pipfile","go.mod","pom.xml","build.gradle","Gemfile","Cargo.toml","composer.json",".csproj","Dockerfile","docker-compose.yml","Makefile"}

# Filename heuristics -> plain English role
FILENAME_HINTS = {
    "main": "This is likely the main entry point — where the program starts.",
    "index": "This is an entry/barrel file — it pulls things together and is often the first file run.",
    "app": "Core application setup — wires the app together.",
    "server": "Sets up and runs the server — handles incoming requests.",
    "client": "Client-side code — runs in the browser/app.",
    "api": "Handles API communication — sending/receiving data from a server.",
    "auth": "Handles login, signup and permissions — who can do what.",
    "login": "Login-related — checking user credentials.",
    "user": "User-related — profiles, accounts or user data.",
    "db": "Database-related — storing and fetching data.",
    "database": "Database setup or queries.",
    "model": "Defines data shapes — what a 'User' or 'Product' looks like.",
    "config": "Configuration — settings that control how the app behaves.",
    "settings": "App settings / configuration.",
    "utils": "Helper functions — small reusable tools used across the app.",
    "helpers": "Helper functions — shared utilities.",
    "helper": "Helper utilities.",
    "common": "Shared/common code used in many places.",
    "lib": "Library/shared code.",
    "service": "Business logic / service layer — the 'work' of the app.",
    "controller": "Handles web requests — decides what to do when a URL is visited.",
    "route": "Defines URL routes — maps web addresses to code.",
    "router": "Routing — decides which code runs for which URL.",
    "middleware": "In-between code that runs before/after requests (e.g. auth checks).",
    "handler": "Handles a specific task or event.",
    "component": "UI component — a piece of the user interface.",
    "view": "UI / view layer — what the user sees.",
    "page": "A page/screen of the app.",
    "layout": "Page layout — overall structure of pages.",
    "store": "State management — keeps track of app data.",
    "state": "Manages app state/data.",
    "context": "Shares data across components.",
    "hook": "React hook / reusable logic.",
    "test": "Tests — checks that code works correctly.",
    "spec": "Tests / specifications.",
    "mock": "Fake data for testing or development.",
    "seed": "Creates initial/example data.",
    "migration": "Database migration — changes the database structure.",
    "script": "Automation script — does a specific task.",
    "worker": "Background job — runs tasks behind the scenes.",
    "job": "Background job.",
    "queue": "Handles queued/background tasks.",
    "cache": "Caching — makes things faster by saving results.",
    "email": "Email handling.",
    "payment": "Payment / checkout logic.",
    "cart": "Shopping cart logic.",
    "order": "Order handling.",
    "product": "Product-related logic.",
    "admin": "Admin / dashboard features.",
    "dashboard": "Dashboard UI.",
    "style": "Styling — how things look.",
    "theme": "Theming / visual style.",
    "constant": "Defines fixed values used across the app.",
    "types": "Type definitions — describes data shapes for TypeScript.",
    "interface": "Type/interface definitions.",
    "enum": "Fixed set of options/values.",
    "validation": "Checks that data is correct.",
    "schema": "Data validation/schema.",
    "form": "Form handling — user input.",
    "upload": "File upload handling.",
    "image": "Image handling.",
    "file": "File handling.",
    "logger": "Logging — records what the app is doing.",
    "log": "Logging.",
    "error": "Error handling.",
    "exception": "Error/exception handling.",
    "security": "Security-related code.",
    "crypto": "Encryption / security.",
    "token": "Authentication tokens.",
    "session": "User sessions.",
}

DIR_HINTS = {
    "src": "Source code", "lib": "Library", "app": "App core", "components": "UI components",
    "pages": "App pages", "views": "Views", "controllers": "Controllers", "models": "Data models",
    "routes": "Routes", "api": "API layer", "services": "Services", "utils": "Utilities",
    "helpers": "Helpers", "assets": "Static assets", "public": "Public files", "static": "Static files",
    "tests": "Tests", "test": "Tests", "__tests__": "Tests", "spec": "Tests",
    "config": "Configuration", "scripts": "Scripts", "migrations": "DB migrations",
    "middleware": "Middleware", "hooks": "Hooks", "store": "State", "styles": "Styles",
    "css": "Styles", "auth": "Authentication",
}

@dataclass
class FileInfo:
    path: Path
    rel: str
    name: str
    stem: str
    ext: str
    language: str
    size_kb: float
    lines: int
    functions: list[str] = field(default_factory=list)
    classes: list[str] = field(default_factory=list)
    imports: list[str] = field(default_factory=list)
    exports: list[str] = field(default_factory=list)
    docstring: str = ""
    explanation: str = ""
    role: str = ""
    complexity: str = ""  # simple / medium / complex
    symbols: list[dict] = field(default_factory=list)  # per-function one-liners
    calls_out: list[str] = field(default_factory=list)  # func names this file calls


# ---------------------------------------------------------------------------
# Scanning helpers
# ---------------------------------------------------------------------------

def find_code_files(root: Path) -> list[Path]:
    files = []
    for dirpath, dirnames, filenames in os.walk(root):
        # skip ignored dirs
        dirnames[:] = [d for d in dirnames if d not in IGNORE_DIRS and not d.startswith(".")]
        for name in filenames:
            p = Path(dirpath) / name
            ext = p.suffix.lower()
            # include code + config + docs
            if ext in EXT_LANG or name in CONFIG_FILES or name.lower().startswith("dockerfile"):
                # skip huge minified / lock files partially
                if name in {"package-lock.json","yarn.lock","pnpm-lock.yaml","poetry.lock"}:
                    continue
                if p.stat().st_size > 2_000_000:  # skip >2MB
                    continue
                files.append(p)
    files.sort()
    return files


def read_head(path: Path, max_lines=80, max_chars=6000) -> str:
    try:
        text = path.read_text(encoding="utf-8", errors="ignore")
        lines = text.splitlines()[:max_lines]
        head = "\n".join(lines)
        return head[:max_chars]
    except Exception:
        return ""


def parse_python_file(path: Path) -> tuple[list[str], list[str], list[str], list[str], str]:
    funcs, classes, imports, exports = [], [], [], []
    doc = ""
    try:
        # utf-8-sig strips a BOM so ast.parse doesn't choke on Windows-written files
        src = path.read_text(encoding="utf-8-sig", errors="ignore")
        tree = ast.parse(src, filename=str(path))
        # module docstring
        d = ast.get_docstring(tree)
        if d:
            doc = d.strip().splitlines()[0][:180]
        for node in tree.body:
            if isinstance(node, ast.FunctionDef):
                funcs.append(f"{node.name} (line {node.lineno})")
                # __all__ exports
            elif isinstance(node, ast.AsyncFunctionDef):
                funcs.append(f"{node.name} (async, line {node.lineno})")
            elif isinstance(node, ast.ClassDef):
                classes.append(f"{node.name} (line {node.lineno})")
            elif isinstance(node, ast.Import):
                for alias in node.names:
                    imports.append(alias.name.split(".")[0])
            elif isinstance(node, ast.ImportFrom):
                if node.module:
                    imports.append(node.module.split(".")[0])
            elif isinstance(node, ast.Assign):
                # catch __all__
                for t in node.targets:
                    if isinstance(t, ast.Name) and t.id == "__all__":
                        if isinstance(node.value, (ast.List, ast.Tuple)):
                            for elt in node.value.elts:
                                if isinstance(elt, ast.Constant) and isinstance(elt.value, str):
                                    exports.append(elt.value)
        # also walk for nested? we only show top-level for clarity, but also count nested funcs as hints
        # imports via walk
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    mod = alias.name.split(".")[0]
                    if mod not in imports:
                        imports.append(mod)
            elif isinstance(node, ast.ImportFrom):
                if node.module and node.module.split(".")[0] not in imports:
                    imports.append(node.module.split(".")[0])
    except Exception as e:
        # fallback regex for broken syntax
        head = read_head(path)
        funcs += re.findall(r"^\s*def\s+(\w+)", head, re.M)
        classes += re.findall(r"^\s*class\s+(\w+)", head, re.M)
        imports += re.findall(r"^\s*import\s+(\w+)", head, re.M)
        imports += re.findall(r"^\s*from\s+(\w+)", head, re.M)
        funcs = [f"{f} (regex)" for f in funcs]
        classes = [f"{c} (regex)" for c in classes]
    return funcs, classes, imports, exports, doc


# Generic regex parsers for JS/TS etc.
JS_FUNC_RE = re.compile(r"(?:function\s+(\w+)|(?:const|let|var)\s+(\w+)\s*=\s*(?:async\s*)?\(.*?\)\s*=>|(?:async\s+)?(\w+)\s*\(.*?\)\s*\{)")
JS_CLASS_RE = re.compile(r"class\s+(\w+)")
JS_IMPORT_RE = re.compile(r"""(?:import\s+.*?from\s+['\"]([^'\"]+)['\"]|require\(\s*['\"]([^'\"]+)['\"]\))""")
JS_EXPORT_RE = re.compile(r"export\s+(?:default\s+)?(?:class|function|const|let|var)?\s*(\w+)")
GENERIC_FUNC_RE = re.compile(r"(?:function\s+(\w+)|def\s+(\w+)|func\s+(\w+))")
GENERIC_CLASS_RE = re.compile(r"class\s+(\w+)")

# ---------------------------------------------------------------------------
# Smarter explanations: per-symbol one-liners + call graph
# ---------------------------------------------------------------------------

def humanize_name(name: str) -> str:
    """Turn getUsers / create_app / CreateUser into 'get users' etc."""
    s = re.sub(r"([a-z0-9])([A-Z])", r"\1 \2", name)
    s = s.replace("_", " ").replace("-", " ").strip().lower()
    s = re.sub(r"\s+", " ", s)
    return s or name.lower()


def clean_comment_line(line: str) -> str:
    t = line.strip()
    # strip common markers: // /// # * /* */ /** <!-- --> -- "
    t = re.sub(r"^(///|//|#|--|\"\"\"|'''|\*|/\*+|\<!--|\"|')+", "", t).strip()
    t = re.sub(r"(\*/|-->|\"\"\"|''')$", "", t).strip()
    t = re.sub(r"^[\*\-\:\|]+\s*", "", t).strip()
    # skip annotations / decorators / tags
    if not t or t.startswith("@") or t.startswith("<") or t.startswith("["):
        return ""
    if len(t) < 4:
        return ""
    return t[:140]


def preceding_comment(lines: list[str], def_idx: int, max_back: int = 6) -> str:
    """Look above a def line for a // # * /** comment to use as a hint.

    Only real comment lines count — plain code above the def must NOT
    leak into the hint (that was producing hints like
    'void helper() {}' for the next function).
    """
    collected = []
    i = def_idx - 1
    steps = 0
    while i >= 0 and steps < max_back:
        raw = lines[i]
        t = raw.strip()
        steps += 1
        if not t:
            i -= 1
            continue
        # allow decorators/annotations/attributes above the def
        if t.startswith("@") or t.startswith("["):
            i -= 1
            continue
        # lone modifier line belonging to this def (e.g. "public" on its own line)
        if re.match(r"^(public|private|protected|internal|static|final|async|override|virtual|sealed|abstract|partial|extern)\s*$", t):
            i -= 1
            continue
        # must look like a comment, otherwise stop
        if not (t.startswith("//") or t.startswith("#") or t.startswith("/*")
                or t.startswith("*") or t.startswith("<!--") or t.startswith("--")
                or t.startswith('"""') or t.startswith("'''") or t.startswith('"')):
            break
        cleaned = clean_comment_line(t)
        if cleaned:
            collected.append(cleaned)
            # if we hit an opening block marker, stop
            if "/**" in raw or "/*" in raw or '"""' in raw:
                break
        i -= 1
        continue
    if not collected:
        return ""
    collected.reverse()
    # prefer the closest meaningful line
    return collected[-1][:140]


def python_symbols(src: str) -> list[dict]:
    """AST-based per-function/class details: signature, doc hint, calls."""
    out: list[dict] = []
    try:
        # strip BOM if present (e.g. PowerShell utf8 output)
        tree = ast.parse(src.lstrip("\ufeff"))
    except Exception:
        return out
    for node in tree.body:
        # top-level functions
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            doc = (ast.get_docstring(node) or "").strip().splitlines()
            hint = doc[0][:140] if doc and len(doc[0]) > 3 else ""
            args = [a.arg for a in node.args.args if a.arg not in {"self", "cls"}][:5]
            calls: set[str] = set()
            for n in ast.walk(node):
                if isinstance(n, ast.Call):
                    f = n.func
                    if isinstance(f, ast.Name):
                        calls.add(f.id)
                    elif isinstance(f, ast.Attribute):
                        calls.add(f.attr)
            out.append({
                "name": node.name, "kind": "func", "line": node.lineno,
                "signature": f"{node.name}({', '.join(args)})",
                "hint": hint or humanize_name(node.name),
                "calls": sorted(calls)[:12],
            })
        elif isinstance(node, ast.ClassDef):
            doc = (ast.get_docstring(node) or "").strip().splitlines()
            hint = doc[0][:140] if doc and len(doc[0]) > 3 else ""
            out.append({
                "name": node.name, "kind": "class", "line": node.lineno,
                "signature": f"class {node.name}",
                "hint": hint or humanize_name(node.name),
                "calls": [],
            })
            # methods (one level)
            for item in node.body:
                if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    if item.name.startswith("__") and item.name.endswith("__"):
                        continue
                    mdoc = (ast.get_docstring(item) or "").strip().splitlines()
                    mhint = mdoc[0][:140] if mdoc and len(mdoc[0]) > 3 else ""
                    margs = [a.arg for a in item.args.args if a.arg not in {"self", "cls"}][:5]
                    mcalls: set[str] = set()
                    for n in ast.walk(item):
                        if isinstance(n, ast.Call):
                            f = n.func
                            if isinstance(f, ast.Name):
                                mcalls.add(f.id)
                            elif isinstance(f, ast.Attribute):
                                mcalls.add(f.attr)
                    out.append({
                        "name": f"{node.name}.{item.name}", "kind": "method",
                        "line": item.lineno,
                        "signature": f"{item.name}({', '.join(margs)})",
                        "hint": mhint or humanize_name(item.name),
                        "calls": sorted(mcalls)[:12],
                    })
    return out[:24]


# Per-language def-line patterns used for line numbers + signatures.
# Each entry: (regex with named group 'name', kind)
DEF_PATTERNS: dict[str, list[tuple[str, str]]] = {
    ".java": [
        (r"^\s*(?:@\w+\s*)*(?:public|private|protected)?\s*(?:static\s+|final\s+|abstract\s+|synchronized\s+)*(?:[\w\<\>\[\]\.]+\s+)?(?P<name>[A-Za-z_]\w*)\s*\(.*?\)\s*(?:throws\s+[\w,\s\.]+)?\s*\{", "func"),
        (r"^\s*(?:public\s+|protected\s+|private\s+)?(?:class|interface|enum|record)\s+(?P<name>\w+)", "class"),
    ],
    ".cs": [
        (r"^\s*(?:public|private|protected|internal)\s+(?:static\s+|async\s+|virtual\s+|override\s+|sealed\s+|abstract\s+|extern\s+)*(?:[\w<>\[\]\?,\s]+\s+)?(?P<name>[A-Za-z_]\w*)\s*\(.*?\)\s*(?:=>|\{|:)", "func"),
        (r"^\s*(?:public\s+|private\s+|protected\s+|internal\s+)?(?:sealed\s+|abstract\s+|static\s+|partial\s+)*(?:class|interface|record|struct|enum)\s+(?P<name>\w+)", "class"),
    ],
    ".cpp": [
        (r"(?P<name>[A-Za-z_]\w*)::(?P<meth>[A-Za-z_]\w*)\s*\(.*?\)\s*(?:const)?\s*\{", "func"),
        (r"^\s*(?:inline\s+|static\s+|virtual\s+|constexpr\s+|explicit\s+)*(?:[\w:<>\s\*&]+?\s+)(?P<name>[A-Za-z_]\w*)\s*\(.*?\)\s*(?:const\s*)?(?:\{|;|->)", "func"),
        (r"^\s*(?:class|struct|enum\s+class|namespace)\s+(?P<name>\w+)", "class"),
    ],
    ".c": [
        (r"^\s*(?:inline\s+|static\s+)*(?:[\w\s\*]+?\s+)(?P<name>[A-Za-z_]\w*)\s*\(.*?\)\s*(?:\{|;)", "func"),
        (r"^\s*(?:struct|enum|union)\s+(?P<name>\w+)", "class"),
    ],
    ".h": [
        (r"(?P<name>[A-Za-z_]\w*)::(?P<meth>[A-Za-z_]\w*)\s*\(.*?\)\s*(?:const)?\s*\{", "func"),
        (r"^\s*(?:inline\s+|static\s+|virtual\s+|constexpr\s+|explicit\s+)*(?:[\w:<>\s\*&]+?\s+)(?P<name>[A-Za-z_]\w*)\s*\(.*?\)\s*(?:const\s*)?(?:\{|;|->)", "func"),
        (r"^\s*(?:class|struct|enum\s+class|namespace)\s+(?P<name>\w+)", "class"),
    ],
    ".hpp": [
        (r"(?P<name>[A-Za-z_]\w*)::(?P<meth>[A-Za-z_]\w*)\s*\(.*?\)\s*(?:const)?\s*\{", "func"),
        (r"^\s*(?:inline\s+|static\s+|virtual\s+|constexpr\s+|explicit\s+)*(?:[\w:<>\s\*&]+?\s+)(?P<name>[A-Za-z_]\w*)\s*\(.*?\)\s*(?:const\s*)?(?:\{|;|->)", "func"),
        (r"^\s*(?:class|struct|enum\s+class|namespace)\s+(?P<name>\w+)", "class"),
    ],
}
DEF_PATTERNS[".js"] = [(r"^\s*(?:export\s+)?(?:async\s+)?function\s+(?P<name>[A-Za-z_]\w*)\s*\(", "func")]
DEF_PATTERNS[".ts"] = DEF_PATTERNS[".js"]

SKIP_NAMES = {"if","for","while","switch","catch","return","sizeof","typeid","alignof",
              "foreach","using","lock","when","where","synchronized","try","else"}


def generic_symbols(ext: str, text: str) -> list[dict]:
    """Regex-based per-symbol details for non-Python files."""
    lines = text.splitlines()[:400]
    out: list[dict] = []
    seen: set[str] = set()
    patterns = DEF_PATTERNS.get(ext, [])
    if not patterns:
        # fallback: reuse already-found names (no line info)
        return out
    for idx, line in enumerate(lines):
        for pat, kind in patterns:
            m = re.search(pat, line)
            if not m:
                continue
            gd = m.groupdict()
            # C++ scoped match has name=meth handling
            name = gd.get("meth") or gd.get("name") or ""
            if not name or name.lower() in SKIP_NAMES or len(name) < 2:
                continue
            # skip all-caps macros / constants
            if name.isupper() and kind == "func":
                continue
            key = f"{kind}:{name}:{idx}"
            if key in seen:
                continue
            seen.add(key)
            sig = line.strip()[:110]
            # trim body opener
            sig = re.sub(r"\s*\{.*$", "", sig)
            hint = preceding_comment(lines, idx) or humanize_name(name)
            out.append({"name": name, "kind": kind, "line": idx + 1,
                        "signature": sig, "hint": hint, "calls": []})
            break  # one symbol per line is enough
        if len(out) >= 24:
            break
    # dedupe by name keeping first (lowest line)
    uniq: dict[str, dict] = {}
    for s in out:
        if s["name"] not in uniq:
            uniq[s["name"]] = s
    return list(uniq.values())[:20]


def build_call_edges(text: str, known_funcs: set[str]) -> set[str]:
    """Rough call graph: names followed by '(' that match a known local func."""
    if not known_funcs or not text:
        return set()
    found = set(re.findall(r"\b([A-Za-z_]\w*)\s*\(", text))
    # case-sensitive match first, fall back to lower
    lower_map = {f.lower(): f for f in known_funcs}
    edges = set()
    for f in found:
        if f in known_funcs:
            edges.add(f)
        elif f.lower() in lower_map and len(f) > 3:
            edges.add(lower_map[f.lower()])
    return edges


def file_calls_out(ftext: str, symbols: list[dict], known_funcs: set[str]) -> set[str]:
    """Calls made by this file, excluding pure definition occurrences.

    A `name(` on the same line as that function's own definition doesn't
    count — otherwise every function 'calls itself'. A sibling call on the
    same line (e.g. `int main() { helper(); }`) still counts because the
    name differs from the def on that line.
    """
    if not known_funcs or not ftext:
        return set()
    lines = ftext.splitlines()[:500]
    # short-name -> def line (1-indexed) for funcs defined in this file
    def_line: dict[str, int] = {}
    for s in symbols or []:
        n = str(s.get("name", "")).split(".")[-1]
        ln = s.get("line")
        if n and isinstance(ln, int) and n not in def_line:
            def_line[n] = ln
    lower_map = {f.lower(): f for f in known_funcs}
    edges: set[str] = set()
    for idx, line in enumerate(lines, start=1):
        for m in re.finditer(r"\b([A-Za-z_]\w*)\s*\(", line):
            raw = m.group(1)
            target = raw if raw in known_funcs else lower_map.get(raw.lower(), "")
            if not target:
                continue
            if len(target) <= 2:
                continue
            # skip the definition occurrence itself
            if def_line.get(target) == idx and raw == target:
                continue
            # for case-insensitive fallback, also skip def line
            if raw.lower() == target.lower() and def_line.get(target) == idx:
                # allow it only if the line also contains a call AFTER the signature,
                # e.g. `int main() { helper(); }` — but that match is for a
                # different name, so reaching here means raw == target on its
                # own def line -> skip
                continue
            edges.add(target)
    return edges


# ---------------------------------------------------------------------------
# In-depth explanations: per-function deep dives
# ---------------------------------------------------------------------------

def _expr_short(node, limit: int = 64) -> str:
    """Short readable form of an AST expression, e.g. `user in db`."""
    try:
        s = ast.unparse(node).replace("\n", " ")  # py3.9+
    except Exception:
        s = ""
    s = (s or "?").strip()
    return s if len(s) <= limit else s[:limit - 3] + "..."


def _call_name(call: ast.Call) -> str:
    f = call.func
    if isinstance(f, ast.Name):
        return f.id
    if isinstance(f, ast.Attribute):
        return f.attr
    return ""


def _describe_stmt(st) -> str | None:
    """One plain-English sentence for a single statement. None = skip noise."""
    if isinstance(st, ast.For):
        tgt = _expr_short(st.target, 24)
        return f"Loops over `{_expr_short(st.iter)}` — repeats the block for each item as `{tgt}`."
    if isinstance(st, ast.AsyncFor):
        return f"Loops (async) over `{_expr_short(st.iter)}` — repeats for each item."
    if isinstance(st, ast.While):
        return f"Keeps looping while `{_expr_short(st.test)}` stays true."
    if isinstance(st, ast.If):
        return f"Checks whether `{_expr_short(st.test)}` — takes one path if yes, another if no."
    if isinstance(st, ast.Return):
        return f"Returns `{_expr_short(st.value)}` to the caller." if st.value else "Returns with no value (done)."
    if isinstance(st, ast.Raise):
        return f"Raises an error (`{_expr_short(st.exc or st.cause)}`) — stops here when something is wrong."
    if isinstance(st, ast.Assert):
        return f"Asserts `{_expr_short(st.test)}` — crashes loudly if that isn't true."
    if isinstance(st, ast.Try):
        return "Tries a risky block, with a fallback plan if it throws an error."
    if isinstance(st, (ast.With, ast.AsyncWith)):
        return "Opens/manages a resource that cleans itself up afterwards (file, lock, connection…)."
    if isinstance(st, (ast.FunctionDef, ast.AsyncFunctionDef)):
        return f"Defines a helper `{st.name}` inside (only usable here)."
    if isinstance(st, ast.ClassDef):
        return f"Defines a class `{st.name}` inside (only usable here)."
    if isinstance(st, (ast.Import, ast.ImportFrom)):
        return None  # noise at function level
    if isinstance(st, ast.Expr) and isinstance(st.value, ast.Call):
        name = _call_name(st.value) or "something"
        return f"Calls `{name}` (uses its result, doesn't store it)."
    if isinstance(st, ast.Expr):
        return f"Evaluates `{_expr_short(st.value)}`."
    if isinstance(st, ast.Assign):
        tgts = ", ".join(_expr_short(t, 24) for t in st.targets)
        if isinstance(st.value, ast.Call):
            return f"Sets `{tgts}` to whatever `{_call_name(st.value) or '…'}` gives back."
        return f"Sets `{tgts}` to `{_expr_short(st.value)}`."
    if isinstance(st, ast.AnnAssign):
        return f"Sets `{_expr_short(st.target, 24)}` (with a type hint)."
    if isinstance(st, ast.AugAssign):
        return f"Updates `{_expr_short(st.target, 24)}` in place (`{type(st.op).__name__}`)."
    if isinstance(st, (ast.Delete,)):
        return "Cleans up / deletes something."
    if isinstance(st, (ast.Pass, ast.Break, ast.Continue)):
        return {"Pass": None, "Break": "Stops the loop early.",
                "Continue": "Skips to the next loop round."}[type(st).__name__]
    if isinstance(st, (ast.Global, ast.Nonlocal)):
        return None
    return None


def python_deepdive(src: str, qualname: str) -> dict | None:
    """Full walkthrough of one Python function/method. None if not found."""
    try:
        tree = ast.parse(src.lstrip("\ufeff"))
    except Exception:
        return None
    short = qualname.split(".")[-1]
    target = None
    parent_cls = None
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name in (qualname, short):
            target = node
            break
        if isinstance(node, ast.ClassDef):
            for item in node.body:
                if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)) and item.name in (qualname, short, qualname.split(".")[-1]):
                    if qualname == f"{node.name}.{item.name}" or item.name == short:
                        target, parent_cls = item, node.name
                        break
    if target is None:
        return None
    doc = (ast.get_docstring(target) or "").strip()
    all_args = list(target.args.args)
    defaults = list(target.args.defaults)
    params = []
    plain = [a.arg for a in all_args if a.arg not in {"self", "cls"}]
    first_default = len(all_args) - len(defaults)
    for i, a in enumerate(all_args):
        if a.arg in {"self", "cls"}:
            continue
        d = ""
        if i >= first_default:
            d = _expr_short(defaults[i - first_default], 30)
        params.append({"name": a.arg, "human": humanize_name(a.arg),
                       "default": d, "required": not d})
    steps = []
    body = list(target.body)
    # skip the docstring itself (a bare string as first statement) — it's
    # shown as Purpose above, not a "step"
    if body and isinstance(body[0], ast.Expr):
        v = body[0].value
        if isinstance(v, ast.Constant) and isinstance(v.value, str):
            body = body[1:]
    for st in body:
        s = _describe_stmt(st)
        if s:
            steps.append(s)
    # complexity: 1 + branches/loops/handlers
    complexity = 1
    rets, raises, calls = [], [], []
    for n in ast.walk(target):
        if isinstance(n, (ast.If, ast.For, ast.AsyncFor, ast.While, ast.ExceptHandler, ast.With, ast.Assert)):
            complexity += 1
        elif isinstance(n, ast.BoolOp):
            complexity += max(0, len(n.values) - 1)
        elif isinstance(n, ast.Return) and n.value is not None:
            r = _expr_short(n.value)
            if r not in rets:
                rets.append(r)
        elif isinstance(n, ast.Raise):
            r = _expr_short(n.exc or n.cause)
            if r not in raises:
                raises.append(r)
        elif isinstance(n, ast.Call):
            c = _call_name(n)
            if c and c not in calls:
                calls.append(c)
    span = (getattr(target, "end_lineno", target.lineno) or target.lineno) - target.lineno + 1
    level = "simple" if complexity <= 3 else ("medium" if complexity <= 7 else "complex")
    words = humanize_name(short)
    purpose = doc.splitlines()[0] if doc else f"Does '{words}' — no docstring, so this is inferred from the name and steps below."
    return {
        "language": "Python", "name": target.name,
        "qualified": f"{parent_cls}.{target.name}" if parent_cls else target.name,
        "kind": "method" if parent_cls else ("async function" if isinstance(target, ast.AsyncFunctionDef) else "function"),
        "line": target.lineno, "span_lines": span,
        "signature": f"{target.name}({', '.join(plain)})",
        "purpose": purpose, "doc": doc,
        "params": params, "steps": steps[:12], "steps_total": len(steps),
        "returns": rets[:5], "raises": raises[:5], "calls": calls[:15],
        "complexity": complexity, "level": level,
    }


def _brace_body(lines: list[str], start_idx: int, max_lines: int = 120) -> list[str]:
    """Capture a { ... } body starting at/after start_idx via brace counting."""
    body: list[str] = []
    depth = 0
    started = False
    for i in range(start_idx, min(len(lines), start_idx + max_lines)):
        ln = lines[i]
        depth += ln.count("{") - ln.count("}")
        if "{" in ln:
            started = True
        if started:
            body.append(ln)
        if started and depth <= 0 and i > start_idx:
            break
    return body


def generic_deepdive(ext: str, text: str, name: str) -> dict | None:
    """Heuristic deep dive for Java/C#/C++/etc. based on signature + body scan."""
    lines = text.splitlines()[:600]
    short = name.split(".")[-1].split("::")[-1]
    def_idx = None
    sig = ""
    for idx, ln in enumerate(lines):
        for pat, _kind in DEF_PATTERNS.get(ext, []):
            m = re.search(pat, ln)
            if not m:
                continue
            gd = m.groupdict()
            cand = gd.get("meth") or gd.get("name") or ""
            if cand == short or cand == name:
                def_idx, sig = idx, ln.strip()[:160]
                break
        if def_idx is not None:
            break
    if def_idx is None:
        # fallback: any line calling/defining name(
        for idx, ln in enumerate(lines):
            if re.search(r"\b" + re.escape(short) + r"\s*\(", ln):
                def_idx, sig = idx, ln.strip()[:160]
                break
    if def_idx is None:
        return None
    comment = preceding_comment(lines, def_idx)
    # params from the signature's (...)
    params = []
    pm = re.search(r"\((.*)\)", sig)
    if pm and pm.group(1).strip():
        for p in pm.group(1).split(",")[:8]:
            p = p.strip().strip("{};")
            if not p or p in {"void"}:
                continue
            pname = re.split(r"\s+", p)[-1].strip("*&[]. ")
            pname = re.sub(r"=.*", "", pname).strip()
            if pname:
                params.append({"name": pname, "human": humanize_name(pname), "default": "", "required": True})
    body = _brace_body(lines, def_idx) or lines[def_idx + 1:def_idx + 31]
    body_text = "\n".join(body)
    counts = {k: len(re.findall(p, body_text)) for k, p in {
        "branches": r"\b(if|else\s+if|switch|case|when)\b",
        "loops": r"\b(for|foreach|while|do)\b",
        "returns": r"\breturn\b",
        "errors": r"\b(throw|throws|catch|except|try)\b",
    }.items()}
    steps = []
    if counts["loops"]:
        steps.append(f"Repeats work in {counts['loops']} loop(s) (for/while) — the core repetition.")
    if counts["branches"]:
        steps.append(f"Makes {counts['branches']} decision(s) (if/switch) — different paths for different inputs.")
    if counts["errors"]:
        steps.append("Has error handling (try/catch/throw) — plans for things going wrong.")
    if counts["returns"]:
        steps.append(f"Hands back a result in {counts['returns']} place(s) (return).")
    in_body_comments = []
    for ln in body[1:]:
        t = ln.strip()
        # real comment lines only — never code
        if not (t.startswith("//") or t.startswith("#") or t.startswith("/*")
                or t.startswith("*") or t.startswith("<!--")):
            continue
        c = clean_comment_line(ln)
        if c and len(c) > 8:
            in_body_comments.append(c)
        if len(in_body_comments) >= 3:
            break
    calls = [c for c in re.findall(r"\b([A-Za-z_]\w*)\s*\(", body_text)
             if c != short and c.lower() not in SKIP_NAMES and len(c) > 2][:12]
    # dedupe, keep order
    calls = list(dict.fromkeys(calls))
    complexity = 1 + counts["branches"] + counts["loops"] + (1 if counts["errors"] else 0)
    level = "simple" if complexity <= 3 else ("medium" if complexity <= 7 else "complex")
    purpose = comment or f"Does '{humanize_name(short)}' — inferred from the name (no comment above it)."
    return {
        "language": EXT_LANG.get(ext, ext), "name": short, "qualified": name,
        "kind": "method/function", "line": def_idx + 1, "span_lines": len(body),
        "signature": re.sub(r"\s*\{.*$", "", sig), "purpose": purpose, "doc": comment,
        "params": params, "steps": steps, "steps_total": len(steps),
        "returns": [], "raises": [],
        "notes": in_body_comments, "calls": calls,
        "complexity": complexity, "level": level,
    }


def find_called_by(root: Path, symbol: str, own_rel: str = "", limit_files: int = 250) -> list[str]:
    """Which files mention `symbol(` (outside its own definition file). Cheap project grep."""
    short = symbol.split(".")[-1].split("::")[-1]
    if len(short) < 2:
        return []
    pat = re.compile(r"\b" + re.escape(short) + r"\s*\(")
    hits: list[str] = []
    try:
        files = find_code_files(root)
    except Exception:
        return []
    for p in files[:limit_files]:
        try:
            if p.stat().st_size > 200_000:
                continue
            if p.suffix.lower() not in CODE_EXTS:
                continue
            t = p.read_text(encoding="utf-8-sig", errors="ignore")
        except Exception:
            continue
        if not pat.search(t):
            continue
        try:
            rel = p.relative_to(root).as_posix()
        except Exception:
            rel = p.name
        if rel != own_rel:
            hits.append(rel)
        if len(hits) >= 10:
            break
    return hits


def deepdive_symbol(path: Path, symbol: str, root: Path | None = None) -> dict:
    """Shared by /api/deepdive and CLI --deep. Always returns a dict (may carry 'error')."""
    if not path.exists() or not path.is_file():
        return {"error": f"File not found: {path}"}
    ext = path.suffix.lower()
    try:
        text = path.read_text(encoding="utf-8-sig", errors="ignore")
    except Exception as e:
        return {"error": f"Cannot read file: {e}"}
    if ext == ".py":
        detail = python_deepdive(text, symbol)
    elif ext in CODE_EXTS:
        detail = generic_deepdive(ext, text, symbol)
    else:
        return {"error": f"No deep dive for {ext or 'this file type'} — code files only."}
    if not detail:
        return {"error": f"Symbol '{symbol}' not found in {path.name}."}
    try:
        rel = path.relative_to(root).as_posix() if root and path.is_relative_to(root) else path.name
    except Exception:
        rel = path.name
    detail["file"] = rel
    if root and root.is_dir():
        detail["called_by"] = find_called_by(root, detail.get("qualified", symbol), own_rel=rel)
    else:
        detail["called_by"] = []
    return detail


def print_deepdive(detail: dict) -> None:
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
    def _p(s):
        try:
            print(s)
        except UnicodeEncodeError:
            print(s.encode("ascii", "replace").decode("ascii"))
    if detail.get("error"):
        _p(f"Deep dive failed: {detail['error']}")
        return
    _p(f"\n=== Deep dive: {detail['qualified']}  ({detail['language']}, line {detail['line']}) ===\n")
    _p(f"Signature: {detail['signature']}")
    _p(f"Size: ~{detail['span_lines']} lines, complexity {detail['complexity']} ({detail['level']}).\n")
    _p(f"Purpose: {detail['purpose']}")
    if detail.get("params"):
        _p("\nParameters:")
        for p in detail["params"]:
            req = "required" if p["required"] else f"optional, default {p['default']}"
            _p(f"  - {p['name']} ('{p['human']}') — {req}")
    else:
        _p("\nParameters: none.")
    _p("\nHow it works, step by step:")
    if detail.get("steps"):
        for i, s in enumerate(detail["steps"], 1):
            _p(f"  {i}. {s}")
        if detail.get("steps_total", 0) > len(detail["steps"]):
            _p(f"  ... +{detail['steps_total'] - len(detail['steps'])} more steps inside.")
    else:
        _p("  (No step-by-step breakdown available — body is tiny or uses patterns I don't describe yet.)")
    if detail.get("notes"):
        _p("\nNotes found inside the code:")
        for n in detail["notes"]:
            _p(f"  - \"{n}\"")
    if detail.get("returns"):
        _p(f"\nReturns: {'; '.join(detail['returns'])}")
    if detail.get("raises"):
        _p(f"\nCan raise: {'; '.join(detail['raises'])}")
    if detail.get("calls"):
        _p(f"\nCalls: {', '.join(detail['calls'])}")
    if detail.get("called_by"):
        _p(f"\nCalled by (other files): {', '.join(detail['called_by'])}")
    _p("")


def parse_generic_file(path: Path, head: str) -> tuple[list[str], list[str], list[str], list[str], str]:
    funcs, classes, imports, exports = [], [], [], []
    doc = ""
    ext = path.suffix.lower()
    # docstring heuristic: first block comment / // or #
    m = re.search(r"(?:\/\*\*(.*?)\*\/|\"\"\"(.*?)\"\"\"|'''(.*?)'''|^#\s*(.+)|^\/\/\s*(.+))", head, re.S|re.M)
    if m:
        g = next((x for x in m.groups() if x), "")
        doc = g.strip().splitlines()[0][:180] if g else ""
        doc = re.sub(r"^[\s\*\#\/]+", "", doc).strip()

    if ext in {".js",".jsx",".ts",".tsx",".mjs",".cjs",".vue",".svelte"}:
        for a,b,c in JS_FUNC_RE.findall(head):
            name = a or b or c
            if name and name not in {"if","for","while","catch"}:
                funcs.append(name)
        classes = JS_CLASS_RE.findall(head)
        for a,b in JS_IMPORT_RE.findall(head):
            mod = (a or b or "").split("/")[-1].split(".")[0]
            if mod and not mod.startswith("."):
                imports.append(mod)
            elif (a or b or "").startswith("."):
                # local import: use filename
                local = Path(a or b).stem
                if local:
                    imports.append(local)
        exports = JS_EXPORT_RE.findall(head)
        # normalize
        funcs = [f"{f}" for f in funcs[:12]]
        classes = [f"{c}" for c in classes[:12]]
    elif ext == ".java":
        # match methods/constructors: modifiers + return type (or nothing for ctor) + name + (
        raw = re.findall(r"(?:public|private|protected)?\s*(?:static\s+)?(?:\w+\s+)?(\w+)\s*\(.*?\)\s*(?:throws\s+[\w,\s]+)?\s*\{", head)
        SKIP = {"if","for","while","switch","catch","synchronized","try","else"}
        funcs = [f for f in raw if f.lower() not in SKIP]
        classes = re.findall(r"(?:class|interface|enum|record)\s+(\w+)", head)
        imports = [x.split(".")[-1] for x in re.findall(r"import\s+([\w\.]+)", head)]
    elif ext == ".go":
        funcs = re.findall(r"func\s+(?:\(\w+\s+[\w\*]+\))?\s*(\w+)\s*\(", head)
        classes = []  # structs
        structs = re.findall(r"type\s+(\w+)\s+struct", head)
        classes = structs
        imports = re.findall(r'"([^"]+)"', head)  # rough
        imports = [x.split("/")[-1] for x in imports if "/" in x or "." not in x][:10]
    elif ext == ".php":
        funcs = re.findall(r"function\s+(\w+)\s*\(", head)
        classes = re.findall(r"class\s+(\w+)", head)
        imports = re.findall(r"use\s+([\w\\]+)", head)
        imports = [x.split("\\")[-1] for x in imports]
    elif ext in {".rb"}:
        funcs = re.findall(r"def\s+(\w+)", head)
        classes = re.findall(r"class\s+(\w+)", head)
        imports = re.findall(r"require\s+['\"]([^'\"]+)", head)
    elif ext in {".cs"}:
        raw = re.findall(r"^\s*(?:public|private|protected|internal)\s+(?:static\s+|async\s+|virtual\s+|override\s+|sealed\s+|abstract\s+)*[\w<>\[\],\s]*\s+(\w+)\s*\(.*?\)", head, re.M)
        SKIP_CS = {"if","for","while","foreach","switch","catch","using","lock","when","where"}
        funcs = [f for f in raw if f.lower() not in SKIP_CS]
        # also capture ctors (same name as class) — they lack return type
        ctors = re.findall(r"^\s*(?:public|private|protected|internal)\s+(\w+)\s*\(.*?\)\s*(?:\{|:)", head, re.M)
        for c in ctors:
            if c not in funcs and c[0].isupper():
                funcs.append(c)
        # dedupe preserve order
        seen=set(); uniq=[]
        for f in funcs:
            if f not in seen:
                seen.add(f); uniq.append(f)
        funcs=uniq
        classes = re.findall(r"(?:class|interface|record|struct|enum)\s+(\w+)", head)
        imports = re.findall(r"using\s+([\w\.]+)", head)
        imports = [x.split(".")[-1] for x in imports]
    elif ext in {".cpp",".c",".h",".hpp"}:
        # functions: return_type name(params) { or ;  — avoid if/for
        raw = re.findall(r"(?:^|\n)\s*(?:inline\s+|static\s+|virtual\s+|constexpr\s+)*\w[\w:<>\s\*&]*\s+(\w+)\s*\(.*?\)\s*(?:const)?\s*(?:\{|;|->)", head)
        SKIP_CPP = {"if","for","while","switch","catch","return","sizeof","typeid","alignof"}
        funcs = [f for f in raw if f not in SKIP_CPP]
        # also capture scope-qualified: Class::method
        scoped = re.findall(r"(\w+)::(\w+)\s*\(.*?\)\s*\{", head)
        for _, meth in scoped:
            if meth not in funcs:
                funcs.append(meth)
        classes = re.findall(r"(?:class|struct|enum\s+class|namespace)\s+(\w+)", head)
        imports = re.findall(r"#include\s+[<\"]([^>\"]+)", head)
    elif ext == ".rs":
        funcs = re.findall(r"fn\s+(\w+)", head)
        classes = re.findall(r"struct\s+(\w+)", head)
        imports = re.findall(r"use\s+([\w:]+)", head)
    elif ext in {".kt"}:
        funcs = re.findall(r"fun\s+(\w+)\s*\(", head)
        classes = re.findall(r"(?:class|interface|object|data\s+class)\s+(\w+)", head)
        imports = [x.split(".")[-1] for x in re.findall(r"import\s+([\w\.]+)", head)]
    elif ext in {".swift"}:
        funcs = re.findall(r"func\s+(\w+)\s*\(", head)
        classes = re.findall(r"(?:class|struct|enum)\s+(\w+)", head)
        imports = re.findall(r"import\s+(\w+)", head)
    elif ext in {".dart"}:
        funcs = re.findall(r"(?:\w+\s+)?(\w+)\s*\(.*?\)\s*(?:async\s*)?\{", head)
        classes = re.findall(r"class\s+(\w+)", head)
        imports = re.findall(r"import\s+['\"]([^'\"]+)", head)
        imports = [Path(x).stem for x in imports]
    else:
        # fallback
        funcs = re.findall(r"function\s+(\w+)", head)
        classes = re.findall(r"class\s+(\w+)", head)
        imports = []

    return funcs, classes, imports, exports, doc


def explain_file(info: FileInfo, all_stems: set[str], head: str) -> str:
    """Generate plain-English explanation — no LLM needed."""
    name = info.name
    stem = info.stem.lower()
    ext = info.ext
    lang = info.language
    dir_part = Path(info.rel).parent.as_posix().lower()

    # collect hints — longest (most specific) filename match wins,
    # so "controller" beats "user" in "UserController"
    role_hints = []
    best = max((k for k in FILENAME_HINTS if k in stem), key=len, default=None)
    if best:
        role_hints.append(FILENAME_HINTS[best])
    # dir hint
    for dpart in dir_part.split("/"):
        if dpart in DIR_HINTS:
            role_hints.append(f"Located in `{dpart}/` — {DIR_HINTS[dpart].lower()}.")
            break

    # what it contains
    parts = []
    # Language + size
    if lang in {"JSON","YAML","TOML","Markdown"}:
        if lang == "JSON":
            if "package" in stem:
                return "Project manifest — lists dependencies, scripts and project info (like an ingredients list). Not code that runs, but tells tools how to build/run the app."
            if "tsconfig" in stem:
                return "TypeScript configuration — tells the TypeScript compiler how to work."
            return f"Data file ({lang}) — stores structured data/settings, not program logic. {info.lines} lines."
        if lang == "Markdown":
            return f"Documentation file — explains the project in human language ({info.lines} lines). Not executed as code."
        return f"Configuration/data file ({lang}) — {info.lines} lines. Stores settings."

    # Config files
    if info.name in CONFIG_FILES or "dockerfile" in stem:
        cfg_map = {
            "package.json": "Node.js project manifest — lists JavaScript dependencies and npm scripts.",
            "requirements.txt": "Python dependencies list — what libraries this project needs.",
            "pyproject.toml": "Python project config — dependencies and tool settings.",
            "go.mod": "Go module definition — lists Go dependencies.",
            "cargo.toml": "Rust project manifest.",
            "pom.xml": "Java/Maven project config.",
            "gemfile": "Ruby dependencies.",
            "composer.json": "PHP dependencies.",
        }
        return cfg_map.get(info.name, f"Project configuration file — controls how the app is built or run ({info.lines} lines).")

    # Heuristic based on content
    n_func = len(info.functions)
    n_class = len(info.classes)
    n_imports = len(info.imports)

    # Simple role sentence
    if role_hints:
        base = role_hints[0]
    else:
        # infer from symbols
        if n_class > 0 and n_func > 3:
            base = "Defines classes and functions — likely core business logic or a reusable module."
        elif n_class > 0:
            base = "Defines a class/blueprint — models an object (like User, Product) or a service."
        elif n_func > 4:
            base = "A collection of helper functions — does specific tasks when called."
        elif n_func > 0:
            base = "Contains a few functions — performs focused tasks."
        elif "html" in ext:
            base = "Web page markup — structure of what the user sees."
        elif "css" in ext or "scss" in ext:
            base = "Styling — controls colors, layout and appearance."
        elif "sql" in ext:
            base = "Database queries/migrations — how data is stored or changed."
        elif "sh" in ext or "ps1" in ext:
            base = "Script — automates a task when run."
        elif info.lines < 20:
            base = "Small file — likely constants, types or a tiny utility."
        else:
            base = "General code file — part of the app's logic."

    # Complexity
    if info.lines > 400 or n_func > 15 or n_class > 5:
        complexity = "Large and fairly complex."
    elif info.lines > 150 or n_func > 7:
        complexity = "Medium-sized."
    else:
        complexity = "Small and focused."

    # Docstring hint
    doc_part = f" Starts with: \"{info.docstring}\"." if info.docstring and len(info.docstring) > 8 else ""

    # Imports hint
    if n_imports:
        imp_str = ", ".join(info.imports[:4])
        if len(info.imports) > 4:
            imp_str += f" +{len(info.imports)-4} more"
        import_part = f" Works with: {imp_str}."
    else:
        import_part = " No local dependencies — stands alone."

    # Functions/classes preview
    if n_class or n_func:
        preview = []
        if n_class:
            preview.append(f"{n_class} class{'es' if n_class!=1 else ''} ({', '.join([c.split()[0] for c in info.classes[:2]])})")
        if n_func:
            preview.append(f"{n_func} function{'s' if n_func!=1 else ''} ({', '.join([f.split()[0] for f in info.functions[:3]])})")
        preview_str = " Contains " + " and ".join(preview) + "."
    else:
        preview_str = ""

    explanation = f"{base} {complexity}{preview_str}{import_part}{doc_part}"
    # Trim to ~2 sentences-ish but keep informative
    if len(explanation) > 320:
        explanation = explanation[:317] + "..."
    return explanation


def analyze_file(path: Path, root: Path, all_stems: set[str]) -> FileInfo:
    rel = path.relative_to(root).as_posix() if path.is_relative_to(root) else str(path)
    ext = path.suffix.lower()
    lang = EXT_LANG.get(ext, "Text")
    if path.name in CONFIG_FILES or path.name.lower().startswith("dockerfile"):
        lang = "Config"
    try:
        size_kb = round(path.stat().st_size / 1024, 1)
    except:
        size_kb = 0
    try:
        text = path.read_text(encoding="utf-8-sig", errors="ignore")
        lines = text.count("\n") + 1 if text else 0
    except:
        lines = 0
        text = ""

    funcs, classes, imports, exports, doc = [], [], [], [], ""
    if ext == ".py":
        funcs, classes, imports, exports, doc = parse_python_file(path)
    elif ext in CODE_EXTS:
        head = text[:6000] if text else read_head(path)
        funcs, classes, imports, exports, doc = parse_generic_file(path, head)
    else:
        # config/docs: no symbols
        head = text[:2000]
        # try to extract doc
        if head.strip().startswith("#") or head.strip().startswith("//") or head.strip().startswith("/*"):
            doc = head.strip().splitlines()[0][:180]

    # Complexity string
    if lines > 400 or len(funcs) > 15:
        comp = "complex"
    elif lines > 150 or len(funcs) > 7:
        comp = "medium"
    else:
        comp = "simple"

    # per-symbol one-liners (richer than the plain func/class name lists)
    symbols: list[dict] = []
    try:
        if ext == ".py" and text:
            symbols = python_symbols(text)
        elif text and ext in CODE_EXTS:
            symbols = generic_symbols(ext, text[:20000])
    except Exception:
        symbols = []

    info = FileInfo(
        path=path, rel=rel, name=path.name, stem=path.stem, ext=ext, language=lang,
        size_kb=size_kb, lines=lines,
        functions=funcs[:20], classes=classes[:20],
        imports=imports[:20], exports=exports[:10],
        docstring=doc, complexity=comp,
        symbols=symbols,
    )
    # generate explanation after info built
    info.explanation = explain_file(info, all_stems, text[:4000])
    # role short — filename-based, not explanation-text-based
    # (checking the explanation string was fragile: any docstring with
    # the word "entry" flipped the role)
    if any(k in path.stem.lower() for k in {"main", "index", "app", "server", "program"}):
        info.role = "entry"
    elif "config" in lang.lower() or path.name in CONFIG_FILES:
        info.role = "config"
    elif "test" in path.stem.lower() or "spec" in path.stem.lower():
        info.role = "test"
    elif info.language in {"Markdown"}:
        info.role = "docs"
    elif len(funcs)==0 and len(classes)==0 and lines<30:
        info.role = "support"
    else:
        info.role = "code"
    return info


def detect_stack(root: Path, files: list[Path]) -> dict:
    names = {p.name for p in files}
    exts = [p.suffix.lower() for p in files]
    from collections import Counter
    lang_counts = Counter(EXT_LANG.get(e, "Other") for e in exts if e in EXT_LANG)
    stack = []
    if "package.json" in names: stack.append("Node.js / JavaScript")
    if any(n in names for n in {"requirements.txt","pyproject.toml","Pipfile","setup.py"}): stack.append("Python")
    if "go.mod" in names: stack.append("Go")
    if "pom.xml" in names or "build.gradle" in names or any(e==".java" for e in exts): stack.append("Java")
    if "Gemfile" in names: stack.append("Ruby")
    if "Cargo.toml" in names: stack.append("Rust")
    if "composer.json" in names: stack.append("PHP")
    if any(p.suffix==".cs" for p in files): stack.append("C#")
    if any(e in {".cpp",".c",".h",".hpp"} for e in exts): stack.append("C++")
    if "Dockerfile" in names or "docker-compose.yml" in names: stack.append("Docker")
    # frontend hint
    if any("react" in p.name.lower() for p in files) or any(p.suffix in {".tsx",".jsx"} for p in files):
        stack.append("React")
    if any(p.suffix==".vue" for p in files): stack.append("Vue")
    if any(p.suffix==".svelte" for p in files): stack.append("Svelte")

    return {"languages": dict(lang_counts.most_common()), "stack": stack}


def project_summary(root: Path, infos: list[FileInfo], stack: dict) -> str:
    n = len(infos)
    if n == 0:
        return "Empty folder — no code files found."
    total_lines = sum(i.lines for i in infos)
    langs = stack.get("languages", {})
    top_lang = max(langs, key=langs.get) if langs else "Mixed"
    n_code = sum(1 for i in infos if i.role=="code")
    n_config = sum(1 for i in infos if i.role=="config")
    # entry candidates: files not imported elsewhere (local imports only,
    # so stdlib names like "System"/"List" don't affect the result)
    local_stems = {i.stem.lower() for i in infos}
    all_imports = set()
    for i in infos:
        all_imports.update(x.lower() for x in i.imports if x.lower() in local_stems)
    entry_candidates = [i.name for i in infos if i.stem.lower() not in all_imports and i.role in {"code", "entry"}]
    # prioritize known entry names
    preferred = [c for c in entry_candidates if any(k in c.lower() for k in {"main","index","app","server","client"})]
    entry = preferred[:3] if preferred else entry_candidates[:3]

    lines_desc = f"~{total_lines} lines of code"
    if n <= 5:
        size_desc = "A tiny project — easy to grasp in one sitting."
    elif n <= 15:
        size_desc = "A small project — a few files working together."
    elif n <= 40:
        size_desc = "A medium-sized app — several modules with clear responsibilities."
    else:
        size_desc = "A larger codebase — many modules, likely with layers (UI, logic, data)."

    stack_str = ", ".join(stack.get("stack") or [top_lang]) or top_lang
    # Simple narrative
    parts = [
        f"This project has {n} files ({n_code} code, {n_config} config) and {lines_desc}.",
        f"Main language: {top_lang}. Stack detected: {stack_str}.",
        size_desc,
    ]
    # Add what it might be
    names_lower = " ".join(i.name.lower() for i in infos)
    if any(k in names_lower for k in {"api","server","route","controller"}):
        parts.append("Looks like a backend/API service — it handles requests and data.")
    elif any(k in names_lower for k in {"component","page","view","css","html"}):
        parts.append("Looks like a frontend/UI app — what the user sees and interacts with.")
    elif "test" in names_lower:
        parts.append("Includes tests.")
    if entry:
        parts.append(f"Start reading here: {', '.join(entry)} — these are entry points nothing else imports.")
    else:
        parts.append("No single entry point stands out — every file is imported by another (tightly coupled).")
    parts.append("Tip: read config files first, then entry points, then the files they import.")
    return " ".join(parts)


def scan_project(root: Path) -> dict:
    files = find_code_files(root)
    if not files:
        return {"root": str(root.resolve()), "file_count": 0, "files": [], "entry_points": [],
                "languages": {}, "stack": [], "calls": [], "call_count": 0,
                "project_explanation": "No code files found. Try a different folder or check IGNORED dirs.", "error": "No code files found."}
    stems = {p.stem.lower() for p in files}
    infos = [analyze_file(p, root, stems) for p in files]
    # entry points: local imports graph
    all_local_imports = set()
    for info in infos:
        all_local_imports.update(x.lower() for x in info.imports if x.lower() in stems)
    entry_points = [i.name for i in infos if i.stem.lower() not in all_local_imports and i.role in {"code","entry"}]
    # call graph (second pass): which local functions does each file call?
    # global func names from symbols + legacy func lists (base names only)
    known_funcs: set[str] = set()
    for info in infos:
        for s in info.symbols:
            n = str(s.get("name", ""))
            if n:
                known_funcs.add(n.split(".")[-1])
        for f in info.functions:
            known_funcs.add(f.split()[0].split("(")[0])
    known_funcs = {k for k in known_funcs if k and len(k) > 1}
    calls: list[dict] = []
    for info in infos:
        # call graph is for code files only — docs/config contain
        # `like_this()` inline code that would otherwise false-positive
        if info.ext not in CODE_EXTS:
            info.calls_out = []
            continue
        try:
            ftext = info.path.read_text(encoding="utf-8-sig", errors="ignore")[:30000]
        except Exception:
            ftext = ""
        # line-aware scan: definition occurrences don't count as calls,
        # but sibling calls (same file or cross-file) do
        edges = file_calls_out(ftext, info.symbols, known_funcs)
        # python per-symbol calls are precise — merge them in too
        own_defs = {str(s.get("name", "")).split(".")[-1] for s in info.symbols}
        for s in info.symbols:
            for c in s.get("calls", []) or []:
                if c in known_funcs:
                    edges.add(c)
        # drop pure self-recursion noise: a file whose only edge is its own
        # single function defining itself is not a real link (already handled
        # by file_calls_out, this is just a safety net)
        info.calls_out = sorted(edges)[:15]
        for e in info.calls_out:
            calls.append({"from_file": info.rel, "to": e})
    calls = calls[:200]
    # if too many (e.g. no imports), pick main/index/app
    if len(entry_points) > 8:
        preferred = [e for e in entry_points if any(k in e.lower() for k in {"main","index","app","server"})]
        if preferred:
            entry_points = preferred
    infos_sorted = sorted(infos, key=lambda x: x.rel.lower())
    stack = detect_stack(root, files)
    summary = project_summary(root, infos_sorted, stack)
    # build serializable
    return {
        "root": str(root.resolve()),
        "file_count": len(infos_sorted),
        "total_lines": sum(i.lines for i in infos_sorted),
        "languages": stack["languages"],
        "stack": stack["stack"],
        "project_explanation": summary,
        "entry_points": entry_points,
        "calls": calls,
        "call_count": len(calls),
        "files": [
            {
                "path": str(i.path),
                "rel": i.rel,
                "name": i.name,
                "stem": i.stem,
                "ext": i.ext,
                "language": i.language,
                "size_kb": i.size_kb,
                "lines": i.lines,
                "functions": i.functions,
                "classes": i.classes,
                "imports": i.imports,
                "exports": i.exports,
                "docstring": i.docstring,
                "explanation": i.explanation,
                "role": i.role,
                "complexity": i.complexity,
                "symbols": i.symbols,
                "calls_out": i.calls_out,
            } for i in infos_sorted
        ]
    }


def print_report(data: dict):
    # force utf-8 output on Windows cp1252 terminals
    try:
        sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    except Exception:
        pass
    def _p(s):
        try:
            print(s)
        except UnicodeEncodeError:
            print(s.encode('ascii','replace').decode('ascii'))
    _p("\n=== Code Explainer Report ===\n")
    _p(f"Root: {data['root']}")
    _p(f"Files: {data['file_count']}  Lines: {data.get('total_lines',0)}")
    if data.get("languages"):
        _p("Languages: " + ", ".join(f"{k}({v})" for k,v in data["languages"].items()))
    if data.get("stack"):
        _p("Stack: " + ", ".join(data["stack"]))
    _p("\n--- Project overview (plain English) ---")
    _p(data.get("project_explanation",""))
    _p("\n--- What each file does ---")
    for f in data["files"]:
        _p(f"\n* {f['rel']}  [{f['language']}, {f['lines']} lines, {f['complexity']}]")
        _p(f"  -> {f['explanation']}")
        for s in (f.get("symbols") or [])[:6]:
            kind = s.get("kind", "func")
            sig = s.get("signature", s.get("name", ""))
            hint = s.get("hint", "")
            _p(f"    {kind} {sig} — {hint}")
        if not f.get("symbols"):
            if f["functions"] or f["classes"]:
                if f["classes"]:
                    _p(f"    classes: {', '.join(f['classes'][:5])}")
                if f["functions"]:
                    _p(f"    functions: {', '.join(f['functions'][:5])}")
        if f["imports"]:
            _p(f"    imports: {', '.join(f['imports'][:6])}")
        if f.get("calls_out"):
            _p(f"    calls: {', '.join(f['calls_out'][:8])}")
    if data.get("calls"):
        _p(f"\n--- Call links ({data.get('call_count', len(data['calls']))}) ---")
        for c in data["calls"][:15]:
            _p(f"  {c['from_file']} calls {c['to']}")
    _p("\n--- Entry points (start here) ---")
    if data["entry_points"]:
        for ep in data["entry_points"]:
            _p(f"  {ep}")
    else:
        _p("  (none — every file is imported elsewhere)")
    _p("")


# ---------------------------------------------------------------------------
# Web UI — single HTML_PAGE
# ---------------------------------------------------------------------------
HTML_PAGE = r"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Code Explainer — Understand any codebase</title>
<style>
  :root { --bg:#0f1117; --card:#1a1d27; --card2:#1e2232; --border:#2a2e3f; --text:#e6e8f0; --muted:#9aa0b5; --accent:#6c7cff; --accent2:#22d3a5; --warn:#f5a623; --danger:#ff6b6b; --radius:14px; --radius2:10px; }
  *{box-sizing:border-box}
  body{margin:0;font-family:Inter,system-ui,Segoe UI,Roboto,Helvetica,Arial,sans-serif;background:var(--bg);color:var(--text);line-height:1.55}
  header{position:sticky;top:0;z-index:20;background:rgba(15,17,23,0.92);backdrop-filter:blur(12px);border-bottom:1px solid var(--border);padding:14px 18px}
  .wrap{max-width:1180px;margin:0 auto}
  h1{margin:0;font-size:21px;letter-spacing:-0.02em;display:flex;align-items:center;gap:10px}
  h1 .logo{width:32px;height:32px;border-radius:9px;background:linear-gradient(135deg,#6c7cff,#22d3a5);display:grid;place-items:center;font-size:14px}
  .sub{color:var(--muted);font-size:13px;margin-top:4px}
  .toolbar{display:flex;gap:8px;margin-top:14px;flex-wrap:wrap}
  .toolbar input{flex:1;min-width:260px;background:var(--card);border:1px solid var(--border);color:var(--text);padding:10px 12px;border-radius:10px;font-size:14px;outline:none}
  .toolbar input:focus{border-color:var(--accent);box-shadow:0 0 0 3px rgba(108,124,255,0.15)}
  .btn{background:var(--accent);color:white;border:0;padding:10px 16px;border-radius:10px;font-weight:650;cursor:pointer;transition:0.15s;font-size:13px;display:inline-flex;align-items:center;gap:6px}
  .btn:hover{opacity:0.92;transform:translateY(-1px)}
  .btn.secondary{background:var(--card);border:1px solid var(--border);color:var(--text)}
  .btn.ghost{background:transparent;border:1px solid var(--border);color:var(--muted)}
  .btn:disabled{opacity:0.5;cursor:not-allowed;transform:none}
  main{padding:18px;max-width:1180px;margin:0 auto}
  .stats{display:grid;grid-template-columns:repeat(4,1fr);gap:10px;margin-bottom:14px}
  @media(max-width:900px){.stats{grid-template-columns:repeat(2,1fr)}}
  .stat{background:var(--card);border:1px solid var(--border);border-radius:var(--radius);padding:12px 14px}
  .stat .k{font-size:11px;color:var(--muted);text-transform:uppercase;letter-spacing:0.07em}
  .stat .v{font-size:20px;font-weight:750;margin-top:4px;word-break:break-word}
  .stat .v.small{font-size:12px;font-weight:600;color:var(--muted)}
  .overview{background:linear-gradient(135deg,#1a1d27 0%,#1e2232 100%);border:1px solid var(--border);border-radius:var(--radius);padding:16px;margin-bottom:14px}
  .overview h2{margin:0 0 8px 0;font-size:13px;letter-spacing:0.06em;text-transform:uppercase;color:var(--accent2)}
  .overview p{margin:0;color:var(--text);font-size:14px;line-height:1.6}
  .overview .chips{margin-top:10px;display:flex;gap:6px;flex-wrap:wrap}
  .chip{font-size:11px;background:#252a40;border:1px solid var(--border);padding:4px 8px;border-radius:999px;color:var(--muted)}
  .chip.accent{color:var(--accent2);border-color:rgba(34,211,165,0.3);background:rgba(34,211,165,0.08)}
  .chip.warn{color:var(--warn);border-color:rgba(245,166,35,0.3)}
  .grid{display:grid;grid-template-columns:1.35fr 0.75fr;gap:14px}
  @media(max-width:980px){.grid{grid-template-columns:1fr}}
  .card{background:var(--card);border:1px solid var(--border);border-radius:var(--radius);overflow:hidden}
  .card h2{margin:0;padding:13px 14px;border-bottom:1px solid var(--border);font-size:12px;letter-spacing:0.06em;text-transform:uppercase;color:var(--muted);display:flex;justify-content:space-between;align-items:center;gap:8px}
  .card-body{max-height:640px;overflow:auto}
  .file{border-bottom:1px solid var(--border);padding:12px 14px;transition:0.12s}
  .file:hover{background:rgba(108,124,255,0.04)}
  .file:last-child{border:0}
  .file-head{display:flex;justify-content:space-between;gap:10px;align-items:flex-start;cursor:pointer}
  .file-title{font-family:ui-monospace,Menlo,Consolas,monospace;font-size:12.5px;word-break:break-all;display:flex;gap:8px;align-items:center}
  .file-title .icon{width:26px;height:26px;border-radius:7px;display:grid;place-items:center;font-size:12px;flex-shrink:0;border:1px solid var(--border);background:#12141e}
  .explain{margin-top:8px;background:#12141e;border:1px solid var(--border);border-radius:9px;padding:10px 11px;font-size:13px;color:var(--text);line-height:1.5}
  .explain b{color:var(--accent2)}
  .meta{margin-top:8px;display:flex;gap:6px;flex-wrap:wrap;font-size:11px;color:var(--muted);align-items:center}
  .badge{font-size:10.5px;background:#252a40;border:1px solid var(--border);padding:2px 7px;border-radius:999px;white-space:nowrap}
  .badge.fn{color:var(--accent2);border-color:rgba(34,211,165,0.28)}
  .badge.cl{color:#f472b6;border-color:rgba(244,114,182,0.28)}
  .badge.lang{color:#7dd3fc;border-color:rgba(125,211,252,0.28)}
  .badge.complex-simple{color:var(--accent2)}
  .badge.complex-medium{color:var(--warn)}
  .badge.complex-complex{color:var(--danger)}
  .detail{margin-top:8px;display:grid;gap:6px}
  .detail code{font-size:11px;background:#12141e;border:1px solid var(--border);padding:3px 7px;border-radius:6px;display:inline-block;margin:2px 4px 2px 0}
  .detail .label{font-size:10px;text-transform:uppercase;letter-spacing:0.06em;color:var(--muted);margin-top:6px}
  .empty{padding:28px;text-align:center;color:var(--muted);font-size:13px}
  .side-stack{display:grid;gap:14px}
  .search{width:100%;background:#12141e;border:0;border-bottom:1px solid var(--border);color:var(--text);padding:10px 14px;font-size:13px;outline:none}
  .search:focus{border-color:var(--accent)}
  .import-row{display:flex;justify-content:space-between;align-items:center;padding:8px 14px;border-bottom:1px solid var(--border);font-size:12px;gap:8px}
  .import-row code{font-size:12px}
  .entry{padding:9px 14px;border-bottom:1px solid var(--border);font-family:ui-monospace,monospace;font-size:12px;display:flex;align-items:center;gap:8px}
  .dot{width:8px;height:8px;border-radius:50%;background:var(--accent2);flex-shrink:0}
  .lang-row{display:flex;justify-content:space-between;align-items:center;padding:7px 14px;border-bottom:1px solid var(--border);font-size:12px}
  .bar{height:6px;background:#12141e;border-radius:999px;overflow:hidden;margin-top:4px}
  .bar > i{display:block;height:100%;background:linear-gradient(90deg,#6c7cff,#22d3a5)}
  #status{margin-top:10px;font-size:13px;color:var(--muted);min-height:18px}
  .error{color:var(--danger)!important}
  .ok{color:var(--accent2)!important}
  .overlay{position:fixed;inset:0;background:rgba(0,0,0,0.6);backdrop-filter:blur(4px);display:none;align-items:center;justify-content:center;z-index:50;padding:18px}
  .modal{background:var(--card);border:1px solid var(--border);border-radius:16px;width:100%;max-width:640px;max-height:80vh;display:flex;flex-direction:column;overflow:hidden;box-shadow:0 20px 60px rgba(0,0,0,0.5)}
  .modal-head{padding:14px;border-bottom:1px solid var(--border);display:flex;justify-content:space-between;align-items:center;gap:12px}
  .crumb{font-family:ui-monospace,monospace;font-size:12px;color:var(--muted);word-break:break-all;padding:8px 14px;background:#12141e;border-bottom:1px solid var(--border)}
  .dir-list{overflow:auto;flex:1;padding:6px}
  .dir-item{display:flex;align-items:center;gap:10px;padding:9px 10px;border-radius:8px;cursor:pointer;font-size:13px}
  .dir-item:hover{background:#252a40}
  .modal-foot{padding:12px 14px;border-top:1px solid var(--border);display:flex;gap:10px;justify-content:flex-end}
  .pill{font-size:11px;background:#12141e;border:1px solid var(--border);padding:4px 8px;border-radius:999px;color:var(--muted)}
  .actions{display:flex;gap:6px;flex-wrap:wrap;margin-top:10px}
  pre{margin:0;background:#12141e;border:1px solid var(--border);border-radius:8px;padding:10px;overflow:auto;font-size:11.5px;line-height:1.5;max-height:280px}
</style>
</head>
<body>
<header>
  <div class="wrap">
    <h1><span class="logo">≋</span> Code Explainer <span style="font-weight:500;color:var(--muted);font-size:13px">— plain-English codebase guide</span></h1>
    <div class="sub">Drop a folder path — get what each file does, tech stack, and where to start reading. No install, no API key. <b style="color:var(--accent2)">100% local</b> — the server runs on your machine (127.0.0.1) and your code never leaves it.</div>
    <div class="toolbar">
      <input id="pathInput" placeholder="Path to project — e.g. . or C:\Users\...\MyProject" value="." />
      <button class="btn secondary" onclick="openPicker()" title="Browse folders in the page">📁 Browse</button>
      <button class="btn secondary" onclick="pickNative()" title="Native Windows folder dialog (needs desktop)">🪟 Windows…</button>
      <button class="btn" onclick="doScan()">🔍 Explain</button>
      <button class="btn secondary" onclick="doScan(true)" title="Rescan current folder">↻ Rescan</button>
      <button class="btn ghost" onclick="downloadMD()" title="Download Markdown report">⬇ Markdown</button>
      <button class="btn ghost" onclick="downloadJSON()" title="Download JSON">⬇ JSON</button>
    </div>
    <div id="status"></div>
  </div>
</header>

<div id="pickerOverlay" class="overlay" onclick="if(event.target===this) closePicker()">
  <div class="modal">
    <div class="modal-head">
      <h3 style="margin:0;font-size:14px">Choose folder</h3>
      <button class="btn secondary" style="padding:6px 12px;font-size:12px" onclick="closePicker()">✕ Close</button>
    </div>
    <div id="crumb" class="crumb">—</div>
    <div style="padding:8px 14px;display:flex;gap:8px;border-bottom:1px solid var(--border)">
      <input id="browsePath" style="flex:1;background:#12141e;border:1px solid var(--border);color:var(--text);padding:8px 10px;border-radius:6px;font-size:12px;font-family:ui-monospace,monospace" onkeydown="if(event.key==='Enter') loadBrowse(this.value)" />
      <button class="btn secondary" style="padding:8px 12px" onclick="loadBrowse(document.getElementById('browsePath').value)">Go</button>
    </div>
    <div id="browseList" class="dir-list"><div class="empty">Loading…</div></div>
    <div class="modal-foot">
      <span id="pickerStatus" class="pill" style="margin-right:auto">—</span>
      <button class="btn secondary" onclick="closePicker()">Cancel</button>
      <button class="btn" onclick="pickCurrentFolder()">Select this folder</button>
    </div>
  </div>
</div>

<!-- In-depth explanation modal -->
<div id="deepOverlay" class="overlay" onclick="if(event.target===this) closeDeep()">
  <div class="modal" style="max-width:720px">
    <div class="modal-head">
      <h3 id="deepTitle" style="margin:0;font-size:14px">🔍 Deep dive</h3>
      <button class="btn secondary" style="padding:6px 12px;font-size:12px" onclick="closeDeep()">✕ Close</button>
    </div>
    <div id="deepBody" class="dir-list" style="padding:14px 16px"><div class="empty">—</div></div>
    <div class="modal-foot">
      <span class="pill" style="margin-right:auto">100% local — analyzed on your machine</span>
      <button class="btn secondary" onclick="closeDeep()">Close</button>
    </div>
  </div>
</div>

<main>
  <div class="stats">
    <div class="stat"><div class="k">Files found</div><div class="v" id="statFiles">—</div><div class="v small" id="statLines">—</div></div>
    <div class="stat"><div class="k">Languages</div><div class="v small" id="statLangs">—</div></div>
    <div class="stat"><div class="k">Entry points</div><div class="v" id="statEntry">—</div><div class="v small">start here →</div></div>
    <div class="stat"><div class="k">Root</div><div class="v small" id="statRoot" style="word-break:break-all">—</div></div>
  </div>

  <div class="overview" id="overview" style="display:none">
    <h2>📖 Project overview — in simple terms</h2>
    <p id="overviewText">—</p>
    <div class="chips" id="chips"></div>
    <div class="actions">
      <button class="btn ghost" style="font-size:12px" onclick="copyOverview()">Copy overview</button>
      <button class="btn ghost" style="font-size:12px" onclick="toggleHowTo()">How to read this codebase?</button>
    </div>
    <div id="howto" style="display:none;margin-top:12px;background:#12141e;border:1px solid var(--border);border-radius:9px;padding:10px;font-size:13px;color:var(--muted);line-height:1.6">
      <b style="color:var(--text)">Suggested order:</b> 1) Read config files (package.json / requirements.txt) → 2) Open <b>entry points</b> (main, index, app) → 3) Follow their imports to understand the flow → 4) Check <code>utils/helpers</code> last (they're helpers, not core flow). Use the search box to filter by keyword.
    </div>
  </div>

  <div class="grid">
    <div class="card">
      <h2><span>📂 Files — what each does</span> <span class="pill" id="fileCountPill">—</span></h2>
      <input class="search" id="filter" placeholder="Filter by filename, language, or what it does... (e.g. auth, api, test)" oninput="renderFiles()" />
      <div style="padding:8px 10px;display:flex;gap:6px;flex-wrap:wrap;border-bottom:1px solid var(--border);background:#12141e">
        <button class="btn ghost" style="padding:5px 9px;font-size:11px" onclick="setFilter('')">All</button>
        <button class="btn ghost" style="padding:5px 9px;font-size:11px" onclick="setFilter('entry')">Entry</button>
        <button class="btn ghost" style="padding:5px 9px;font-size:11px" onclick="setFilter('config')">Config</button>
        <button class="btn ghost" style="padding:5px 9px;font-size:11px" onclick="setFilter('test')">Tests</button>
        <button class="btn ghost" style="padding:5px 9px;font-size:11px" onclick="setFilter('.py')">Python</button>
        <button class="btn ghost" style="padding:5px 9px;font-size:11px" onclick="setFilter('.js')">JS/TS</button>
      </div>
      <div class="card-body" id="filesBody"><div class="empty">Click <b>Explain</b> to scan a folder</div></div>
    </div>
    <div class="side-stack">
      <div class="card">
        <h2>🧱 Languages</h2>
        <div class="card-body" id="langsBody"><div class="empty">No data yet</div></div>
      </div>
      <div class="card">
        <h2>🔗 How files connect</h2>
        <div class="card-body" id="importsBody"><div class="empty">No local imports yet</div></div>
      </div>
      <div class="card">
        <h2>📞 Who calls whom</h2>
        <div class="card-body" id="callsBody"><div class="empty">No call links yet</div></div>
      </div>
      <div class="card">
        <h2>🚀 Where to start reading</h2>
        <div class="card-body" id="entryBody"><div class="empty">Run a scan first</div></div>
      </div>
      <div class="card" id="previewCard" style="display:none">
        <h2>👁 File preview <button class="btn ghost" style="padding:4px 8px;font-size:11px" onclick="closePreview()">✕</button></h2>
        <div style="padding:12px"><div id="previewMeta" class="pill" style="margin-bottom:8px;display:inline-block"></div><pre id="previewPre">—</pre></div>
      </div>
    </div>
  </div>
</main>
<script>
let lastData = null;
let currentBrowsePath = ".";

function escapeHtml(s){ return String(s).replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c])); }

async function doScan(useDot=false){
  const path = useDot ? "." : (document.getElementById('pathInput').value.trim() || ".");
  const status = document.getElementById('status');
  if(window.location.protocol === 'file:'){
    status.textContent = 'Open via http://127.0.0.1:PORT — not file://. Run: python code_explainer.py --web';
    status.className='error'; return;
  }
  status.textContent = "Explaining "+path+" ..."; status.className='';
  const url = window.location.origin + '/api/scan?path=' + encodeURIComponent(path);
  try{
    const res = await fetch(url);
    const text = await res.text();
    let data; try{ data = JSON.parse(text);} catch{ throw new Error('Server returned non-JSON: '+text.slice(0,300));}
    if(!res.ok) throw new Error(data.error || 'Scan failed');
    lastData = data;
    renderAll(data);
    status.textContent = "Explained "+data.file_count+" files from "+data.root+" ("+data.total_lines+" lines)";
    status.className='ok';
  }catch(e){
    let msg = e.message||String(e);
    if(msg.includes('Failed to fetch') || msg.includes('NetworkError') || msg.includes('Load failed')){
      status.innerHTML = `Cannot reach the server at <b>${escapeHtml(url)}</b>.<br>`
        + `1) Is the black terminal with <b>python code_explainer.py --web</b> still open? If not, double-click <b>run.bat</b> again.<br>`
        + `2) Are you on <b>${escapeHtml(window.location.origin)}</b> (not a file:// tab, not a different port)?<br>`
        + `3) Did the server start on another port? Check the terminal — it prints the real URL if 8000 was busy.<br>`
        + `<button class="btn ghost" style="padding:4px 10px;font-size:11px;margin-top:6px" onclick="doScan()">↻ Retry</button>`;
      status.className='error';
      return;
    }
    status.textContent = msg; status.className='error';
  }
}

function renderAll(data){
  document.getElementById('statFiles').textContent = data.file_count;
  document.getElementById('statLines').textContent = data.total_lines + " lines";
  document.getElementById('statEntry').textContent = data.entry_points.length;
  document.getElementById('statRoot').textContent = data.root;
  document.getElementById('fileCountPill').textContent = data.file_count + " files";
  // langs
  const langs = data.languages || {};
  const total = Object.values(langs).reduce((a,b)=>a+b,0) || 1;
  document.getElementById('statLangs').textContent = Object.keys(langs).slice(0,3).join(", ") || "—";
  const ov = document.getElementById('overview');
  ov.style.display='block';
  document.getElementById('overviewText').textContent = data.project_explanation || "—";
  const chips = document.getElementById('chips');
  chips.innerHTML = (data.stack||[]).map(s=>`<span class="chip accent">${escapeHtml(s)}</span>`).join('') +
    Object.entries(langs).slice(0,6).map(([k,v])=>`<span class="chip">${escapeHtml(k)}: ${v}</span>`).join('') +
    (data.entry_points.length? `<span class="chip warn">Entry: ${escapeHtml(data.entry_points.slice(0,2).join(", "))}</span>` : "");
  renderFiles();
  renderLangs(data);
  renderImports(data);
  renderCalls(data);
  renderEntries(data);
}

function langIcon(lang, ext){
  const m = {Python:"🐍",JavaScript:"🟨",TypeScript:"🔷",Java:"☕",Go:"🐹",PHP:"🐘",Ruby:"💎",Rust:"🦀","C#":"🔷","C++":"⚙️",C:"⚙️",Kotlin:"🟣",Swift:"🍎",Dart:"🎯",HTML:"🌐",CSS:"🎨",JSON:"📦",YAML:"⚙️",Markdown:"📝",Config:"⚙️"};
  if(m[lang]) return m[lang];
  if(ext===".py") return "🐍";
  if(ext===".js"||ext===".ts"||ext===".tsx") return "🟦";
  if(ext===".json") return "📦";
  if(ext===".md") return "📝";
  return "📄";
}

function setFilter(v){ document.getElementById('filter').value=v; renderFiles(); }
function toggleHowTo(){ const el=document.getElementById('howto'); el.style.display = el.style.display==='none'?'block':'none'; }
function copyOverview(){
  const t=document.getElementById('overviewText').textContent;
  navigator.clipboard.writeText(t).then(()=>{ const s=document.getElementById('status'); s.textContent='Copied overview'; s.className='ok'; setTimeout(()=>s.textContent='',1500); });
}

function renderFiles(){
  const body=document.getElementById('filesBody');
  if(!lastData || !lastData.files.length){ body.innerHTML='<div class="empty">No files found</div>'; return; }
  const q=(document.getElementById('filter').value||'').toLowerCase();
  let files=lastData.files;
  if(q){
    files=files.filter(f=>{
      const symText = (f.symbols||[]).map(s=>(s.name||'')+' '+(s.hint||'')+' '+(s.signature||'')).join(' ');
      return f.rel.toLowerCase().includes(q) || f.language.toLowerCase().includes(q) || f.explanation.toLowerCase().includes(q) || f.role.toLowerCase().includes(q) || f.functions.join(' ').toLowerCase().includes(q) || f.classes.join(' ').toLowerCase().includes(q) || f.ext.toLowerCase().includes(q) || symText.toLowerCase().includes(q) || (f.calls_out||[]).join(' ').toLowerCase().includes(q);
    });
  }
  if(!files.length){ body.innerHTML='<div class="empty">No matches for "'+escapeHtml(q)+'"</div>'; return; }
  body.innerHTML = files.map(f=>{
    const syms = (f.symbols||[]).slice(0,8);
    const fRelQ = escapeHtml(f.rel).replace(/'/g,"\\'");
    const symHtml = syms.length ? `<div class="label">What each function does — click 🔍 for a deep dive</div>` + syms.map(s=>{ const sNameQ = escapeHtml(s.name||'').replace(/'/g,"\\'"); return `<div style="font-size:12px;margin:3px 0;display:flex;gap:6px;align-items:baseline"><button class="btn ghost" style="padding:2px 7px;font-size:11px;flex-shrink:0" title="In-depth explanation" onclick="event.stopPropagation();deepdive('${fRelQ}','${sNameQ}')">🔍</button><span><code>${escapeHtml(s.signature||s.name)}</code> <span style="color:var(--text)">— ${escapeHtml(s.hint||'')}</span>${s.line?` <span style="color:var(--muted)">(line ${s.line})</span>`:''}</span></div>`; }).join('') : '';
    const callsHtml = (f.calls_out && f.calls_out.length) ? `<div class="label">Calls</div><div>${f.calls_out.slice(0,8).map(c=>`<code>${escapeHtml(c)}</code>`).join('')}</div>` : '';
    return `
    <div class="file">
      <div class="file-head" onclick="toggleDetail(this)">
        <div class="file-title">
          <span class="icon">${langIcon(f.language,f.ext)}</span>
          <span>
            <span style="color:var(--text);font-weight:600">${escapeHtml(f.rel)}</span>
            <span style="color:var(--muted);font-size:11px"> · ${escapeHtml(f.language)} · ${f.lines} lines · ${f.size_kb} KB</span>
          </span>
        </div>
        <span style="display:flex;gap:4px;flex-shrink:0;flex-wrap:wrap;justify-content:flex-end">
          <span class="badge lang">${escapeHtml(f.language)}</span>
          ${f.classes.length? `<span class="badge cl">${f.classes.length} class</span>`:''}
          ${f.functions.length? `<span class="badge fn">${f.functions.length} fn</span>`:''}
          <span class="badge complex-${f.complexity}">${f.complexity}</span>
        </span>
      </div>
      <div class="explain">💡 ${escapeHtml(f.explanation)}</div>
      <div class="detail" style="display:none">
        ${f.docstring? `<div class="label">💬 Note</div><div style="font-size:12px;color:var(--muted)">"${escapeHtml(f.docstring)}"</div>`:''}
        ${symHtml}
        ${!syms.length && f.classes.length? `<div class="label">Classes</div><div>${f.classes.map(c=>`<code>${escapeHtml(c)}</code>`).join('')}</div>`:''}
        ${!syms.length && f.functions.length? `<div class="label">Functions</div><div>${f.functions.map(fn=>`<code>${escapeHtml(fn)}</code>`).join('')}</div>`:''}
        ${f.imports.length? `<div class="label">Imports</div><div>${f.imports.map(i=>`<code>${escapeHtml(i)}</code>`).join('')}</div>`:''}
        ${callsHtml}
        ${f.exports.length? `<div class="label">Exports</div><div>${f.exports.map(e=>`<code>${escapeHtml(e)}</code>`).join('')}</div>`:''}
        <div style="margin-top:8px;display:flex;gap:6px">
          <button class="btn ghost" style="padding:5px 9px;font-size:11px" onclick="previewFile('${escapeHtml(f.rel).replace(/'/g,"\\'")}')">👁 Preview</button>
          <span class="pill">Role: ${escapeHtml(f.role)}</span>
        </div>
      </div>
    </div>`;
  }).join('');
}

function toggleDetail(head){
  const d=head.nextElementSibling.nextElementSibling;
  d.style.display = d.style.display==='none' ? 'grid' : 'none';
}

function renderLangs(data){
  const body=document.getElementById('langsBody');
  const langs=data.languages||{};
  const total=Object.values(langs).reduce((a,b)=>a+b,0)||1;
  if(!Object.keys(langs).length){ body.innerHTML='<div class="empty">No data</div>'; return; }
  body.innerHTML = Object.entries(langs).map(([lang,count])=>{
    const pct=Math.round(count/total*100);
    return `<div class="lang-row"><span>${escapeHtml(lang)}</span><span style="color:var(--muted)">${count} files · ${pct}%</span></div><div style="padding:0 14px 8px 14px"><div class="bar"><i style="width:${pct}%"></i></div></div>`;
  }).join('');
}

function renderImports(data){
  const body=document.getElementById('importsBody');
  const withImports=data.files.filter(f=>f.imports.length);
  if(!withImports.length){ body.innerHTML='<div class="empty">No local imports — files are standalone</div>'; return; }
  body.innerHTML = withImports.slice(0,22).map(f=>`
    <div class="import-row"><code>${escapeHtml(f.name)}</code> <span style="color:var(--muted)">→</span> <span style="text-align:right">${f.imports.slice(0,4).map(i=>`<code>${escapeHtml(i)}</code>`).join(', ')}${f.imports.length>4? ' +'+(f.imports.length-4):''}</span></div>
  `).join('') + (withImports.length>22? `<div class="empty" style="padding:10px">+${withImports.length-22} more</div>`:'');
}

function renderCalls(data){
  const body=document.getElementById('callsBody');
  const calls=data.calls||[];
  if(!calls.length){ body.innerHTML='<div class="empty">No cross-function calls detected — files stand alone</div>'; return; }
  body.innerHTML = calls.slice(0,20).map(c=>`
    <div class="import-row"><code>${escapeHtml(c.from_file)}</code> <span style="color:var(--muted)">calls</span> <code>${escapeHtml(c.to)}</code></div>
  `).join('') + (calls.length>20? `<div class="empty" style="padding:10px">+${calls.length-20} more</div>`:'');
}

function renderEntries(data){
  const body=document.getElementById('entryBody');
  if(!data.entry_points.length){ body.innerHTML='<div class="empty">Every file is imported elsewhere — no clear entry</div>'; return; }
  body.innerHTML = data.entry_points.map(e=>`<div class="entry"><span class="dot"></span>${escapeHtml(e)} <span style="margin-left:auto;color:var(--muted);font-size:11px">start here</span></div>`).join('');
}

// Browse
async function openPicker(){ document.getElementById('pickerOverlay').style.display='flex'; const cur=document.getElementById('pathInput').value.trim()||"."; document.getElementById('browsePath').value=cur; await loadBrowse(cur); }
function closePicker(){ document.getElementById('pickerOverlay').style.display='none'; }
async function loadBrowse(path){
  const list=document.getElementById('browseList'), crumb=document.getElementById('crumb'), status=document.getElementById('pickerStatus');
  list.innerHTML='<div class="empty">Loading…</div>';
  try{
    const res=await fetch(window.location.origin+'/api/browse?path='+encodeURIComponent(path||"."));
    const data=await res.json(); if(!res.ok) throw new Error(data.error||'Browse failed');
    currentBrowsePath=data.current; document.getElementById('browsePath').value=data.current; crumb.textContent=data.current; status.textContent=data.directories.length+' folders'+(data.py_count!=null?' • '+data.py_count+' code files':'');
    renderBrowse(data);
  }catch(e){ list.innerHTML='<div class="empty" style="color:var(--danger)">'+escapeHtml(e.message)+'</div>'; }
}
function browseItem(fullPath, label, icon){
  // NOTE: path goes in a data-attribute, NOT inline in onclick.
  // Windows backslashes (C:\..., trailing C:\) break inside JS string
  // literals (\U collapses, \' terminates early) — dataset passes them
  // through untouched. Forward slashes are used for joining; the Python
  // server accepts them on Windows.
  return `<div class="dir-item" data-path="${escapeHtml(fullPath)}" onclick="loadBrowse(this.dataset.path)"><span class="icon">${icon}</span> <span>${label}</span></div>`;
}
function joinBrowsePath(current, name){
  const base = current.replace(/\\/g,'/').replace(/\/+$/,'');
  return base + '/' + name;
}
function renderBrowse(data){
  const list=document.getElementById('browseList'); const items=[];
  if(data.parent) items.push(browseItem(data.parent, '.. (parent)', '⬆️'));
  if(data.drives && data.drives.length){ data.drives.forEach(d=> items.push(browseItem(d, d, '💾'))); if(items.length) items.push('<div style="height:1px;background:var(--border);margin:6px 0"></div>'); }
  if(!data.directories.length) items.push('<div class="empty">No subfolders</div>'); else data.directories.forEach(name=>{ items.push(browseItem(joinBrowsePath(data.current, name), name, '📁')); });
  list.innerHTML=items.join('');
}
function pickCurrentFolder(){ document.getElementById('pathInput').value=currentBrowsePath; closePicker(); doScan(); }

async function pickNative(){
  // Native Windows folder popup, opened by the local server (tkinter, stdlib).
  // The request stays open until you pick a folder or cancel.
  const cur=document.getElementById('pathInput').value.trim()||".";
  const status=document.getElementById('status');
  if(window.location.protocol==='file:'){
    status.textContent='Open via http://127.0.0.1:PORT — not file://. Run: python code_explainer.py --web';
    status.className='error'; return;
  }
  status.textContent='Waiting for the Windows folder window… (check your taskbar if you don\u2019t see it)';
  status.className='';
  try{
    const res=await fetch(window.location.origin+'/api/pick?path='+encodeURIComponent(cur));
    const data=await res.json();
    if(!res.ok){
      if(res.status===501){ status.textContent='Native dialog unavailable — using Browse instead.'; openPicker(); return; }
      throw new Error(data.error||'Picker failed');
    }
    if(data.cancelled){ status.textContent='Folder pick cancelled — nothing changed.'; return; }
    document.getElementById('pathInput').value=data.path;
    doScan();
  }catch(e){
    let msg=e.message||String(e);
    if(msg.includes('Failed to fetch')) msg='Lost connection to the local server — is the terminal with "python code_explainer.py --web" still open?';
    status.textContent=msg; status.className='error';
  }
}

// Preview
async function previewFile(rel){
  if(!lastData) return;
  const card=document.getElementById('previewCard');
  const meta=document.getElementById('previewMeta');
  const pre=document.getElementById('previewPre');
  card.style.display='block';
  meta.textContent=rel + " — loading...";
  pre.textContent="Loading...";
  try{
    const url=window.location.origin+'/api/file?path='+encodeURIComponent(lastData.root+'/'+rel);
    const res=await fetch(url); const data=await res.json();
    if(!res.ok) throw new Error(data.error||'Failed');
    meta.textContent = rel + " · " + data.lines + " lines · " + data.language;
    pre.textContent = data.preview || "(empty)";
    card.scrollIntoView({behavior:'smooth'});
  }catch(e){ pre.textContent="Error: "+e.message; }
}
function closePreview(){ document.getElementById('previewCard').style.display='none'; }

// In-depth explanation modal
function closeDeep(){ document.getElementById('deepOverlay').style.display='none'; }
async function deepdive(rel, name){
  const ov=document.getElementById('deepOverlay'), body=document.getElementById('deepBody'), title=document.getElementById('deepTitle');
  ov.style.display='flex';
  title.textContent='🔍 '+name+' — analyzing…';
  body.innerHTML='<div class="empty">Reading the code…</div>';
  try{
    const url=window.location.origin+'/api/deepdive?path='+encodeURIComponent(lastData.root+'/'+rel)+'&symbol='+encodeURIComponent(name)+'&root='+encodeURIComponent(lastData.root);
    const res=await fetch(url); const d=await res.json();
    if(!res.ok) throw new Error(d.error||'Deep dive failed');
    title.textContent='🔍 '+d.qualified+'  ·  line '+d.line+'  ·  '+d.level;
    const sec=(t,inner)=> inner? `<div class="label" style="margin-top:10px">${t}</div><div style="font-size:13px">${inner}</div>` : '';
    body.innerHTML =
      `<div style="font-size:13px;color:var(--muted)"><code>${escapeHtml(d.signature||'')}</code> · ${escapeHtml(d.kind||'')} · ~${d.span_lines} lines · complexity ${d.complexity}</div>`
      + `<div style="font-size:14px;margin-top:8px">💡 ${escapeHtml(d.purpose||'')}</div>`
      + sec('Parameters', (d.params||[]).length ? d.params.map(p=>`<div style="margin:3px 0"><code>${escapeHtml(p.name)}</code> <span style="color:var(--muted)">('${escapeHtml(p.human)}')</span> — ${p.required?'required':'optional'+(p.default?', default '+escapeHtml(p.default):'')}</div>`).join('') : '<span style="color:var(--muted)">none</span>')
      + sec('How it works, step by step', (d.steps||[]).length ? '<ol style="margin:6px 0;padding-left:20px">'+d.steps.map(s=>`<li style="margin:3px 0">${escapeHtml(s)}</li>`).join('')+'</ol>'+(d.steps_total>d.steps.length?`<div style="color:var(--muted);font-size:12px">+${d.steps_total-d.steps.length} more steps inside</div>`:'') : '<span style="color:var(--muted)">Body is tiny — nothing to break down.</span>')
      + sec('Notes from inside the code', (d.notes||[]).map(n=>`<div style="color:var(--muted)">"${escapeHtml(n)}"</div>`).join(''))
      + sec('Returns', (d.returns||[]).map(r=>`<code>${escapeHtml(r)}</code>`).join(' '))
      + sec('Can raise', (d.raises||[]).map(r=>`<code>${escapeHtml(r)}</code>`).join(' '))
      + sec('Calls', (d.calls||[]).map(c=>`<code>${escapeHtml(c)}</code>`).join(' '))
      + sec('Called by (other files)', (d.called_by||[]).map(c=>`<code>${escapeHtml(c)}</code>`).join(' '));
  }catch(e){ title.textContent='🔍 '+name; body.innerHTML='<div class="empty" style="color:var(--danger)">'+escapeHtml(e.message||String(e))+'</div>'; }
}

// Exports
function downloadJSON(){
  if(!lastData){ alert('Scan first'); return; }
  const blob=new Blob([JSON.stringify(lastData,null,2)],{type:'application/json'});
  const a=document.createElement('a'); a.href=URL.createObjectURL(blob); a.download='code-explainer.json'; a.click();
}
function downloadMD(){
  if(!lastData){ alert('Scan first'); return; }
  let md = `# Code Explainer — ${lastData.root}\n\n`;
  md += `**${lastData.file_count} files, ${lastData.total_lines} lines**\n\n`;
  if(lastData.stack && lastData.stack.length) md += `**Stack:** ${lastData.stack.join(", ")}\n\n`;
  md += `## Project overview\n\n${lastData.project_explanation}\n\n`;
  md += `## Entry points (start here)\n\n` + (lastData.entry_points.length? lastData.entry_points.map(e=>`- ${e}`).join("\n") : "_No clear entry — all files imported elsewhere._") + "\n\n";
  md += `## Languages\n\n` + Object.entries(lastData.languages||{}).map(([k,v])=>`- ${k}: ${v} files`).join("\n") + "\n\n";
  md += `## What each file does\n\n`;
  if(lastData.calls && lastData.calls.length){
    md += `## Call links\n\n` + lastData.calls.slice(0,30).map(c=>`- ${c.from_file} calls \`${c.to}\``).join("\n") + "\n\n";
  }
  lastData.files.forEach(f=>{
    md += `### ${f.rel} — ${f.language} (${f.lines} lines)\n\n`;
    md += `> ${f.explanation}\n\n`;
    if(f.symbols && f.symbols.length){
      md += f.symbols.slice(0,10).map(s=>`- \`${s.signature||s.name}\` — ${s.hint||''}`).join("\n") + "\n\n";
    } else {
      if(f.functions.length) md += `**Functions:** ${f.functions.join(", ")}\n\n`;
      if(f.classes.length) md += `**Classes:** ${f.classes.join(", ")}\n\n`;
    }
    if(f.imports.length) md += `**Imports:** ${f.imports.join(", ")}\n\n`;
    if(f.calls_out && f.calls_out.length) md += `**Calls:** ${f.calls_out.join(", ")}\n\n`;
  });
  const blob=new Blob([md],{type:'text/markdown'});
  const a=document.createElement('a'); a.href=URL.createObjectURL(blob); a.download='CODE_EXPLAINED.md'; a.click();
}

window.addEventListener('DOMContentLoaded', ()=> doScan());
</script>
</body>
</html>
"""

# ---------------------------------------------------------------------------
# HTTP handler
# ---------------------------------------------------------------------------

class ExplainerHandler(BaseHTTPRequestHandler):
    def _cors(self):
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")

    def do_OPTIONS(self):
        self.send_response(204); self._cors(); self.end_headers()

    def do_GET(self):
        parsed = urllib.parse.urlparse(self.path)
        if parsed.path in ("/", "/index.html"):
            body = HTML_PAGE.encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type","text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self._cors(); self.end_headers()
            self.wfile.write(body)
        elif parsed.path == "/api/scan":
            qs = urllib.parse.parse_qs(parsed.query)
            raw = qs.get("path",["."])[0]
            root = Path(raw) if raw else Path(".")
            if not root.is_absolute():
                root = (Path.cwd() / root).resolve()
            if not root.exists():
                self._json({"error": f"Path not found: {raw}"}, 404); return
            if root.is_file():
                root = root.parent
            try:
                data = scan_project(root)
                self._json(data)
            except Exception as e:
                import traceback; traceback.print_exc()
                self._json({"error": str(e)}, 500)
        elif parsed.path == "/api/browse":
            qs = urllib.parse.parse_qs(parsed.query)
            raw = qs.get("path",["."])[0] or "."
            p = Path(raw) if raw else Path(".")
            if not p.is_absolute():
                p = (Path.cwd() / p).resolve()
            else:
                try: p = p.resolve()
                except: pass
            if not p.exists():
                self._json({"error": f"Path not found: {raw}"}, 404); return
            if p.is_file():
                p = p.parent
            try:
                dirs=[]; count=0
                for entry in p.iterdir():
                    if entry.is_dir(): dirs.append(entry.name)
                    elif entry.is_file() and entry.suffix.lower() in EXT_LANG or entry.name in CONFIG_FILES:
                        count+=1
                dirs.sort(key=lambda s: s.lower())
                parent = str(p.parent) if str(p.resolve()) != str(p.parent.resolve()) else None
                drives=[]
                if os.name=="nt":
                    import string
                    for ch in string.ascii_uppercase:
                        d=f"{ch}:\\"
                        if Path(d).exists(): drives.append(d)
                self._json({"current": str(p), "parent": parent, "separator": os.sep, "directories": dirs, "py_count": count, "drives": drives})
            except Exception as e:
                import traceback; traceback.print_exc()
                self._json({"error": str(e)}, 500)
        elif parsed.path == "/api/pick":
            # Native Windows folder dialog via stdlib tkinter (still 100% local).
            # Blocks this request until the user picks a folder or cancels.
            # (Single-threaded server: other clicks simply wait their turn.)
            qs = urllib.parse.parse_qs(parsed.query)
            raw = qs.get("path",["."])[0] or "."
            try:
                import tkinter
                from tkinter import filedialog
            except Exception:
                self._json({"error": "Native dialog unavailable (tkinter missing in this Python). Use Browse instead."}, 501)
                return
            start = Path(raw)
            if not start.is_absolute():
                start = (Path.cwd() / start)
            initial = str(start if start.is_dir() else start.parent)
            print(f"[web] Opening native folder dialog (from {initial}) ...")
            try:
                root = tkinter.Tk()
                root.withdraw()
                try:
                    root.attributes("-topmost", True)
                except Exception:
                    pass
                try:
                    root.lift()
                    root.focus_force()
                except Exception:
                    pass
                try:
                    chosen = filedialog.askdirectory(title="Choose a codebase folder", initialdir=initial, mustexist=True)
                finally:
                    try:
                        root.destroy()
                    except Exception:
                        pass
            except Exception as e:
                import traceback
                traceback.print_exc()
                self._json({"error": f"Folder dialog failed: {e}"}, 500)
                return
            if not chosen:
                print("[web] Folder dialog cancelled.")
                self._json({"cancelled": True})
                return
            print(f"[web] Folder dialog chose: {chosen}")
            self._json({"path": chosen})
        elif parsed.path == "/api/file":
            qs = urllib.parse.parse_qs(parsed.query)
            raw = qs.get("path",[""])[0]
            if not raw:
                self._json({"error":"Missing path"},400); return
            p = Path(raw)
            if not p.exists() or not p.is_file():
                self._json({"error": f"File not found: {raw}"},404); return
            try:
                text = p.read_text(encoding="utf-8", errors="ignore")
                preview = "\n".join(text.splitlines()[:180])[:8000]
                ext = p.suffix.lower()
                lang = EXT_LANG.get(ext,"Text")
                self._json({"path": str(p), "language": lang, "lines": text.count("\n")+1, "size_kb": round(p.stat().st_size/1024,1), "preview": preview})
            except Exception as e:
                self._json({"error": str(e)},500)
        elif parsed.path == "/api/deepdive":
            qs = urllib.parse.parse_qs(parsed.query)
            raw = qs.get("path", [""])[0]
            symbol = qs.get("symbol", [""])[0]
            root_raw = qs.get("root", [""])[0]
            if not raw or not symbol:
                self._json({"error": "Need ?path=<file>&symbol=<name> (and optional &root=<project>)."}, 400)
                return
            p = Path(raw)
            root = Path(root_raw) if root_raw else (p.parent if p.is_file() else p)
            try:
                detail = deepdive_symbol(p, symbol, root if root.is_dir() else None)
            except Exception as e:
                import traceback
                traceback.print_exc()
                self._json({"error": str(e)}, 500)
                return
            if detail.get("error") and "not found" in detail["error"]:
                self._json(detail, 404)
            else:
                self._json(detail)
        elif parsed.path == "/api/health":
            self._json({"ok": True})
        else:
            self.send_response(404); self._cors(); self.end_headers(); self.wfile.write(b"Not found")

    def _json(self, obj, status=200):
        body=json.dumps(obj).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type","application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self._cors(); self.end_headers()
        self.wfile.write(body)

    def log_message(self, format, *args):
        sys.stdout.write(f"[web] {self.address_string()} - {format % args}\n")


def start_server(port=8000, open_browser=True):
    addr=("127.0.0.1", port)
    for attempt in range(5):
        try:
            httpd=HTTPServer(addr, ExplainerHandler); break
        except OSError as e:
            print(f"Port {addr[1]} busy, trying {addr[1]+1} ... ({e})")
            addr=("127.0.0.1", addr[1]+1)
    else:
        print("Could not bind."); sys.exit(1)
    actual=httpd.server_address[1]
    url=f"http://127.0.0.1:{actual}/"
    print(f"\n=== Code Explainer ===\nServing at {url}  (also http://localhost:{actual}/)\nKeep this terminal open. Press Ctrl+C to stop.\n")
    if open_browser:
        try: webbrowser.open(url)
        except: pass
    try: httpd.serve_forever()
    except KeyboardInterrupt:
        print("\nShutting down..."); httpd.shutdown()


def print_help():
    print("""Code Explainer — describe any codebase in plain English
Usage:
  python code_explainer.py <path>                 Scan and print report
  python code_explainer.py <path> --deep <name>   In-depth explanation of one function/method
  python code_explainer.py --web [path]           Start browser UI
  python code_explainer.py --web --port 8080      Custom port
  python code_explainer.py --help                 Help
Examples:
  python code_explainer.py .
  python code_explainer.py "C:\\MyProject" --deep login
  python code_explainer.py --web . --port 9000
""")


def main():
    args=sys.argv[1:]
    if not args or args in (["--help"],["-h"]):
        if not args:
            print("Usage: python code_explainer.py <path>  OR  python code_explainer.py --web [path]")
            print("Try --help for more."); sys.exit(1)
        print_help(); sys.exit(0)
    if "--web" in args or "--serve" in args:
        port=8000
        if "--port" in args:
            idx=args.index("--port")
            if idx+1 < len(args):
                try: port=int(args[idx+1])
                except: print(f"Invalid port: {args[idx+1]}"); sys.exit(1)
                args=[a for i,a in enumerate(args) if i not in (idx, idx+1)]
        path_arg=None
        for a in args:
            if a not in ("--web","--serve"): path_arg=a; break
        if path_arg:
            p = Path(path_arg)
            if p.is_file():
                p = p.parent
            if p.exists() and p.is_dir():
                try:
                    os.chdir(p)
                    print(f"Serving folder: {p.resolve()}")
                except Exception as e:
                    print(f"Could not switch to {p}: {e}")
            else:
                print(f"Path not found, serving current folder instead: {path_arg}")
        start_server(port=port)
        return
    # CLI deep dive: python code_explainer.py <path> --deep <name>
    if "--deep" in args:
        idx = args.index("--deep")
        rest = [a for i, a in enumerate(args) if i not in (idx, idx + 1)]
        query = args[idx + 1] if idx + 1 < len(args) else ""
        if not rest or not query:
            print("Usage: python code_explainer.py <path-or-file> --deep <function-name>")
            sys.exit(1)
        target = Path(rest[0])
        if not target.exists():
            print(f"Path not found: {target}"); sys.exit(1)
        root = target if target.is_dir() else target.parent
        if target.is_file():
            detail = deepdive_symbol(target, query, root)
            print_deepdive(detail)
        else:
            found = False
            for p in find_code_files(target):
                if p.suffix.lower() not in CODE_EXTS:
                    continue
                try:
                    t = p.read_text(encoding="utf-8-sig", errors="ignore")
                except Exception:
                    continue
                names = {s.get("name", "").split(".")[-1].lower() for s in (
                    python_symbols(t) if p.suffix.lower() == ".py" else generic_symbols(p.suffix.lower(), t))}
                if query.lower() in names or any(query.lower() in n for n in names):
                    print_deepdive(deepdive_symbol(p, query, target))
                    found = True
                    break
            if not found:
                print(f"No function/method matching '{query}' found under {target}.")
        return
    if len(args)!=1:
        print("Usage: python code_explainer.py <path>"); print("   or: python code_explainer.py <path> --deep <name>"); print("   or: python code_explainer.py --web [path] [--port 8000]"); sys.exit(1)
    root=Path(args[0])
    if not root.exists():
        print(f"Path not found: {root}"); sys.exit(1)
    data=scan_project(root)
    print_report(data)

if __name__=="__main__":
    main()
