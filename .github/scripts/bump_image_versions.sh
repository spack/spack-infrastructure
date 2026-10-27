#!/usr/bin/env bash
# Bump the tag of every custom image whose directory has changed relative to
# BASE_REF (default origin/main), and replace all references to the old tag
# throughout the repo. Images whose tag has already been bumped are skipped,
# so this is safe to re-run.
#
# Usage: ./.github/scripts/bump_image_versions.sh [base-ref]

set -euo pipefail

echoerr() { printf "%s\n" "$*" >&2; }
escapestr() { sed -e 's/[.\/]/\\&/g'; }

cd "$(git rev-parse --show-toplevel)"

IMAGES_FILE=./.github/images.yml
BASE_REF=${1:-origin/main}

# Compare against the merge base, so changes that landed on main after this
# branch was created aren't mistaken for changes made on this branch.
GIT_DIFF="git diff $BASE_REF...HEAD"
# Uncommitted changes count too, so the script can be run before committing.
CHANGED_FILES=$( { $GIT_DIFF --name-only; git diff --name-only HEAD; } | sort -u)
IMAGES_FILE_DIFF=$( { $GIT_DIFF -- $IMAGES_FILE; git diff HEAD -- $IMAGES_FILE; } )

IMAGES=$(cat $IMAGES_FILE | yq ".images" -o json | jq -c ".[]")

BUMPED=0

# What gets fed into the $image var is defined at the end of the loop
while read -r image; do
    DOCKER_IMAGE_DIR=$(echo "$image" | jq -r '.path' | sed 's/^\.\///')
    DOCKER_IMAGE_DIR_PATTERN=$(echo "$DOCKER_IMAGE_DIR" | escapestr)

    # Skip if the directory was not modified at all
    if ! echo "$CHANGED_FILES" | grep "^$DOCKER_IMAGE_DIR_PATTERN/" > /dev/null; then
        continue
    fi

    # Skip if the tag has already been bumped on this branch
    OLD_TAG=$(echo "$image" | jq -r '.image')
    OLD_TAG_PATTERN=$(echo "$OLD_TAG" | escapestr)
    if echo "$IMAGES_FILE_DIFF" | grep "^+[^+].\+$OLD_TAG_PATTERN" > /dev/null; then
        echoerr "Skipping $OLD_TAG, already bumped"
        continue
    fi

    # Increment the last component of the version, e.g. 0.0.9 -> 0.0.10
    BASE_IMAGE_TAG=${OLD_TAG%:*}
    OLD_VERSION=${OLD_TAG##*:}
    NEW_VERSION=$(echo "$OLD_VERSION" | awk -F. -v OFS=. '{ $NF += 1; print }')
    NEW_TAG="$BASE_IMAGE_TAG:$NEW_VERSION"

    # Replace every exact occurrence of the old tag. The trailing group keeps
    # e.g. "foo:0.0.5" from matching "foo:0.0.56".
    git grep -lE "$OLD_TAG_PATTERN([^0-9.]|$)" | while read -r file; do
        sed -i -E "s/$OLD_TAG_PATTERN([^0-9.]|$)/$(echo "$NEW_TAG" | escapestr)\1/g" "$file"
    done

    echo "Bumped $BASE_IMAGE_TAG: $OLD_VERSION -> $NEW_VERSION"
    BUMPED=1

# This is where the input to the while loop variable $image comes in. This is called a "here string" and
# circumvents the issue with subshells setting global variables.
# https://www.gnu.org/savannah-checkouts/gnu/bash/manual/bash.html#Here-Strings
done <<< "$IMAGES"

if [ "$BUMPED" -eq "0" ]; then
    echo "No images need bumping"
fi
