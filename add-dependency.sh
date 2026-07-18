#!/bin/bash

# Usage: ./add-dependency.sh <package_name>

if [ -z "$1" ]; then
  echo "Usage: ./add-dependency.sh <package_name>"
  echo "Example: ./add-dependency.sh requests"
  exit 1
fi

PACKAGE=$1

echo "📦 Adding dependency: $PACKAGE"
uv add $PACKAGE
echo ""
echo "📄 Exporting to src/requirements.txt..."
uv export --format requirements-txt | grep -v "^-e" > src/requirements.txt
cp src/requirements.txt requirements.txt
echo "✓ Done! src/requirements.txt updated"
echo ""
echo "Next step: ./deploy.sh"
