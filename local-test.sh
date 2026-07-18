#!/bin/bash

set -e

echo "🧪 Running local tests..."
echo ""

# Check if database is running
echo "✓ Checking database connection..."
python -c "from recruitment.services.database import get_candidate; print('  Database: OK')" || {
  echo "  ⚠️  Database not available. Make sure PostgreSQL is running."
  exit 1
}

echo ""
echo "✓ Running main.py end-to-end test..."
uv run main.py

echo ""
echo "✅ All tests passed!"
