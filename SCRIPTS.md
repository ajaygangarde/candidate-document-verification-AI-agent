# Deployment & Development Scripts

All scripts automate common tasks. Run from project root.

## 🚀 Deployment

### `./deploy.sh`
Full deployment pipeline: exports deps → builds → deploys to AWS Lambda

```bash
./deploy.sh
```

**What it does:**
1. Verifies AWS credentials (uses `candidate-doc-verify-deployer` profile)
2. Exports dependencies from `pyproject.toml` to `requirements.txt`
3. Builds SAM application
4. Deploys to AWS CloudFormation
5. Shows API endpoints

**Note:** Requires AWS profile `candidate-doc-verify-deployer` configured in `~/.aws/credentials`

---

## 📦 Dependency Management

### `./add-dependency.sh <package_name>`
Add a new dependency and automatically sync `requirements.txt`

```bash
./add-dependency.sh requests
./add-dependency.sh langchain
```

**What it does:**
1. Adds package to `pyproject.toml` via `uv add`
2. Exports updated dependencies to `requirements.txt`

### `./export-deps.sh`
Manually sync `requirements.txt` from `pyproject.toml`

```bash
./export-deps.sh
```

Use this if you manually edited `pyproject.toml` or want to refresh deps.

---

## 🧪 Testing

### `./local-test.sh`
Run end-to-end test locally (requires PostgreSQL running)

```bash
./local-test.sh
```

**What it does:**
1. Verifies database connection
2. Runs `python main.py` for full pipeline test
3. Shows results

---

## 🗑️ Cleanup

### `./cleanup-stack.sh`
Delete the CloudFormation stack from AWS

```bash
./cleanup-stack.sh
```

**Warning:** This deletes all resources (Lambda, API Gateway, S3 bucket). Use only if you want to start fresh.

---

## Typical Workflow

### First time deployment:
```bash
./deploy.sh
```

### Adding a new dependency:
```bash
./add-dependency.sh pydantic-extra
./deploy.sh
```

### Local testing before deployment:
```bash
./local-test.sh
# if OK:
./deploy.sh
```

### Clean up and redeploy:
```bash
./cleanup-stack.sh
./deploy.sh
```

---

## Troubleshooting

**"AWS credentials failed"**
- Check `~/.aws/credentials` has `[candidate-doc-verify-deployer]` section
- Run: `AWS_PROFILE=candidate-doc-verify-deployer aws sts get-caller-identity`

**"Database not available"**
- Ensure PostgreSQL is running locally for `local-test.sh`
- For production, set `DATABASE_URL` in Lambda environment

**"SAM build failed"**
- Run `./export-deps.sh` to regenerate `requirements.txt`
- Check `requirements.txt` has all packages from `pyproject.toml`

---

## Configuration

All scripts use these hardcoded values (edit the scripts to change):
- **AWS Profile:** `candidate-doc-verify-deployer`
- **Stack Name:** `candidate-document-processing`
- **Region:** `us-east-1`
- **Template:** `infra/prod-template.yaml`
