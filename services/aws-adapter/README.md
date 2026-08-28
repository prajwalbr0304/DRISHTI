# DRISHTI protected AWS adapter (Prompt 14 Part F)

The **only** ingress from the Catalyst serving layer to the retained AWS custom
model plane. It runs inside the AWS VPC behind the AWS API Gateway and never
touches the browser.

```
Catalyst frontend
  -> Catalyst Authentication -> API Gateway -> gateway_api (facade)
  -> AppSail FastAPI (services/ml)  [server-side only]
  -> app/bedrock_adapter.py | app/predict/adapter.py  (signed HTTPS clients)
  -> AWS API Gateway (TLS, throttle, request-size cap)
  -> THIS adapter (Lambda or ECS/Fargate, execution-role creds)
  -> Amazon Bedrock Converse (Z.AI GLM 4.7 Flash only)
     | SageMaker (async / real-time) | AWS Batch | Batch Transform
  -> (only where necessary) read-only PostGIS/pgRouting analytics RDS
```

## Why this exists (capability gap, F.6)

Catalyst has no custom GPU runtime for TabFM/TimesFM/ST-GNN and no managed
PostGIS/pgRouting. Those specific workloads stay on AWS; **everything Catalyst
can do stays on Catalyst.** The full justification is in
`services/ml/app/predict/capability_gaps.py` + `infra/aws/capability-gaps.json`
and the Part F phase report.

## Files

| File | Role |
|---|---|
| `signing.py` | HMAC verify (ts+nonce+replay+skew) of inbound requests; sign the result the AppSail client verifies. Self-contained copy of the wire contract (`ENVELOPE_VERSION`). |
| `schema.py` | Thin routing view + fail-closed validation (approved task/backend/dispatch-mode, row + size caps). |
| `circuit.py` | Compact circuit breaker for the adapter's downstream calls. |
| `bedrock.py` | Text-only Converse validation + exact Chinese-model allow-list (`zai.glm-4.7-flash`); no Claude or GPT/OpenAI model can be selected. |
| `dispatch.py` | `FakeDispatcher` (offline, TabFM fails closed) + `AwsDispatcher` (boto3 SageMaker/Batch; idempotency; retry-with-jitter; circuit breaker). |
| `handler.py` | Transport-agnostic `process_request` + `lambda_handler` (API Gateway proxy) + `create_app` (Flask/ECS). |

## Authentication (F.4 — an API key alone is NOT authentication)

Every request must carry:

```
X-DRISHTI-Timestamp        unix seconds
X-DRISHTI-Nonce            single-use random hex
X-DRISHTI-Signature        HMAC_SHA256(secret, "<ts>|<nonce>|<raw-body>")
X-DRISHTI-Envelope-Version 1.0.0
```

The adapter rejects a missing/expired/replayed/forged signature with an opaque
`401`. An API Gateway API key (if used) is only for usage-plan throttling.

Preferred long-term: front the adapter with an OAuth/OIDC authorizer (e.g.
Cognito) and mint tokens via **Catalyst Connections** — see
`services/ml/app/connections.py`.

## Least-privilege execution role (F.5)

The Lambda/ECS role grants only: `bedrock:InvokeModel` on the exact Z.AI GLM
4.7 Flash foundation-model ARN, `sagemaker:InvokeEndpoint` /
`InvokeEndpointAsync` on the DRISHTI endpoint ARNs, `batch:SubmitJob` +
`DescribeJobs` on the DRISHTI queue/definition, `s3:GetObject`/`PutObject` on the
staging prefix only, `secretsmanager:GetSecretValue` on the adapter secret, and
CloudWatch Logs. Claude, GPT/OpenAI, and unreviewed model ARNs are not permitted.
See `infra/aws/adapter/iam/`.

## Config (execution-role env, never static keys, never committed)

```
DRISHTI_AWS_ADAPTER_SECRET      shared HMAC secret (Secrets Manager)
DRISHTI_SM_REALTIME_ENDPOINT    SageMaker real-time endpoint name
DRISHTI_SM_ASYNC_ENDPOINT       SageMaker async endpoint name
DRISHTI_BATCH_JOB_QUEUE         AWS Batch job queue
DRISHTI_BATCH_JOB_DEFINITION    AWS Batch job definition
DRISHTI_ADAPTER_S3_STAGING      s3://bucket/prefix for async/batch I/O
DRISHTI_ADAPTER_MAX_SKEW_S      signature clock-skew window (default 300)
DRISHTI_ADAPTER_RATE_PER_MIN    in-process rate cap (default 600)
DRISHTI_BEDROCK_MODEL_ID         must be zai.glm-4.7-flash (default and only approved ID)
AWS_REGION                       ap-south-1 for the deployed adapter
```

With none of the backend endpoints/queues set, `get_dispatcher()` returns the
offline `FakeDispatcher` (TabFM fails closed) so the adapter is importable and
testable without AWS.

## Deploy (HELD — spends credits / needs the AWS account)

See `infra/aws/adapter/provision_adapter.py` (dry-run plan by default) and the
Part F phase report §"Held cloud steps".
