# gh-gl-sync

This document describes the goals and implementation of the gh-gh-sync cron job.

## Responsibilities

The "sync script" as we sometimes call it, implemented in `images/gh-gl-sync/SpackCIBridge.py`
and deployed by `k8s/custom/gh-gl-sync/cron-jobs.yaml`, is mainly responsible for pushing
branches and tags from a GitHub repo to a GitLab repo configured to run pipelines.  It has
the additional responsibility of posting commit statuses back to GitHub based on GitLab
pipeline results.

### Deferred PR pipelines

The sync script supports something we have termed "deferred PR pipelines", which works
like this:  You can specify a `--main-branch` on the command line to enable this feature,
and if you do so, then the script will defer pushing branches for PRs that are based on
a version of that main branch which has not yet been tested in gitlab.  When used for
Spack CI, we specify the `--main-branch` to be `develop`.

## How it works

To accomplish the goals state above, the script makes use of GitHub and GitLab REST api
endpoints, and it performs fairly extensive git operations, the most complex of which
include the operations required to implement deferred PR pipelines.

At a high level the sync script does the following:

1. Use GitHub api to get lists of open pull requests, protected branches and tags, and
merge queue branches.
2. Use `git` commands to initialize a local repo with remotes pointing to the GitHub
and GitLab target repos, fetch all the necessary refs from GitHub, check PR branch
ancestry, make merge commits, etc, and finally push changes to GitLab.
3. Use GitLab api to get pipeline status for all refs of interest, and post those
statuses back to the appropriate commits on GitHub

### Description of Git operaions

Within the `SpackCIBridge.py` module, the high-level algorithm can be followed by
looking at the `sync()` method.  Below we describe in detail the operations
coordinated by that method.

#### `setup_git_repo()`

The `setup_git_repo()` method sets up an empty repo, configures some options, adds
remotes for GitHub and GitLab, and depending on whether there's a main branch, may
fetch `--unshallow` from GitHub.

    git init
    git config user.email noreply@spack.io
    git config user.name spackbot
    git config advice.detachedHead false
    git remote add github self.github_repo
    git remote add gitlab self.gitlab_repo

    git fetch -q --depth=1 gitlab

If there's a main branch we also do:

    git fetch --unshallow github self.main_branch

#### `list_github_prs()`

The `list_github_prs()` is the next method where we run git commands, and it issues
a lot of them, as this is where we implement deferred PR pipelines.  We start by
using the GitHub api to request information about all open PRs, which gives us,
among other bits of info, the `HEAD` sha associated with the PR branch. Then, for
each PR, we perform the following checks and operations:

If the PR is a draft, or has not been updated recently, we will skip pushing.
Otherwise, we get the log of that PR branch from GitLab, so we can search the merge
commit message for the pull head sha.  If this sha matches what we got from the GitHub
api for this PR, we will also skip pushing in this case.

Throughout the remainder of the document we use `<pr_branch_name>` to represent the
PR branch name we push to GitLab.  Those branches actually have this form:
`pr<pr_number>_<pr_branch-name>`.

    git log --pretty=%s gitlab/<pr_branch_name>

Now we are ready to either try to make a merge commit for the PR, or possibly just
fetch GitHub's `merge_commit_sha` for the PR (if deferred PR pipelines is not
enabled, or the PR does not targe the main branch).  For the deferred PR pipeline
case, we:

Fetch the PR branch from GitHub and check its `merge-base` with the main branch:

    git fetch --unshallow github refs/pull/<pull_number>/head:<tmp_pr_branch>
    git merge-base <tmp_pr_branch> github/<main_branch>

Notice that we use a temporary branch name in the above commands, rather than the
branch that we want to push to GitLab.  The reason for this is to support how we
make merge commits, described below.  If the above two commands succeeded, then
we use git to read the sha of PR `HEAD`, which we compare to the value returned
by the api, since we have seen these out of sync in the past.

    git rev-parse <tmp_pr_branch>

Now check if the PR is based on a version of the main branch which has already
been tested by GitLab (which we previously fetched using GitLab REST API):

    git merge-base --is-ancestor merge_base_sha <latest_tested_main_branch_commit>

If we find out PR is based behind a gitlab-tested main branch (meaning the merge-base
between the PR and the main branch *is not* an ancestor of a tested main branch
commit), we mark the PR as "deferred" and will post that on the PR later.  Otherwise,
we make a merge commit having the PR `HEAD` and the latest tested main branch
commit as parents:

    git checkout <latest_tested_main_branch_commit>
    git checkout -b <pr_branch_name>
    git merge --no-ff -m <commit_msg> tmp_pr_branch

The above commands first check out the main branch commit to be used as one of the
parents of the merge commit, from there check out a new branch named as we want
the PR branch named on GitLab, and then create a merge commit (garanteed not to
be a fast-forward) using the temporary branch we fetched for the PR, above.  If
there were any problems running these commands, we make sure to clean up after
ourselves with:

    git merge --abort

 As mentioned earlier, if we don't have a main branch or this PR doesn't target
 it, then we just fetch the `merge_commit_sha` made by GitHub for this PR:

    git fetch --unshallow github <pr_merge_commit_sha>:<pr_branch_name>

#### List all the other branches and tags

The methods `list_github_protected_branches()`, `list_github_tags()`, and
`list_queued_prs()` use the GitHub api to fetch information about protected branches
and tags as well as merge queue branches.  That information is used in the following
methods that build refspecs for fetching (from GitHub) and pushing (to GitLab).

#### get_open_refspecs()

Here we build refspecs for open PRs, and because we've already done the fetching for
open PRs, we only create push refspecs for these now.  These push refspecs have
the form: `<pr_branch_name>:<pr_branch_name>`.

#### update_refspecs_for_queued_prs() and update_refspecs_for_protected_branches()

These method use information from the GitHub api fetched earlier to build fetch
and push refspecs for protected and merge queue branches.  The fetch refspecs take
the form: `+refs/heads/<branch-name>:refs/remotes/<branch-name>`, while the push
refspecs look like `refs/heads/<branch-name>:refs/heads/<branch-name>`.  In both
cases the form of `<branch-name>` is `gh-readonly-queue/<main_branch_name>/pr-<pr_number>-<sha>`.

You may have noticed that destination refspec for fetching doesn't match the source
refspec for pushing.  This is because after we fetch, we create local branches from
the fetched refspecs that will satisfy the source refspecs when we push (described
a bit more below).

#### update_refspecs_for_tags()

This is similar for what we do for branches, above, except for tags we don't need to
check out local branches in between fetching and pushing, so the fetch and push
refspecs are a bit more straightforward.  Fetch refspecs have this form
`+refs/tags/<tag_name>:refs/tags/<tag_name>` while push refspecs have this form:
`refs/tags/<tag_name>:refs/tags/<tag_name>`.

#### fetch_github_branches()

Here we take the list of fetch refspecs we built up and use them to fetch.

    git fetch -q --unshallow github <fetch_refspecs>

#### build_local_branches()

Now that we have fetched, we need to create local branches corresponding to remote
protected and merge queue branches (this is not required for us to push the tags,
so those aren't included here).  For this step, the local branches we create are
named as we want the branches to be named on gitlab and the commands have the form:

    git branch -q <local_branch_name> <remote_ref_spec>

The final step is to push to gitlab all the branches and tags in a single command,
using the list of push refspecs we built up previously.  We do this with "-f" in
case we already pushed any of the branches previously and there are non-fast-forward
changes among those we already pushed.  Git will kindly ignore any branch or tag we
already pushed previously that hasn't changed, but anything that is new will result
in pushing a ref to gitlab, where pipelines are defined with ref-matching patterns
so that protected and pr pipelines can be distinguished.  Here is the push command
we use:

    git push --porcelain -f gitlab <open_refspecs>

### Posting status back to GitHub

To post status to each relevant commit on GitHub, we start by using the GitLab
API to query for piplines run on each ref of interest.

...

