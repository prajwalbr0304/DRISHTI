# Nova 2 Sonic Voice

## Status (2026-08-31)

- AWS SSO profile `prajwal-sso` verified against account `022499043641`.
- Real Bedrock text/tool/audio and speech/transcription/tool/audio probes passed.
- The existing `drishti-bedrock-appsail` IAM user also passed a real invocation.
- AppSail Docker deployment succeeded. The new voice-session HTTP endpoint returns 200.
- AppSail's public WebSocket upgrade returns HTTP 404, so audio uses the separately
  approved AWS AgentCore runtime `drishti_voice-2j6CnE6mZ7` in `us-east-1`.
- Live gateway -> AgentCore -> Nova -> grounded Ask -> audio tests passed with
  Kiara (one turn) and Arjun (two continuous turns in the same conversation).
- The live Ask planner reported `aws-bedrock`; GLM was not replaced by Sonic.
- Zoho's Nova feature flag is enabled and the capability endpoint reports
  `amazon-nova-2-sonic`, `server-streaming`, and `sonic_available=true`.
- Frontend production build, secret scan, 37 voice/chat tests, 12 backend tests,
  and two relay authorization tests passed. Re-test on deployment after changes.
- These tests use synthetic demo data, not a live police operational feed.

## Architecture

The browser obtains a signed, 60-second voice ticket through the authenticated
Catalyst gateway. It sends that ticket in the first WebSocket frame, never the URL.
The gateway also returns a 60-second SigV4-presigned AgentCore WebSocket URL.
Its signed runtime session ID must match the voice ticket. Each isolated runtime
accepts only one connection. The relay exchanges the ticket over HTTPS with
AppSail for a 450-second, owner/role-bound tool token; the signing secret stays in
Zoho. Tool calls cannot extend expiry or choose another user's conversation.
The relay closes at 440 seconds and the client reconnects with saved chat history.
AgentCore has a 60-second idle timeout and 600-second maximum runtime lifetime.
PCM input rate and frame sizes are bounded. These are connection safeguards, not
an account-wide cost ceiling; configure AWS budgets/quotas for your rollout size.
The legacy local AppSail WebSocket route retains its process-local owner limits.

Audio is mono 16-bit PCM at 16 kHz into Bedrock and 24 kHz out. An AudioWorklet
captures microphone samples; Web Audio schedules returned PCM. Raw audio is not
persisted by DRISHTI. Starting the Nova microphone explicitly consents to sending
audio to AWS in `us-east-1`. The browser does not receive AWS secret keys.

Nova is forced to call `ask_drishti`. That tool uses the same owner-bound,
role-checked, read-only Ask service as text chat. GLM remains the configured text
planner. Structured result cards are delivered separately from Nova's spoken
summary. No model-generated SQL is executed outside the existing query guards.

Available English voices: Kiara, Arjun, Tiffany, Matthew, Amy and Olivia.
Kannada continues through browser speech; Nova 2 Sonic does not list Kannada among
its supported languages. Speech-to-text is the transcript output of the continuous
Sonic session, not an evidence-file transcription API.

## AppSail Environment

| Key | Value |
| --- | --- |
| `DRISHTI_SONIC_ENABLED` | `true` (set `false` to roll back to browser voice) |
| `BEDROCK_SONIC_MODEL_ID` | `amazon.nova-2-sonic-v1:0` |
| `BEDROCK_SONIC_REGION` | `us-east-1` |
| `DRISHTI_SONIC_RUNTIME_ARN` | `arn:aws:bedrock-agentcore:us-east-1:022499043641:runtime/drishti_voice-2j6CnE6mZ7` |
| `DRISHTI_SONIC_WS_URL` | Legacy local transport only; ignored when runtime ARN is set |
| `DRISHTI_SONIC_ALLOWED_ORIGINS` | `https://drishti-frvfpunc.onslate.in,https://drishti-uryfmaue.onslate.in` |

Existing server-only `AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY` and
`ZOHO_APPSAIL_SIGNING_SECRET` are reused. Do not copy SSO session credentials into
Catalyst or commit secrets. Keep `BEDROCK_MODEL_ID=zai.glm-4.7-flash` and the existing
text-planner configuration unchanged.

The added IAM inline policy `DrishtiNovaSonicInvokeOnly` allows only
`bedrock:InvokeModel` on
`arn:aws:bedrock:us-east-1::foundation-model/amazon.nova-2-sonic-v1:0`.
The existing GLM policy is unchanged.

`DrishtiVoiceRuntimeInvokeOnly` allows the AppSail IAM user to open WebSockets on
this runtime only. AgentCore assumes `DrishtiBedrockAgentCoreVoice`, which can
invoke Nova and access its own image/logs, not the DRISHTI database or Zoho secrets.

## Deploy Audio Relay

The relay is a separate ARM64 image. Rebuild it when changing `sonic_stream.py`
or `services/voice-relay`, as backend deployment alone does not update AWS audio.
The script creates/updates the scoped role, ECR image, runtime and invocation policy.

```powershell
cd C:\Users\Prajwal\Desktop\DRISHTI
aws sso login --profile prajwal-sso
python services/voice-relay/deploy.py --backend https://drishti-api-50044118953.development.catalystappsail.in
```

Relay environment (configured by the script): `DRISHTI_VOICE_BACKEND_URL`,
`BEDROCK_SONIC_MODEL_ID`, `BEDROCK_SONIC_REGION`. No long-lived AWS keys are stored
in the image or relay environment. AWS model and AgentCore usage incur charges.

## Deploy Backend

Start Docker Desktop, then run in PowerShell:

```powershell
cd C:\Users\Prajwal\Desktop\DRISHTI
$env:NODE_OPTIONS = '--dns-result-order=ipv4first'
.\infra\catalyst\appsail\deploy.ps1 -Tag drishti-api:sonic -Deploy
```

Do not set `CI=true` for this local CLI workflow: Catalyst's CI mode requires
additional organization/project configuration. Deployment targets the project's
Development AppSail environment, not Production.

## Verify

These probes incur Bedrock usage. WAV input must contain non-sensitive test audio,
16 kHz, mono, signed 16-bit PCM.

```powershell
cd C:\Users\Prajwal\Desktop\DRISHTI
aws sso login --profile prajwal-sso
$env:AWS_PROFILE = 'prajwal-sso'
python services/ml/scripts/probe_sonic.py
python services/ml/scripts/probe_sonic.py C:\path\to\test-question.wav
python -m pytest services/ml/tests/test_sonic.py services/ml/tests/test_voice_auto_send.py -q
```

Verify hosted streaming, including a continuous second turn:

```powershell
python services/ml/scripts/probe_sonic_deployment.py --api https://dhristi-60075362708.development.catalystserverless.in/api --origin https://drishti-uryfmaue.onslate.in --audio C:\path\to\test-question.wav --voice arjun --turns 2
```

This last probe uses the deployed gateway and saves a test conversation. It must
return a user transcript, a grounded answer and audio before rollout is considered
complete. Automated audio probes do not replace a real microphone/listening test.

Slate publishes the frontend from GitHub `main`. Pull before committing and push
the verified changes; check both Slate deployment histories for the new commit.
Do not create a duplicate CLI-hosted Slate app to update these Git-linked apps.

## References

- https://docs.aws.amazon.com/nova/latest/nova2-userguide/sonic-getting-started.html
- https://docs.aws.amazon.com/nova/latest/nova2-userguide/sonic-language-support.html
- https://docs.aws.amazon.com/nova/latest/nova2-userguide/sonic-tool-configuration.html
- https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/runtime-get-started-websocket.html
