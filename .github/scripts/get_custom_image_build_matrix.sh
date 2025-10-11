#!/usr/bin/env bash

escapestr() { sed -e 's/[.\/]/\\&/g'; }

IMAGES_FILE=./.github/images.yml
GIT_DIFF='git diff origin/main HEAD'
MATRIX_FILE=matrix.json

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
