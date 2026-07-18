#!/bin/bash

set -e


echo "🚀 Candidate Document Processing - AWS Building"
echo "=================================================="
echo ""
AWS_PROFILE=candidate-doc-verify-deployer sam build --template infra/prod-template.yaml