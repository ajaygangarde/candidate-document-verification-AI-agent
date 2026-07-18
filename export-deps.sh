#!/bin/bash

# Export dependencies from pyproject.toml to src/requirements.txt (Lambda location)
echo "📦 Exporting dependencies from pyproject.toml..."
uv export --format requirements-txt | grep -v "^-e" > src/requirements.txt

# Also update root for local dev reference
cp src/requirements.txt requirements.txt

echo "✓ src/requirements.txt updated"
echo ""
echo "Updated dependencies:"
cat src/requirements.txt
