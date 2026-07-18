#!/bin/bash

set -e

# Configuration
PROFILE="candidate-doc-verify-deployer"
STACK_NAME="candidate-document-processing"
REGION="us-east-1"
TEMPLATE="infra/prod-template.yaml"

echo "🚀 Candidate Document Processing - AWS Deployment"
echo "=================================================="
echo ""

# 1. Verify AWS credentials
echo "✓ Checking AWS credentials..."
AWS_PROFILE=$PROFILE aws sts get-caller-identity > /dev/null 2>&1 || {
  echo "❌ AWS credentials failed. Check AWS_PROFILE=$PROFILE"
  exit 1
}
echo "  Using account: $(AWS_PROFILE=$PROFILE aws sts get-caller-identity --query Account --output text)"
echo ""

# 2. Export dependencies (to src for Lambda)
echo "📦 Exporting dependencies to src/requirements.txt..."
uv export --format requirements-txt | grep -v "^-e" > src/requirements.txt
cp src/requirements.txt requirements.txt
echo "  ✓ src/requirements.txt updated"
echo ""

# 3. SAM Build
echo "🔨 Building SAM application..."
AWS_PROFILE=$PROFILE sam build --template $TEMPLATE
echo "  ✓ Build complete"
echo ""

# 3b. Overlay the Linux psycopg[binary] wheel into each function's build dir.
# sam build on macOS installs the macOS wheel; Lambda runs Linux x86_64.
# psycopg[binary] publishes pre-built manylinux2014_x86_64 wheels on PyPI that
# statically bundle libpq, so we can pull the correct wheel without Docker.
echo "🐧 Installing Linux psycopg[binary] into build artifacts..."
for FUNC in ApiFunction ProcessVerificationFunction; do
  uv pip install \
    --python-platform manylinux2014_x86_64 \
    --python 3.13 \
    --only-binary=:all: \
    --target ".aws-sam/build/$FUNC" \
    "psycopg[binary]" --quiet
  echo "  ✓ $FUNC"
done
echo ""

# 4. SAM Deploy
# NOTE: Do NOT pass --template-file here. Omitting it makes sam deploy use the
# built template at .aws-sam/build/template.yaml (which bundles the installed
# dependencies). Pointing --template-file at the raw source template would
# re-package straight from src/ and drop every third-party dependency.
echo "🌍 Deploying to AWS Lambda..."
AWS_PROFILE=$PROFILE sam deploy \
  --stack-name $STACK_NAME \
  --resolve-s3 \
  --capabilities CAPABILITY_IAM \
  --no-confirm-changeset

echo ""
echo "✅ Deployment complete!"
echo ""

# 5. Get API endpoint
echo "📍 API Endpoints:"
AWS_PROFILE=$PROFILE aws apigateway get-rest-apis --region $REGION --query "items[?name=='candidate-document-processing (erua4gd8tl)'].id" --output text | xargs -I {} \
  AWS_PROFILE=$PROFILE aws apigateway get-stages --rest-api-id {} --region $REGION --query "item[*].[stageName,variables]" --output text 2>/dev/null || echo "  POST https://erua4gd8tl.execute-api.us-east-1.amazonaws.com/prod/create_verification"

echo ""
echo "📝 Next steps:"
echo "  1. Upload documents to S3 using presigned URLs"
echo "  2. Start processing: POST /prod/start_verification"
echo "  3. Fetch results: GET /prod/get_verification"
