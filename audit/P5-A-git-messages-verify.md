# P5-A — Ruthless Git History Audit (Commit Messages)

**Audit ID:** P5-A
**Scope:** ALL git commit messages across all branches, tags, and reflog in `/home/z/my-project/securagentx-work/`
**Target string:** `<old-org>` (case-insensitive), plus stem `[<OLD-ORG>]`
**Auditor:** P5-A sub-agent (merciless)
**Date:** 2025-07-28
**Verdict:** **FAIL**

---

## 1. Executive Summary

The orphan-branch strategy was applied to `clean-main` and `securagentx/main`, both of which now carry a single clean commit. **However**, the local `main` branch still retains the full 385-commit legacy history, and **one of those commits (`ea8ca5a`) contains the literal string `<OLD-ORG>` in its message body**. Additionally, the local reflog records the original clone URL `https://github.com/<OLD-ORG>/Elengenix.git` in three entries.

**The <OLD-ORG> identity is therefore NOT fully purged from this repository's git metadata.**

---

## 2. Methodology

| Step | Command | Purpose |
|------|---------|---------|
| 1 | `git log --all --pretty=format:"%H %s" \| head -50` | Enumerate recent commit subjects across all refs |
| 2 | `git log --all --pretty=format:"%H %s%n%b" \| grep -i "<old-org>"` | Case-insensitive full-body scan |
| 3 | `git log --all --pretty=format:"%H %s%n%b" \| grep -E "[<OLD-ORG>]"` | Stem scan (catches `<OLD-ORG>`, `<old-org>`) |
| 4 | `git log --all --oneline \| wc -l` | Total commit count across all branches |
| 5 | `git branch -a` + `git log --oneline -5` | Branch inventory and HEAD |
| 6 | `git log --all -i --grep="<old-org>"` | Locate offending commit(s) precisely |
| 7 | `git branch -a --contains <hash>` + `git merge-base --is-ancestor` | Determine which branches carry offending commit |
| 8 | `git reflog --all \| grep -i <old-org>` | Check reflog for clone-URL leakage |
| 9 | Per-branch `git log -i --grep="<old-org>"` | Build per-branch scorecard |

---

## 3. Repository State

### 3.1 Branch inventory
```
* clean-main              <- current HEAD (orphan, 1 clean commit)
  main                    <- LOCAL main, still has 385 legacy commits
  remotes/origin/HEAD -> origin/main
  remotes/origin/main     <- 384 commits, no <OLD-ORG> in messages
  remotes/securagentx/main <- orphan, 1 clean commit
```

### 3.2 HEAD
```
3456366 feat: SecurAgentX — Autonomous AI Security Research Framework
```

### 3.3 Per-branch scorecard

| Branch              | Commits | Commits w/ `<old-org>` |
|---------------------|--------:|----------------------:|
| `clean-main`        |       1 |                     0 |
| `main` (local)      |     385 |                   **1** |
| `origin/main`       |     384 |                     0 |
| `securagentx/main`  |       1 |                     0 |

- Total commits on the **current (clean-main)** branch: **1**
- Total commits across **all** branches (`git log --all`): **386**

---

## 4. Offending Commit (the smoking gun)

**Hash:** `ea8ca5abed7de7c5b79ca53af68a45ab36b62d20`
**Subject:** `feat: rename Elengenix → SecurAgentX across entire repo + create reports module`
**Parent:** `4eb91a172d008a7a51d8f70fe982a4613d4b3870` (Merge PR #5)
**Reachable from:** `refs/heads/main` (local) — **NOT** from `origin/main`, `clean-main`, or `securagentx/main`

### 4.1 Exact lines in the commit body containing `<OLD-ORG>`

```
  - pyproject.toml: name=securagentx, script=securagentx=main:main,
    URLs → <OLD-ORG>/SecurAgentX, added itsdangerous + strawberry-graphql + pytest-asyncio
```
```
  - All GitHub URLs → <OLD-ORG>/SecurAgentX
```

Both occurrences appear in the commit-message **body** (not subject). The references describe the rename mapping `<OLD-ORG>/Elengenix` → `<OLD-ORG>/SecurAgentX` for GitHub URLs.

### 4.2 Branch ancestry

- The offending commit was created **on top of** `4eb91a1` (the pre-rename HEAD).
- It was then pushed to the local `main` but **never** propagated to `origin/main` (which still points to `4eb91a1`'s lineage).
- The orphan branches `clean-main` and `securagentx/main` do **not** include `ea8ca5a` in their ancestry.

---

## 5. Reflog Leakage (secondary finding)

`git reflog --all` contains **3 entries** that record the original clone source URL:

```
4eb91a1 refs/heads/main@{1}: clone: from https://github.com/<OLD-ORG>/Elengenix.git
4eb91a1 refs/remotes/origin/HEAD@{0}: clone: from https://github.com/<OLD-ORG>/Elengenix.git
4eb91a1 HEAD@{9}: clone: from https://github.com/<OLD-ORG>/Elengenix.git
```

These are local-only reflog entries (not part of any commit object), but they persist in `.git/logs/` until the reflog is expired/cleared. They would be silently copied into any full `.git` directory backup or bundle.

---

## 6. Verdict

### **FAIL**

Reasons:
1. **Commit message on `main` contains `<OLD-ORG>`** (commit `ea8ca5a`, two occurrences in body). The orphan-branch technique was applied to `clean-main` and `securagentx/main`, but the **local `main` branch was never rewritten/deleted** and still exposes the full 385-commit history including the offending message.
2. **Reflog leaks the clone URL** `https://github.com/<OLD-ORG>/Elengenix.git` in 3 entries. Even though reflog is local-only, it is part of `.git/` and must be purged for a clean hand-off.

### Positive findings
- The two orphan branches (`clean-main`, `securagentx/main`) are 100% clean: 1 commit each, zero `<old-org>` occurrences.
- `origin/main` (384 commits) does not contain `ea8ca5a` and has no `<old-org>` in any commit message.
- No tags reference `<old-org>`.

---

## 7. Remediation Required

To convert this FAIL → PASS:

### 7.1 Purge the offending commit from `main`
Option A (recommended — align with orphan strategy):
```bash
git checkout main
git reset --hard clean-main          # point main at the clean orphan commit
git push --force origin main         # if main is meant to be the published branch
```

Option B (rewriting history):
```bash
git filter-repo --replace-message <(echo '<OLD-ORG>==>SecurAgentX') --force
# or use git filter-branch / BFG
```

### 7.2 Expire the reflog
```bash
git reflog expire --expire=now --all
git gc --prune=now --aggressive
```

### 7.3 Re-run this audit
After remediation, re-execute step 2 and step 8 — both must return zero matches.

---

## 8. Raw Evidence

### 8.1 Case-insensitive `<old-org>` scan output
```
    URLs → <OLD-ORG>/SecurAgentX, added itsdangerous + strawberry-graphql + pytest-asyncio
  - All GitHub URLs → <OLD-ORG>/SecurAgentX
```
(both lines from commit `ea8ca5a`)

### 8.2 Stem `[<OLD-ORG>]` scan output
Identical to §8.1 — no additional matches (no `<OLD-ORG>` without the `1` suffix, no `<old-org>` lowercase).

### 8.3 Commit-count commands
```
$ git log --all --oneline | wc -l
386

$ git log clean-main --oneline | wc -l
1

$ git log main --oneline | wc -l
385

$ git log origin/main --oneline | wc -l
384

$ git log securagentx/main --oneline | wc -l
1
```

---

## 9. Sign-off

| Field | Value |
|-------|-------|
| Auditor | P5-A sub-agent |
| Verdict | **FAIL** |
| Blocking issues | 1 commit message on `main` + 3 reflog entries |
| Recommended next phase | P5-B: execute remediation steps §7.1–§7.3, then re-verify |
