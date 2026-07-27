# Phase 11-B — pyproject.toml + pytest.ini verification

**Task ID:** P11-B
**Agent:** general-purpose (P11-B)
**Scope:** Post-rename (Elengenix → SecurAgentX) verification of Python packaging
metadata and test-runner configuration.

**Files inspected:**
- `/home/z/my-project/securagentx-work/pyproject.toml` (134 lines)
- `/home/z/my-project/securagentx-work/pytest.ini` (9 lines)
- `/home/z/my-project/securagentx-work/.github/workflows/ci.yml` (43 lines)
- `/home/z/my-project/securagentx-work/.github/workflows/test.yml` (47 lines)

---

## 1. pyproject.toml verification

### 1.1 `[project]` identity block — ✅ PASS

| Field | Expected | Actual (line) | Status |
|---|---|---|---|
| `name` | `"securagentx"` | `name = "securagentx"` (L6) | ✅ |
| `version` | present | `version = "1.0.1"` (L7) | ✅ |
| `description` | SecurAgentX-flavoured | `"Autonomous AI Agent Framework for Security Research"` (L8) | ✅ |
| `license` | present | `{text = "GPL-3.0-only"}` (L10) | ✅ |
| `requires-python` | present | `">=3.10"` (L11) | ✅ |
| `authors` | `[{name = "SecurAgentX Project"}]` | `[{name = "SecurAgentX Project"}]` (L12–L14) | ✅ |
| `keywords` / `classifiers` | clean | no Elengenix mentions | ✅ |

### 1.2 `[project.scripts]` — ✅ PASS

```toml
[project.scripts]
securagentx = "main:main"
```

The console-script entry point uses the lowercase `securagentx` package-name
convention (matches `[project] name`) and targets `main:main` (the top-level
`main.py` module's `main()` function). This is consistent with `securagentx/__main__.py`
routing `python -m securagentx` through the same `main()` function.

### 1.3 `[project.urls]` — ✅ PASS

All three URLs point to the canonical `moussa12345678/SecurAgentX` GitHub repository.
No stray `Elengenix` or alternate-fork URLs remain.

```toml
[project.urls]
Homepage  = "https://github.com/moussa12345678/SecurAgentX"
Repository = "https://github.com/moussa12345678/SecurAgentX"
Issues     = "https://github.com/moussa12345678/SecurAgentX/issues"
```

**Identity audit (post-edit):** `grep -i elengenix pyproject.toml` → 0 matches.

### 1.4 `[tool.setuptools.packages.find]` — ✅ PASS

```toml
[tool.setuptools.packages.find]
exclude = ["tests*", "venv*", "scripts*", "data*", "reports*", "examples*",
           "htmlcov*", "docs*", ".config*", ".cache*", "build*", "dist*",
           ".mimocode*", ".remember*"]
```

Excludes the test tree, virtualenvs, build artifacts, caches, and auxiliary
non-package directories from the wheel/sdist. The `tests*` glob is present
(required by task spec).

### 1.5 `[tool.pytest.ini_options]` — ✅ PASS

```toml
[tool.pytest.ini_options]
minversion = "7.0"
testpaths = ["tests"]
asyncio_mode = "auto"
markers = [
    "integration: opt-in integration tests that hit real network/services (deselect with '-m \"not integration\"')",
]
```

Both required keys present: `asyncio_mode = "auto"` (L112) and
`testpaths = ["tests"]` (L111). The `integration` marker is declared so
`-m "not integration"` works in CI.

### 1.6 `dependencies` — ✅ PASS (after fix)

**Original state:** `pytest`, `pytest-asyncio`, `pytest-timeout`,
`itsdangerous`, and `strawberry-graphql` were NOT all declared.

**Findings from source-code audit:**
- `securagentx/auth/sessions.py:114,225` — `from itsdangerous import URLSafeTimedSerializer, BadSignature, SignatureExpired` → **runtime dep**.
- `securagentx/graphql/__init__.py:106` — `import strawberry` → **runtime dep** (lazy import, but still a runtime requirement for GraphQL API).
- `pytest`, `pytest-asyncio`, `pytest-timeout` → **test/dev deps**.

**Fixes applied via Edit tool:**

1. Added `itsdangerous>=2.1.0` and `strawberry-graphql>=0.220.0` to the main
   `dependencies` list (with explanatory inline comments) — these are
   genuinely runtime imports, so they belong in the install_requires surface.
2. Pinned `pytest-asyncio>=0.23.0` (was unpinned) and added `pytest-timeout>=2.1.0`
   to the `[project.optional-dependencies].dev` block.

Final dependency declaration matrix:

| Package | Location | Version pin | Status |
|---|---|---|---|
| `itsdangerous` | `dependencies` (runtime) | `>=2.1.0` | ✅ added |
| `strawberry-graphql` | `dependencies` (runtime) | `>=0.220.0` | ✅ added |
| `pytest` | `optional-dependencies.dev` | `>=7.0.0` | ✅ pre-existing |
| `pytest-asyncio` | `optional-dependencies.dev` | `>=0.23.0` | ✅ pinned (was unpinned) |
| `pytest-timeout` | `optional-dependencies.dev` | `>=2.1.0` | ✅ added |

### 1.7 TOML round-trip — ✅ PASS

`python3 -c "import tomllib; data = tomllib.loads(open('pyproject.toml').read()); ..."`
parses cleanly with no errors. Output:

```
name:    securagentx
scripts: {'securagentx': 'main:main'}
urls:    {'Homepage':   'https://github.com/moussa12345678/SecurAgentX',
         'Repository': 'https://github.com/moussa12345678/SecurAgentX',
         'Issues':     'https://github.com/moussa12345678/SecurAgentX/issues'}
```

---

## 2. pytest.ini verification — ✅ PASS

```ini
[pytest]
asyncio_mode = auto
testpaths = tests
python_files = test_*.py
python_classes = Test*
python_functions = test_*
filterwarnings =
    ignore::DeprecationWarning
```

| Required key | Expected | Actual (line) | Status |
|---|---|---|---|
| `asyncio_mode` | `auto` | `asyncio_mode = auto` (L2) | ✅ |
| `testpaths` | `tests` | `testpaths = tests` (L3) | ✅ |
| `python_files` | `test_*.py` | `python_files = test_*.py` (L4) | ✅ |
| `python_classes` | `Test*` | `python_classes = Test*` (L5) | ✅ |
| `python_functions` | `test_*` | `python_functions = test_*` (L6) | ✅ |

**Note on dual pytest config:** `pytest.ini` and `[tool.pytest.ini_options]`
in `pyproject.toml` both declare `asyncio_mode = auto` and `testpaths = tests`.
When both files exist, `pytest.ini` takes precedence (pytest's config-file
priority order: `pytest.ini` > `pyproject.toml` > `tox.ini` > `setup.cfg`).
Both configurations are consistent with each other, so no conflict — but
future maintainers should be aware that editing only one file is sufficient
and editing only `pyproject.toml` would have no effect while `pytest.ini`
is present.

---

## 3. CI workflow verification

### 3.1 `.github/workflows/ci.yml` — ✅ PASS (after fix)

Matrix job running on `ubuntu-latest` across Python 3.11 / 3.12 / 3.13
(fail-fast: false). The install step previously read:

```yaml
pip install pytest pytest-timeout rich 2>/dev/null || true
```

**Problem:** `pytest-asyncio` was missing. The brutal test suite
(`tests/brutal/`, 1,406 async test functions) uses `async def test_*`
coroutines. With `asyncio_mode = auto` declared in `pytest.ini` /
`pyproject.toml`, pytest-asyncio MUST be installed at runtime — otherwise
pytest aborts with:

> `Skipped (no plugin): async def functions are not natively supported`

**Fix applied:**

```yaml
pip install pytest pytest-asyncio pytest-timeout rich 2>/dev/null || true
```

### 3.2 `.github/workflows/test.yml` — ✅ PASS (after fix)

Single-Python (3.12) extended-suite job. Same install-line fix applied:

```yaml
pip install pytest pytest-asyncio pytest-timeout rich 2>/dev/null || true
```

### 3.3 Why `pip install` is belt-and-suspenders with `pip install -e .`

Both workflows run `pip install -e .` first (which installs runtime
`dependencies`), then explicitly `pip install` the test deps. The dev
optional-deps group is NOT installed by `pip install -e .` alone — that
would require `pip install -e .[dev]`. The explicit `pip install pytest
pytest-asyncio pytest-timeout rich` line is therefore load-bearing and the
correct place to add `pytest-asyncio`.

---

## 4. Summary of fixes applied

| # | File | Change | Reason |
|---|---|---|---|
| 1 | `pyproject.toml` L69–L72 | Added `itsdangerous>=2.1.0` to `dependencies` | Runtime import in `securagentx/auth/sessions.py` |
| 2 | `pyproject.toml` L69–L72 | Added `strawberry-graphql>=0.220.0` to `dependencies` | Runtime import in `securagentx/graphql/__init__.py` |
| 3 | `pyproject.toml` L82 | Pinned `pytest-asyncio>=0.23.0` (was unpinned) | Ensure `asyncio_mode = "auto"` is supported (added in 0.21+) |
| 4 | `pyproject.toml` L83 | Added `pytest-timeout>=2.1.0` to `[project.optional-dependencies].dev` | Matches CI's `--timeout=300` flag |
| 5 | `.github/workflows/ci.yml` L30 | Added `pytest-asyncio` to `pip install` line | Required by brutal async tests; was missing |
| 6 | `.github/workflows/test.yml` L28 | Added `pytest-asyncio` to `pip install` line | Same as above |

No production source files were modified. All changes are to packaging
metadata and CI configuration only.

---

## 5. Verdict

✅ **PASS** — `pyproject.toml` and `pytest.ini` are both correct and
consistent. The Elengenix → SecurAgentX rename is fully reflected in
`[project] name`, `[project.scripts]`, `[project.urls]`, and
`[tool.setuptools]`. All five required packages (`pytest`,
`pytest-asyncio`, `pytest-timeout`, `itsdangerous`, `strawberry-graphql`)
are now declared in the appropriate location (runtime deps in
`dependencies`, test deps in `optional-dependencies.dev`), and CI
explicitly installs the test-time trio so the brutal async suite can run.

**Items verified clean (no fix needed):**
- `[project] name = "securagentx"` ✅
- `authors = [{name = "SecurAgentX Project"}]` ✅
- `[project.scripts] securagentx = "main:main"` ✅
- `[project.urls]` all 3 → moussa12345678/SecurAgentX ✅
- `[tool.setuptools.packages.find]` excludes `tests*` etc. ✅
- `[tool.pytest.ini_options]` has `asyncio_mode = "auto"` and `testpaths = ["tests"]` ✅
- `pytest.ini` has `asyncio_mode = auto`, `testpaths = tests`, `python_files = test_*.py` ✅

**Items fixed (6 edits across 3 files):**
- Added `itsdangerous`, `strawberry-graphql` to runtime deps
- Added `pytest-timeout`, pinned `pytest-asyncio` in dev deps
- Added `pytest-asyncio` to CI install lines in both workflow files
