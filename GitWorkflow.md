# Git Workflow Guide
### AI Stock Valuation Chatbot — Baboon Technologies

---

## Branch Structure

```
main        ← demo-ready only. never commit directly here.
  └── dev   ← team's combined work. merge here when a task is done.
        └── feature/E1.1-T1-edgar-cik-resolver   ← your task branch
        └── feature/E2.1-T3-normalize-xbrl        ← someone else's task
        └── fix/E3.1-wacc-calculation              ← a bug fix
```

- **main** is only touched at sprint milestones. It is always the version you can demo.
- **dev** is where everyone integrates. It may have in-progress work at any time.
- **feature branches** are personal. Your mess stays here until you open a PR.

---

## One-Time Setup (do this once per repo)

```bash
git checkout main
git pull origin main
git checkout -b dev
git push origin dev
```

Then protect both branches on GitHub:
> Settings → Branches → Add rule → enable **Require a pull request before merging** for both `main` and `dev`.

Every teammate runs this once to get `dev` locally:

```bash
git checkout dev
git pull origin dev
```

---

## Branch Naming

```
feature/TICKET-ID-short-description    # new functionality
fix/TICKET-ID-short-description        # bug fix
chore/short-description                # dependencies, config, docs
```

Examples from the backlog:

```
feature/E1.1-T1-edgar-cik-resolver
feature/E2.1-T3-normalize-xbrl
feature/E3.1-T11-dcf-orchestrator
feature/E4.3-T2-system-prompt-routing
fix/E3.1-wacc-edge-case
chore/update-dependencies
```

---

## Workflow Per Task

### 1. Before you start

Make sure `dev` is up to date, then branch off it:

```bash
git checkout dev
git pull origin dev
git checkout -b feature/E1.1-T1-edgar-cik-resolver
```

### 2. While you work

Commit after each meaningful step — not at the end of the day.
A good rule of thumb: **one commit per acceptance criteria bullet**.

```bash
git add src/backend/adapters/edgar.py
git commit -m "feat(E1.1-T1): add resolve_cik skeleton with CIK endpoint"

git add src/backend/adapters/edgar.py
git commit -m "feat(E1.1-T1): add in-memory cache for CIK lookups"

git add src/backend/adapters/exceptions.py src/backend/adapters/edgar.py
git commit -m "feat(E1.1-T1): raise TickerNotFoundError for unknown tickers"

git add tests/unit/adapters/test_edgar.py
git commit -m "test(E1.1-T1): add tests for resolve_cik"
```

**Commit message format:**

```
type(TICKET-ID): short description

types: feat | fix | test | chore | docs | refactor
```

### 3. Before opening a PR

Sync with any changes your teammates pushed to `dev` while you were working:

```bash
git fetch origin
git rebase origin/dev
```

If there are conflicts, resolve them, then:

```bash
git add .
git rebase --continue
```

Push your branch:

```bash
git push origin feature/E1.1-T1-edgar-cik-resolver
```

### 4. Open the PR

On GitHub:
- **Base branch:** `dev`
- **Title:** `[E1.1-T1] EDGAR ticker to CIK resolver`
- **Description:** paste the Jira acceptance criteria and link the ticket
- **Reviewer:** assign one teammate

### 5. After the PR is merged

```bash
git checkout dev
git pull origin dev
git branch -d feature/E1.1-T1-edgar-cik-resolver
```

Delete your local branch to keep things clean.
Enable **"Delete branch on merge"** in GitHub settings to auto-delete remote branches.

---

## Sprint Milestones

At the end of each sprint, once `dev` is stable and tested:

```bash
git checkout main
git pull origin main
git merge dev
git push origin main
git tag sprint-1   # or sprint-2, sprint-3
git push origin sprint-1
```

This gives you a clean restore point for each sprint and a demo-ready `main` at all times.

---

## Quick Reference

| Situation | Command |
|---|---|
| Start a new task | `git checkout dev && git pull origin dev && git checkout -b feature/TICKET-short-name` |
| Save progress | `git add FILE && git commit -m "feat(TICKET): description"` |
| Sync with teammates | `git fetch origin && git rebase origin/dev` |
| Push your branch | `git push origin BRANCH-NAME` |
| After PR merged | `git checkout dev && git pull origin dev && git branch -d BRANCH-NAME` |
| End of sprint | `git checkout main && git merge dev && git push origin main` |

---

## Rules

1. Never commit directly to `main` or `dev`.
2. Always branch off `dev`, not `main`.
3. One branch per Jira task.
4. Keep branches short-lived — merge within 3-4 days to avoid conflicts.
5. PR title always includes the Jira ticket ID.
6. At least one teammate reviews every PR before it merges.
