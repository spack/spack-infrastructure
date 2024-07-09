#!/usr/bin/env bash

echoerr() { printf "%s\n" "$*" >&2; }

WORKFLOW_FILE=./.github/workflows/custom_docker_builds.yml

# Set to 1 if any of the checks fail
FAILED=0

GIT_DIFF='git diff origin/main HEAD'

# test
git branch -a

# What gets fed into the $image var is defined at the end of the loop
while read image; do
    DOCKER_IMAGE_DIR=$(echo $image | jq '."docker-image"' -r | sed 's/^\.\///')
    IMAGE_TAG=$(echo $image | jq '."image-tags"' -r)

    # Skip if the directory was not modified at all
    if ! $GIT_DIFF --name-only | grep $DOCKER_IMAGE_DIR > /dev/null; then
        continue
    fi

    # Is the found tag in the added lines of the diff? If so, don't error just yet.
    # If not, error, as that means the tag we're looking at is the old tag
    if ! $GIT_DIFF -- $WORKFLOW_FILE | grep "^+[^+].\+$IMAGE_TAG" > /dev/null; then
        FAILED=1
        echoerr "ERROR: Directory '$DOCKER_IMAGE_DIR' modified, but image tag $IMAGE_TAG not incremented!"
        continue
    fi

    # Find the old tag from the diff and search for it. If it exists, error, as that means it hasn't been bumped
    BASE_IMAGE_TAG=$(echo $IMAGE_TAG | cut -d ":" -f1)
    BASE_IMAGE_TAG_PATTERN=$(echo $BASE_IMAGE_TAG | sed 's/[.\/]/\\&/g')
    OLD_TAG=$($GIT_DIFF -- $WORKFLOW_FILE | sed -nr s"/^-[^-].+($BASE_IMAGE_TAG_PATTERN)/\1/p")

    NEW_TAG_VERSION=$(echo $IMAGE_TAG | cut -d ":" -f2)
    OLD_TAG_VERSION=$(echo $OLD_TAG | cut -d ":" -f2)

    # Search for this old tag. If found error, as we should only find the new tag
    if git grep $OLD_TAG > /dev/null; then
        FAILED=1
        echoerr "ERROR: Image $BASE_IMAGE_TAG incremented to $NEW_TAG_VERSION, found remaining occurances of $OLD_TAG_VERSION!"
    fi

# This is where the input to the while loop variable $image comes in. This is called a "here string" and
# circumvents the issue with subshells setting global variables.
# https://www.gnu.org/savannah-checkouts/gnu/bash/manual/bash.html#Here-Strings
done <<< $(cat $WORKFLOW_FILE | yq ".jobs.build.strategy.matrix.include" -o json | jq -c ".[]")

if [ "$FAILED" -eq "1" ]; then
    exit 1
fi
