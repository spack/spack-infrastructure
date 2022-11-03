# Gitlab Testing Workflow

This document describes the workflow used to push branches from GitHub to
GitLab, run pipelines, and report status.

Let's follow some diagramming conventions:

- Develop commit associated with the currently GitLab pipeline (if there
is one) is rendering using `type: HIGHLIGHT` so it stands out in the git
graph.
- Develop commit associate with the latest completed GitLab pipeline
includes `COMPLETE` in its label.

## GitHub PR Branch scenarios


## Problems to solve

### Hashes appearing for the first time on develop

This situation arises because changes in PRs don't combine together until they
reach `develop`, and then only one at a time.  Even if both PR branches
are tested with the same `develop`, because they're not tested together, the
new hashes don't appear until the second PR branch is merged.

```mermaid
%%{init: { 'logLevel': 'debug', 'theme': 'base', 'gitGraph': {'rotateCommitLabel': true, 'mainBranchName': 'develop'}} }%%
gitGraph
  commit id: "A"
  branch pr27
  commit id: "update zlib"
  checkout develop
  branch pr28
  commit id: "update cmake"
  checkout develop
  merge pr27
  merge pr28
```

Using GitHub merge queue feature is promising to resolve this problem.  However, using
merge queue introduces other challenges.

### PR pipelines building new develop hashes not yet in mirror

This problem is caused by the lag between new changes getting merged to `develop`
and those changes getting built in a pipeline and pushed to the mirror.  The
amount it happens correlates with how far the commit associated with the latest
*completed* `develop` pipeline is behind the tip of `develop`.

In the figure below, the PR is merged with the tip of `develop`.  When the
pipeline runs, it will find it needs to build any hashes introduced in commits
`C` through `I` on `develop`.  Some of those hashes are likely getting built
in the running `develop` pipeline associated with `E`, but jobs will be
generated for those hashes anyway, since anything already built isn't yet
indexed.

```mermaid
%%{init: { 'logLevel': 'debug', 'theme': 'base', 'gitGraph': {'rotateCommitLabel': true, 'mainBranchName': 'develop'}} }%%
gitGraph
  commit id: "A"
  commit id: "B (COMPLETE)"
  commit id: "C"
  commit id: "D"
  commit id: "E" type: HIGHLIGHT
  commit id: "F"
  commit id: "G"
  commit id: "H"
  commit id: "I (develop HEAD)"
  branch pr27
  commit id: "fix/core"
```

### Repeated merge develop

In the following scenario a user pushes their PR branch, based on a develop
which is behind the currently running develop, but then before that pipeline
finishes, choose to merge `develop` into their PR branch.

```mermaid
%%{init: { 'logLevel': 'debug', 'theme': 'base', 'gitGraph': {'rotateCommitLabel': true, 'mainBranchName': 'develop'}} }%%
gitGraph
  commit id: "A (COMPLETE)"
  commit id: "B"
  branch pr27
  commit id: "fix a thing"
  commit id: "fix another thing"
  checkout develop
  commit id: "C" type: HIGHLIGHT
  commit id: "D"
  checkout pr27
  merge develop
  commit id: "fix something else"
  checkout develop
  commit id: "E"
```
