# Local setup and reproducibility

This is the authoritative zero-budget setup path for Vexux-AI. It targets
Python 3.11, local Neo4j and local MySQL. Deterministic tests do not require
either database or any model provider service.

## 1. Create an environment and install dependencies

From the repository root:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -r requirements.txt -r requirements-dev.txt
```

On Linux/macOS, activate with `source .venv/bin/activate` instead.

The pinned runtime file contains the existing provider, database, FastAPI, and
optional local ML dependencies. The development file contains test and
formatting tools. Heavy Qwen/Transformers imports remain lazy; selecting
`fake` does not load them.

## 2. Configure the environment

```powershell
Copy-Item .env.example .env
```

`.env` is local-only and ignored by Git. The loader reads it from the
repository root. Explicit process environment variables take precedence over
`.env`; for example:

```powershell
$env:MODEL_PROVIDER = "fake"
```

`fake` is the deterministic, credential-free provider. `ollama` is a
zero-budget local option but requires an already-running local Ollama server
and model. `mistral` requires `MISTRAL_API_KEY` and is not used by deterministic
tests. `qwen` requires the existing local adapter/model files and is optional.

The live Mistral test is opt-in only:

```powershell
$env:RUN_LIVE_MISTRAL_TESTS = "1"
python -m pytest tests/live/test_mistral_recovery.py -q
```

Do not set that flag for normal offline validation.

## 3. Bootstrap local fraud databases

The real fraud composition expects Neo4j database `neo4j` (or the configured
`NEO4J_DATABASE`) and MySQL database `vexux_fraud` (or `MYSQL_DATABASE`).
Create the MySQL database and application user using local administrative
credentials, then grant that user access:

```sql
CREATE DATABASE vexux_fraud;
CREATE USER 'vexux_app'@'localhost' IDENTIFIED BY '<local-password>';
GRANT ALL PRIVILEGES ON vexux_fraud.* TO 'vexux_app'@'localhost';
FLUSH PRIVILEGES;
```

Run the repeatable MySQL schema and seed from the repository root:

```powershell
mysql -h 127.0.0.1 -P 3306 -u vexux_app -p vexux_fraud `
  < apps\fraud\data\mysql\schema.sql
mysql -h 127.0.0.1 -P 3306 -u vexux_app -p vexux_fraud `
  < apps\fraud\data\mysql\seed.sql
```

In Neo4j Browser or with `cypher-shell`, run these files against the configured
Neo4j database in order:

```text
apps/fraud/data/neo4j/schema.cypher
apps/fraud/data/neo4j/seed.cypher
```

The scripts are idempotent for the seeded records. Verify the expected C1001
state with:

```sql
SELECT customer_id, full_name, risk_level
FROM customers WHERE customer_id = 'C1001';
SELECT COUNT(*) AS transaction_count
FROM transactions WHERE customer_id = 'C1001';
SELECT alert_id, alert_type, severity, status
FROM fraud_alerts WHERE customer_id = 'C1001';
```

Expected MySQL facts include Alice Smith, four transactions, and two open
high-severity alerts. Neo4j seed data gives C1001 a shared device relationship
with C1002 and open fraud-case context.

## 4. Run deterministic validation

```powershell
$env:MODEL_PROVIDER = "fake"
python -m pytest -q
python -m evaluation
```

The live database tests are separate and are skipped unless their local
credentials are configured:

```powershell
python -m pytest tests/live/test_fraud_databases.py -q
```

## 5. Start the application

Credential-free API smoke run:

```powershell
$env:MODEL_PROVIDER = "fake"
python -m uvicorn api.main:app --host 127.0.0.1 --port 8000
```

Check process health and configuration readiness:

```powershell
Invoke-RestMethod http://127.0.0.1:8000/health
Invoke-RestMethod http://127.0.0.1:8000/ready
```

`/health` reports process liveness. `/ready` validates provider
configuration; it does not prove that Mistral or Ollama is reachable and does
not replace database verification.

For the real fraud application after both databases are bootstrapped, set the
Neo4j/MySQL variables and run:

```powershell
python -m scripts.manual.run_agent
```

The interactive runner uses the real Neo4j/MySQL composition and has no
synthetic database fallback.
