---
name: release
description: End-to-end release workflow for nf-metro. Bumps version in pyproject.toml and __init__.py, drafts a docs/releases/<version>.md page from the git log since the last tag (with illustrations where relevant), wires it into mkdocs.yml nav and the releases index table, then opens a PR. After merge, reminds you to create the GitHub Release. Trigger on phrases like "cut a release", "release X.Y.Z", "prepare release", "bump version to X.Y.Z".
---

# nf-metro Release Workflow

Covers everything from version bump to open PR. After the PR merges you
create the GitHub Release manually — that triggers PyPI publish and the
versioned docs deploy automatically.

## Step 0: Determine the new version

If the user didn't specify a version, read the current one:

```bash
grep '^version' ~/projects/nf-metro/pyproject.toml
```

Ask: "Current version is X.Y.Z — what should the new version be?"
Wait for confirmation before proceeding.

Call the new version `NEW_VERSION` (e.g. `0.8.0`) and the last release
tag `LAST_TAG`.

## Step 1: Gather changes since last release

```bash
LAST_TAG=$(git -C ~/projects/nf-metro describe --tags --abbrev=0)
echo "Last tag: $LAST_TAG"
git -C ~/projects/nf-metro log ${LAST_TAG}..origin/main --oneline
```

Group commits into **Features** (`feat:`), **Fixes** (`fix:`), and
everything else (docs/chores — omit from release notes unless substantial).

For commits that look significant, read the full message:

```bash
git -C ~/projects/nf-metro log --format="%B" -1 <sha>
```

## Step 2: Worktree setup

```bash
git -C ~/projects/nf-metro fetch origin main
git -C ~/projects/nf-metro worktree add /tmp/nf-metro-release-$NEW_VERSION \
    -b release/$NEW_VERSION origin/main
```

All subsequent edits happen inside `/tmp/nf-metro-release-$NEW_VERSION`.

## Step 3: Bump the version in two places

**`pyproject.toml`** — the `version = "X.Y.Z"` line under `[project]`.

**`src/nf_metro/__init__.py`** — the `__version__ = "X.Y.Z"` line.

Verify both:

```bash
grep '^version' /tmp/nf-metro-release-$NEW_VERSION/pyproject.toml
grep '__version__' /tmp/nf-metro-release-$NEW_VERSION/src/nf_metro/__init__.py
```

## Step 4: Draft the release page

Create `/tmp/nf-metro-release-$NEW_VERSION/docs/releases/$NEW_VERSION.md`.

```markdown
# v$NEW_VERSION

*<YYYY-MM-DD>* · [GitHub release](https://github.com/pinin4fjords/nf-metro/releases/tag/$NEW_VERSION) · [Diff](https://github.com/pinin4fjords/nf-metro/compare/$LAST_TAG...$NEW_VERSION)

<one-sentence summary>

## <Feature or fix heading>

<prose for a user who hasn't read the PRs — what it does, why it matters,
how to use it>

![Description](../assets/renders/<relevant_render>.svg)
```

**Illustration guidance:**

- Check what's available: `ls /tmp/nf-metro-release-$NEW_VERSION/docs/assets/renders/`
  (the directory is populated at build time; trust what's in `docs/assets/renders/`
  in the main checkout as a proxy).
- For feature releases, prefer versioned GitHub Pages URLs so readers see
  the exact shipped render:
  `https://pinin4fjords.github.io/nf-metro/$NEW_VERSION/assets/renders/<file>.svg`
  These resolve once the GitHub Release is published and the docs deploy runs.
- For patch releases fixing a visual issue, describe the before/after even
  if you can only show the after state.
- Patch releases with no visual impact (CI fixes, permission fixes) can be
  a single short paragraph with no illustration.

Present the draft. Ask: "Does this look right? Any changes before I commit?"
Wait for approval.

## Step 5: Wire the new page into the nav

### mkdocs.yml

Find the `Releases:` nav section near the bottom of
`/tmp/nf-metro-release-$NEW_VERSION/mkdocs.yml`.

**Patch of an existing minor** (e.g. `0.8.1` when `v0.8.x` already exists):
insert the new entry at the **top** of that block:

```yaml
    - v0.8.x:
      - v0.8.1: releases/0.8.1.md   # ← insert at top
      - v0.8.0: releases/0.8.0.md
```

**New minor version** (e.g. `0.8.0` when there is no `v0.8.x` block yet):
insert a new block at the top of the version list, immediately after the
`- Overview: releases/index.md` line:

```yaml
  - Releases:
    - Overview: releases/index.md
    - v0.8.x:              # ← new block
      - v0.8.0: releases/0.8.0.md
    - v0.7.x:
      ...
```

### releases/index.md

Insert a new row at the **top** of the table (below the header row) in
`/tmp/nf-metro-release-$NEW_VERSION/docs/releases/index.md`:

```markdown
| [v$NEW_VERSION]($NEW_VERSION.md) | <YYYY-MM-DD> | <one-line summary> |
```

## Step 6: Commit and push

```bash
cd /tmp/nf-metro-release-$NEW_VERSION

git add pyproject.toml \
        src/nf_metro/__init__.py \
        docs/releases/$NEW_VERSION.md \
        docs/releases/index.md \
        mkdocs.yml

git commit -m "chore: release $NEW_VERSION"
# No [skip ci] — CI must run on this commit when the PR lands.

git push -u origin release/$NEW_VERSION
```

## Step 7: Open the PR

```bash
gh pr create \
  --repo pinin4fjords/nf-metro \
  --title "chore: release $NEW_VERSION" \
  --body "$(cat <<'EOF'
## Summary

- Bumps version to $NEW_VERSION in \`pyproject.toml\` and \`__init__.py\`
- Adds \`docs/releases/$NEW_VERSION.md\` and wires it into the nav and index

<paste the highlights from the release page here>

## After merge

Create the GitHub Release at https://github.com/pinin4fjords/nf-metro/releases/new
with tag \`$NEW_VERSION\` to trigger the PyPI publish and versioned docs deploy.

🤖 Generated with [Claude Code](https://claude.com/claude-code)
EOF
)"
```

## Step 8: After the PR merges

Remind the user:

> PR merged. Now create the GitHub Release:
> https://github.com/pinin4fjords/nf-metro/releases/new
>
> - **Tag:** `$NEW_VERSION`
> - **Title:** `$NEW_VERSION - <short description>`
> - **Body:** paste the content of `docs/releases/$NEW_VERSION.md`
>   (drop the `# v$NEW_VERSION` heading and the GitHub links line — GitHub
>   generates those itself)
>
> Publishing triggers:
> - `publish.yml` → builds and uploads to PyPI
> - `docs.yml` → deploys versioned docs at
>   `https://pinin4fjords.github.io/nf-metro/$NEW_VERSION/` and updates
>   the `latest` alias

## Step 9: Cleanup

```bash
git -C ~/projects/nf-metro worktree remove /tmp/nf-metro-release-$NEW_VERSION
git -C ~/projects/nf-metro branch -d release/$NEW_VERSION
git -C ~/projects/nf-metro worktree prune
```
