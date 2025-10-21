#!/usr/bin/env bash

escapestr() { sed -e 's/[.\/]/\\&/g'; }

IMAGES_FILE=./.github/images.yml
MATRIX_FILE=matrix.json


if [[ -z $EVENT_TYPE ]]; then
    echo EVENT_TYPE env var must be set!
    exit 1
fi

# In the event of a force push, simply using ${{github.event.before}} won't work,
# since it refers to a commit that's no longer in our history. To work around this, we parse the commits manually and
if [ "$EVENT_TYPE" = "push" ]; then
    # Github sets this value as null on pull_request event types
    if [ -z "$COMMITS" ] || [ "$COMMITS" = "null" ]; then
        echo COMMITS env var must be set on push events
        exit 1
    fi

    FIRST_COMMIT=$(echo $COMMITS | jq '.[0].id' |  tr -d '"')
    BEFORE_SHA=$FIRST_COMMIT~1
    AFTER_SHA=$(echo $COMMITS | jq '.[-1].id' |  tr -d '"')
fi

# Defaults are for pull request events
GIT_DIFF="git diff ${BEFORE_SHA:-origin/main} ${AFTER_SHA:-HEAD}"

touch $MATRIX_FILE

# What gets fed into the $image var is defined at the end of the loop
while read image; do
    DOCKER_IMAGE_DIR=$(echo $image | jq '.path' -r | sed 's/^\.\///')
    DOCKER_IMAGE_DIR_PATTERN=$(echo $DOCKER_IMAGE_DIR | escapestr)

    # Skip if the directory was not modified at all
    if ! $GIT_DIFF --name-only | grep "^$DOCKER_IMAGE_DIR_PATTERN" > /dev/null; then
        continue
    fi

    # Only populate file with JSON if the value will not be empty.
    # We do this to make checking the result of this job easier.
    if [ ! -s $MATRIX_FILE ]; then
        echo '{"include": []}' > $MATRIX_FILE
    fi

    # Directory modified, add to list of images to include in matrix
    export IMAGE_TAGS=$(echo $image | jq '(.image + ":" + .version)')
    export IMAGE_PATH=$(echo $image | jq '.path')
    yq '.include += {"docker-image": env(IMAGE_PATH), "image-tags": env(IMAGE_TAGS)}' -o json -i $MATRIX_FILE -I 0

# This is where the input to the while loop variable $image comes in. This is called a "here string" and
# circumvents the issue with subshells setting global variables.
# https://www.gnu.org/savannah-checkouts/gnu/bash/manual/bash.html#Here-Strings
done <<< $(cat $IMAGES_FILE | yq ".images" -o json | jq -c ".[]")

# Now serialize out the images
cat $MATRIX_FILE
