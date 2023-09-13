#!/bin/bash

case "${GITHUB_EVENT_NAME}"
in
  pull_request)
    BASE_SHA=$(jq -r .pull_request.base.sha ${GITHUB_EVENT_PATH})
    HEAD_SHA=$(jq -r .pull_request.head.sha ${GITHUB_EVENT_PATH})
    ;;
  push)
    BASE_SHA=$(jq -r .before ${GITHUB_EVENT_PATH})
    HEAD_SHA=$(jq -r .after ${GITHUB_EVENT_PATH})
    ;;
  *)
    echo "Unable to get changed files from '${GITHUB_EVENT_NAME}' event"
    exit 1
esac

echo "Event: ${GITHUB_EVENT_NAME}"
echo "Base: ${BASE_SHA}"
echo "Head: ${HEAD_SHA}"
echo ""

git fetch origin ${BASE_SHA}
git fetch origin ${HEAD_SHA}

echo ""
echo "::group::All changed files"
git diff --name-only ${BASE_SHA}...${HEAD_SHA} | xargs
echo "diff=$(git diff --name-only ${BASE_SHA}...${HEAD_SHA} | xargs dirname | xargs)" >> $GITHUB_OUTPUT
