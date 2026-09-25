#!/bin/sh
# Compile the pipeline status page's stylesheet.
#
# Tailwind ships a standalone binary that bundles its own runtime, so this needs no
# node/npm. The binary and the daisyUI package are downloaded on demand into .bin/ and
# node_modules/ (both gitignored); the compiled CSS is committed, so this only needs
# running when a template's classes change.
set -eu

TAILWIND_VERSION="4.0.17"
DAISYUI_VERSION="5.0.9"

cd "$(dirname "$0")"
TAILWIND=".bin/tailwindcss-$TAILWIND_VERSION"
OUTPUT="../static/pipeline_status/app.css"

if [ ! -x "$TAILWIND" ]; then
    echo "Downloading tailwindcss $TAILWIND_VERSION..."
    mkdir -p .bin
    curl -fsSL -o "$TAILWIND" \
        "https://github.com/tailwindlabs/tailwindcss/releases/download/v$TAILWIND_VERSION/tailwindcss-linux-x64"
    chmod +x "$TAILWIND"
fi

# Tailwind resolves `@plugin "daisyui"` from a node_modules directory alongside the
# input stylesheet, so it has to live here even though no package manager is involved.
if [ ! -d "node_modules/daisyui" ]; then
    echo "Downloading daisyui $DAISYUI_VERSION..."
    mkdir -p node_modules
    curl -fsSL "https://registry.npmjs.org/daisyui/-/daisyui-$DAISYUI_VERSION.tgz" \
        | tar -xz -C node_modules
    rm -rf node_modules/daisyui
    mv node_modules/package node_modules/daisyui
fi

"$TAILWIND" -i input.css -o "$OUTPUT" --minify

echo "Wrote analytics/pipeline_status/static/pipeline_status/app.css"
