# GitHub Fork Workflow: 2-Person Open Source Guide

This guide explains exactly how the two of you should coordinate your work using a standard open-source "Fork & Pull Request" model. It covers the exact chronological order, how to handle branches, and provides realistic, "human-like" commit messages.

## 1. The Repository Architecture (Main vs Dev)

For a proper open-source project, you should protect the `main` branch and use a `dev` branch for active work.
- **Upstream (`kuberbolt/financial-pod`)**: The central official repository.
  - `main`: Only contains stable, release-ready code.
  - `dev`: The active integration branch where all Pull Requests (PRs) are merged.
- **Your Forks (`contributor-a/financial-pod`, `contributor-b/financial-pod`)**: Your personal copies of the repository where you do the actual coding.

## 2. The Step-by-Step Chronological Workflow

Here is the exact order of how you two should tackle the 4 issues, simulating a real collaborative environment.

### Step 1: Repo Setup & Issue #1 (Contributor A)
1. **Contributor A** forks the upstream repo, clones it locally, and creates a branch off `dev`.
   ```bash
   git checkout dev
   git checkout -b init-core-modules
   ```
2. **Contributor A** does the work for Issue #1 (Foundation & Core Modules).
3. **Realistic Commits by Contributor A**:
   - `init go.mod and figure out lnd protobuf dependencies`
   - `add config loader for lnd certs`
   - `add sqlite db for ledger (no cgo!)`
   - `setup in-memory hodl invoice cache`
   - `wire up main.go with graceful shutdown`
   - `fix typo in config struct` *(Human touch)*
4. **Contributor A** pushes to their fork and opens a **Pull Request** against the upstream `dev` branch.
5. **Contributor B** reviews the PR, leaves a comment like *"Looks good, but maybe we should add a comment to the SQLite init?"*, and then approves and merges it into `dev`.

### Step 2: Syncing & Issue #2 (Contributor B)
1. **Contributor B** syncs their fork with the newly updated upstream `dev` branch.
   ```bash
   git checkout dev
   git pull upstream dev
   git checkout -b lnd-client-budget
   ```
2. **Contributor B** does the work for Issue #2 (LND Client & Budget Manager).
3. **Realistic Commits by Contributor B**:
   - `wip: setting up lnd grpc client`
   - `got tls and macaroon auth working`
   - `add hodl invoice lifecycle methods`
   - `fix int64 underflow bug in budget manager`
   - `hook up budget manager to sqlite ledger`
   - `add tests for spending limits`
4. **Contributor B** pushes to their fork and opens PR #2 against `dev`.
5. **Contributor A** reviews the PR, approves, and merges it.

### Step 3: Issue #3 (Contributor A)
1. **Contributor A** pulls the latest `dev` (which now has Contributor B's LND client code) and starts Issue #3.
   ```bash
   git checkout dev
   git pull upstream dev
   git checkout -b l402-macaroons
   ```
2. **Realistic Commits by Contributor A**:
   - `start working on macaroon bakery`
   - `add time and account caveats`
   - `finally got macaroon verification working with preimages`
   - `cleanup unused imports` *(Human touch)*
   - `add tests for expired macaroons`
3. **Contributor A** pushes and opens PR #3. **Contributor B** reviews and merges.

### Step 4: Issue #4 (Contributor B)
1. **Contributor B** pulls the latest `dev` (which now has Contributor A's macaroon code) and starts Issue #4.
   ```bash
   git checkout dev
   git pull upstream dev
   git checkout -b gateway-wiring
   ```
2. **Realistic Commits by Contributor B**:
   - `start gateway provider logic`
   - `implement requester retry loop`
   - `wire up interceptors to grpc server`
   - `wip: docker integration test`
   - `fix docker test environment vars` *(Human touch)*
   - `update deprecated grpc.WithInsecure to insecure.NewCredentials`
3. **Contributor B** pushes and opens PR #4. **Contributor A** reviews and merges.

## 3. Summary of Git Commands for Forking

Whenever you start a new task, always follow this pattern so you don't get merge conflicts:

```bash
# 1. Switch to your local dev branch
git checkout dev

# 2. Pull the latest changes from the official upstream repo
# (Make sure you have run: git remote add upstream https://github.com/kuberbolt/financial-pod.git)
git pull upstream dev

# 3. Create your new feature branch
git checkout -b my-new-feature

# ... Do your coding, git add, and git commit ...

# 4. Push to YOUR fork (origin)
git push origin my-new-feature
```
Then go to GitHub and click "Compare & pull request" to submit your code to the main upstream repository's `dev` branch.
