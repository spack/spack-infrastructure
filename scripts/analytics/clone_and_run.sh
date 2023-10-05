#!/usr/bin/env sh

#### NOTE ####
# This script assumes an alpine image is being used
##############

set -euo pipefail
DATETIME=$(date +%s)

# Install git and python/pip
apk add --no-cache git python3 py3-pip

# Clone spack repo
TEMPDIR=$(mktemp -d)
git clone https://github.com/spack/spack-infrastructure.git $TEMPDIR
ls $TEMPDIR
cd $TEMPDIR/analytics

# Install deps
pip install -r requirements.txt

# Run migrations
./manage.py migrate
