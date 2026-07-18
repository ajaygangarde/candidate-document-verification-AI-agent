#!/bin/bash

set -e

PROFILE="candidate-doc-verify-deployer"
STACK_NAME="candidate-document-processing"
REGION="us-east-1"

echo "🗑️  Cleaning up AWS stack..."
echo "Stack: $STACK_NAME"
echo "Region: $REGION"
echo ""
read -p "⚠️  This will DELETE the stack. Continue? (y/n) " -n 1 -r
echo
if [[ $REPLY =~ ^[Yy]$ ]]; then
  echo "Deleting stack..."
  AWS_PROFILE=$PROFILE aws cloudformation delete-stack \
    --stack-name $STACK_NAME \
    --region $REGION

  echo "Waiting for deletion to complete..."
  AWS_PROFILE=$PROFILE aws cloudformation wait stack-delete-complete \
    --stack-name $STACK_NAME \
    --region $REGION 2>/dev/null || echo "Stack deletion in progress..."

  echo "✅ Stack deleted!"
else
  echo "Cancelled."
fi
