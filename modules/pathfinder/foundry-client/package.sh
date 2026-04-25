#!/bin/bash
# package.sh — builds sentinel-connector.zip with correct Foundry subdirectory structure (D-18)
#
# Foundry expects: sentinel-connector/module.json inside the zip (Pitfall 7)
# Usage: cd modules/pathfinder/foundry-client && ./package.sh
#
# After running, serve the zip at:
#   GET http://{SENTINEL_IP}:8000/foundry/static/sentinel-connector.zip
set -euo pipefail

cd "$(dirname "$0")"  # cd to foundry-client/

TMPDIR=$(mktemp -d)
trap "rm -rf $TMPDIR" EXIT

mkdir "$TMPDIR/sentinel-connector"
cp module.json sentinel-connector.js "$TMPDIR/sentinel-connector/"

(cd "$TMPDIR" && zip -r sentinel-connector.zip sentinel-connector/)
mv "$TMPDIR/sentinel-connector.zip" .

echo "Created sentinel-connector.zip"
echo "Verify structure with: unzip -l sentinel-connector.zip"
