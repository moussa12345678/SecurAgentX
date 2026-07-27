#!/usr/bin/env python3
"""
elengenix → securagentx rename script (TEMPLATE — review before running).

Performs safe sed-like substitution using ripgrep for file enumeration,
with proper case-variant handling. Designed to be re-run safely; supports
--dry-run mode for verification.

================================================================
 Case-substitution rules (applied in this exact order, longest-first
 to avoid prefix bugs):
================================================================
    ELENGENIX  →  SECURAGENTX   (uppercase, e.g. ELENGENIX_HOME, ELENGENIX_DIRS)
    Elengenix  →  SecurAgentX   (Title case, e.g. "Elengenix Project",
                                  "moussa12345678/Elengenix", "/mnt/data/Elengenix")
    elengenix  →  securagentx   (lowercase, e.g. `from elengenix.X`,
                                  `elengenix.db`, `~/.elengenix/`,
                                  `elengenix = "main:main"`)

================================================================
 Files excluded from content edits (regenerated, audit output, or binary):
================================================================
    *,cover                              (pytest coverage artifacts, regenerated)
    audit/phase1-*.md                    (Phase 1 audit reports — my own outputs)
    audit/phase2-*.tsv                   (Phase 2 audit TSVs)
    audit/phase2-*.md                    (Phase 2 audit markdown — incl. master plan)
    elengenix-pentagi-integration.tar.gz (binary tarball — KEEP AS-IS per spec)

================================================================
 Files needing MANUAL handling (script REPORTS but does NOT auto-edit):
================================================================
    apply_to_fork.sh              (preserve ARCHIVE= constant + tarball refs on
                                    L8, L16, L17, L19, L57, L58, L68, L92-L97,
                                    L131, L135, L138 — these reference the
                                    KEEP-AS-IS tarball filename)
    apply_to_fork_termux.sh       (same — L7 references ARCHIVE=)
    tests/_pkg_helper.py          (uses dynamic `elen*` glob to discover package
                                    dir; verify post-rename that it still finds
                                    `securagentx/` — pattern `elen*` will FAIL!)

================================================================
 Filename renames (script WILL perform these — only PNG assets):
================================================================
    assets/elengenix.png          → assets/securagentx.png
    assets/elengenix-red.png      → assets/securagentx-red.png
    (elengenix-pentagi-integration.tar.gz is NOT renamed — binary, kept as-is.)

================================================================
 Directory renames (script WILL perform this — top-level package dir):
================================================================
    elengenix/                    → securagentx/
    (Only ONE such directory exists in the project tree per glob `**/elengenix/**`.)

================================================================
 USAGE:
================================================================
    python3 rename_template.py --dry-run                    # preview only
    python3 rename_template.py --dry-run --root /path       # preview, custom root
    python3 rename_template.py --apply                      # perform in-place edits
    python3 rename_template.py --apply --skip-filename-renames --skip-directory-renames
                                                            # content-only pass

Exit codes: 0 = success, 1 = missing dependency / bad args.
"""

from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
from pathlib import Path

# ---- Case-substitution rules (apply in this exact order) ----------------------
# Order matters: ELENGENIX (uppercase) first so that "ELENGENIX_HOME" doesn't
# partially match an "elengenix" substitution; then Elengenix (Title); then
# elengenix (lowercase) last. Because the three forms are distinct strings
# with no character overlap, the order is technically arbitrary, but longest-
# first is the safer convention in case future mixed-case forms appear.
SUBSTITUTIONS: list[tuple[str, str]] = [
    ("ELENGENIX", "SECURAGENTX"),  # uppercase identifiers / headings
    ("Elengenix", "SecurAgentX"),  # Title-case prose, URLs, paths
    ("elengenix", "securagentx"),  # lowercase identifiers, imports, filenames
]

# ---- Files / patterns to EXCLUDE from content edits ---------------------------
EXCLUDE_GLOBS = [
    "*,cover",                              # pytest coverage artifacts (regenerated)
    "audit/phase1-*.md",                    # Phase 1 audit reports
    "audit/phase2-*.tsv",                   # Phase 2 audit TSVs
    "audit/phase2-*.md",                    # Phase 2 audit markdown (incl. this plan)
    "elengenix-pentagi-integration.tar.gz", # binary tarball — KEEP AS-IS
]

# ---- Files needing MANUAL handling (script reports but does NOT auto-edit) ----
MANUAL_REVIEW_FILES = [
    "apply_to_fork.sh",
    "apply_to_fork_termux.sh",
    "tests/_pkg_helper.py",
]

# ---- Filename renames (only asset PNGs; tarball is preserved) -----------------
FILENAME_RENAMES: list[tuple[str, str]] = [
    ("assets/elengenix.png",     "assets/securagentx.png"),
    ("assets/elengenix-red.png", "assets/securagentx-red.png"),
]

# ---- Directory renames (only top-level package dir) ---------------------------
DIRECTORY_RENAMES: list[tuple[str, str]] = [
    ("elengenix", "securagentx"),
]


def find_files_with_brand(root: Path) -> list[Path]:
    """Use ripgrep to list all files containing 'elengenix' (case-insensitive),
    then filter out excluded paths. Manual-review files are returned separately
    by the caller via the MANUAL_REVIEW_FILES list."""
    if not shutil.which("rg"):
        sys.exit("ERROR: ripgrep (rg) not found in PATH. Install ripgrep first.")
    cmd: list[str] = ["rg", "-l", "-i", "elengenix", "--no-messages", "--no-binary"]
    for g in EXCLUDE_GLOBS:
        cmd.extend(["--glob", f"!{g}"])
    cmd.append(str(root))
    result = subprocess.run(cmd, capture_output=True, text=True, check=True)
    files = [Path(line) for line in result.stdout.splitlines() if line.strip()]
    manual_set = {(root / f).resolve() for f in MANUAL_REVIEW_FILES}
    return [f for f in files if f.resolve() not in manual_set]


def apply_substitutions(text: str) -> tuple[str, int]:
    """Apply case-substitution rules in order. Returns (new_text, total_replacements)."""
    total = 0
    for old, new in SUBSTITUTIONS:
        count = text.count(old)
        if count:
            text = text.replace(old, new)
            total += count
    return text, total


def edit_file(path: Path, dry_run: bool) -> tuple[int, int]:
    """Edit a single file in-place (or simulate). Returns (lines_changed, total_replacements).
    Uses surrogateescape so binary-ish bytes round-trip safely."""
    original = path.read_text(encoding="utf-8", errors="surrogateescape")
    new_text, total = apply_substitutions(original)
    if total == 0:
        return 0, 0
    if not dry_run:
        path.write_text(new_text, encoding="utf-8", errors="surrogateescape")
    old_lines = original.splitlines()
    new_lines = new_text.splitlines()
    lines_changed = sum(1 for a, b in zip(old_lines, new_lines) if a != b)
    lines_changed += abs(len(old_lines) - len(new_lines))
    return lines_changed, total


def rename_filename(root: Path, old_rel: str, new_rel: str, dry_run: bool) -> bool:
    old = root / old_rel
    new = root / new_rel
    if not old.exists():
        print(f"  WARN: {old_rel} does not exist, skipping")
        return False
    if new.exists():
        print(f"  WARN: {new_rel} already exists, skipping rename of {old_rel}")
        return False
    if not dry_run:
        old.rename(new)
    return True


def rename_directory(root: Path, old_rel: str, new_rel: str, dry_run: bool) -> bool:
    old = root / old_rel
    new = root / new_rel
    if not old.exists() or not old.is_dir():
        print(f"  WARN: {old_rel}/ does not exist or is not a dir, skipping")
        return False
    if new.exists():
        print(f"  WARN: {new_rel}/ already exists, skipping rename of {old_rel}/")
        return False
    if not dry_run:
        old.rename(new)
    return True


def main() -> int:
    p = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    mode = p.add_mutually_exclusive_group(required=True)
    mode.add_argument("--dry-run", action="store_true",
                      help="Preview only; do not modify any files.")
    mode.add_argument("--apply", action="store_true",
                      help="Perform in-place edits/renames.")
    p.add_argument("--root", default=".",
                   help="Project root directory (default: cwd).")
    p.add_argument("--skip-filename-renames", action="store_true",
                   help="Skip PNG asset filename renames.")
    p.add_argument("--skip-directory-renames", action="store_true",
                   help="Skip elengenix/ → securagentx/ directory rename.")
    args = p.parse_args()

    root = Path(args.root).resolve()
    if not root.is_dir():
        sys.exit(f"ERROR: root {root} is not a directory")

    print(f"=== elengenix → securagentx rename "
          f"{'(DRY RUN)' if args.dry_run else '(APPLY)'} ===")
    print(f"Root: {root}")
    print(f"Substitution rules (in order):")
    for old, new in SUBSTITUTIONS:
        print(f"    {old:<10} → {new}")
    print(f"Excluded globs: {EXCLUDE_GLOBS}")
    print()

    # Step 1: Content edits
    print("--- Step 1/3: Content edits ---")
    files = find_files_with_brand(root)
    print(f"Found {len(files)} files containing 'elengenix' (after exclusions).")
    total_replacements = 0
    files_edited = 0
    for f in sorted(files):
        lines, reps = edit_file(f, dry_run=args.dry_run)
        if reps:
            files_edited += 1
            total_replacements += reps
            try:
                rel = f.relative_to(root)
            except ValueError:
                rel = f
            tag = "[DRY] " if args.dry_run else "[EDIT]"
            print(f"  {tag} {rel}  ({reps} replacements, {lines} lines)")
    print(f"  Total: {files_edited} files edited, {total_replacements} replacements.")
    print()

    # Step 2: Filename renames
    print("--- Step 2/3: Filename renames ---")
    if args.skip_filename_renames:
        print("  Skipped (--skip-filename-renames).")
    else:
        for old_rel, new_rel in FILENAME_RENAMES:
            ok = rename_filename(root, old_rel, new_rel, dry_run=args.dry_run)
            tag = "[DRY] " if args.dry_run else ("[RENAME]" if ok else "[SKIP] ")
            print(f"  {tag} {old_rel} → {new_rel}")
    print()

    # Step 3: Directory renames
    print("--- Step 3/3: Directory renames ---")
    if args.skip_directory_renames:
        print("  Skipped (--skip-directory-renames).")
    else:
        for old_rel, new_rel in DIRECTORY_RENAMES:
            ok = rename_directory(root, old_rel, new_rel, dry_run=args.dry_run)
            tag = "[DRY] " if args.dry_run else ("[RENAME]" if ok else "[SKIP] ")
            print(f"  {tag} {old_rel}/ → {new_rel}/")
    print()

    # Manual review
    print("--- Manual review (NOT auto-edited; review & edit by hand) ---")
    for f in MANUAL_REVIEW_FILES:
        full = root / f
        flag = "EXISTS" if full.exists() else "MISSING"
        print(f"  - {f}  ({flag})")
    print()
    print("=== Done ===")
    return 0


if __name__ == "__main__":
    sys.exit(main())
