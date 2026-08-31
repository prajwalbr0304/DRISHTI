"""Deploy only DRISHTI's voice runtime; use an explicit AWS SSO profile."""
import argparse
import base64
import json
from pathlib import Path
import subprocess
import time

import boto3


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--profile", default="prajwal-sso")
    parser.add_argument("--region", default="us-east-1")
    parser.add_argument("--backend", required=True)
    parser.add_argument("--skip-build", action="store_true")
    args = parser.parse_args()
    session = boto3.Session(profile_name=args.profile, region_name=args.region)
    account = session.client("sts").get_caller_identity()["Account"]
    if account != "022499043641":
        raise RuntimeError("Refusing to deploy outside the DRISHTI AWS account")
    region = args.region
    name, repository, role = "drishti_voice", "drishti-voice-relay", "DrishtiBedrockAgentCoreVoice"
    iam, ecr = session.client("iam"), session.client("ecr")
    runtime = session.client("bedrock-agentcore-control")
    prefix = f"arn:aws:bedrock-agentcore:{region}:{account}"
    trust = {"Version": "2012-10-17", "Statement": [{"Effect": "Allow",
        "Principal": {"Service": "bedrock-agentcore.amazonaws.com"}, "Action": "sts:AssumeRole",
        "Condition": {"StringEquals": {"aws:SourceAccount": account},
                      "ArnLike": {"aws:SourceArn": prefix + ":*"}}}]}
    try:
        iam.get_role(RoleName=role)
    except iam.exceptions.NoSuchEntityException:
        iam.create_role(RoleName=role, AssumeRolePolicyDocument=json.dumps(trust),
                        Description="DRISHTI Nova speech relay only")
    try:
        ecr.describe_repositories(repositoryNames=[repository])
    except ecr.exceptions.RepositoryNotFoundException:
        ecr.create_repository(repositoryName=repository, imageScanningConfiguration={"scanOnPush": True})
    log_arn = f"arn:aws:logs:{region}:{account}:log-group:/aws/bedrock-agentcore/runtimes/{name}-*"
    statements = [
        (["bedrock:InvokeModel"], "arn:aws:bedrock:us-east-1::foundation-model/amazon.nova-2-sonic-v1:0"),
        (["ecr:BatchGetImage", "ecr:GetDownloadUrlForLayer"], f"arn:aws:ecr:{region}:{account}:repository/{repository}"),
        (["ecr:GetAuthorizationToken"], "*"),
        (["logs:CreateLogGroup", "logs:DescribeLogStreams", "logs:CreateLogStream", "logs:PutLogEvents"], log_arn),
        (["logs:DescribeLogGroups"], f"arn:aws:logs:{region}:{account}:log-group:*"),
        (["bedrock-agentcore:GetWorkloadAccessToken"], [prefix + ":workload-identity-directory/default",
          prefix + f":workload-identity-directory/default/workload-identity/{name}-*"]),
    ]
    iam.put_role_policy(RoleName=role, PolicyName="DrishtiVoiceRuntimeOnly", PolicyDocument=json.dumps({
        "Version": "2012-10-17", "Statement": [{"Effect": "Allow", "Action": a, "Resource": r} for a, r in statements]}))
    image = f"{account}.dkr.ecr.{region}.amazonaws.com/{repository}:latest"
    if not args.skip_build:
        auth = ecr.get_authorization_token()["authorizationData"][0]
        password = base64.b64decode(auth["authorizationToken"]).decode().split(":", 1)[1]
        subprocess.run(["docker", "login", "--username", "AWS", "--password-stdin", auth["proxyEndpoint"]],
                       input=password, text=True, check=True)
        subprocess.run(["docker", "buildx", "build", "--platform", "linux/arm64", "--provenance=false",
                        "-f", "services/voice-relay/Dockerfile", "-t", image, "--push", "."],
                       cwd=Path(__file__).resolve().parents[2], check=True)
    digest = ecr.describe_images(repositoryName=repository, imageIds=[{"imageTag": "latest"}])["imageDetails"][0]["imageDigest"]
    params = dict(agentRuntimeArtifact={"containerConfiguration": {"containerUri": image.rsplit(":", 1)[0] + "@" + digest}},
        roleArn=f"arn:aws:iam::{account}:role/{role}", networkConfiguration={"networkMode": "PUBLIC"},
        protocolConfiguration={"serverProtocol": "HTTP"},
        lifecycleConfiguration={"idleRuntimeSessionTimeout": 60, "maxLifetime": 600},
        environmentVariables={"DRISHTI_VOICE_BACKEND_URL": args.backend,
                              "BEDROCK_SONIC_REGION": "us-east-1",
                              "BEDROCK_SONIC_MODEL_ID": "amazon.nova-2-sonic-v1:0"})
    agents = runtime.list_agent_runtimes()["agentRuntimes"]
    existing = next((a for a in agents if a["agentRuntimeName"] == name), None)
    if existing:
        response = runtime.update_agent_runtime(agentRuntimeId=existing["agentRuntimeId"], **params)
    else:
        time.sleep(10)  # Allow IAM role creation to propagate.
        response = runtime.create_agent_runtime(agentRuntimeName=name, **params)
    arn, rid = response["agentRuntimeArn"], response["agentRuntimeId"]
    for _ in range(60):
        state = runtime.get_agent_runtime(agentRuntimeId=rid)
        print("Runtime status:", state["status"], flush=True)
        if state["status"] == "READY":
            break
        if state["status"] in {"CREATE_FAILED", "UPDATE_FAILED"}:
            raise RuntimeError(state.get("failureReason", "Runtime deployment failed"))
        time.sleep(10)
    else:
        raise RuntimeError("Runtime readiness timed out")
    iam.put_user_policy(UserName="drishti-bedrock-appsail", PolicyName="DrishtiVoiceRuntimeInvokeOnly",
        PolicyDocument=json.dumps({"Version": "2012-10-17", "Statement": [{"Effect": "Allow",
        "Action": "bedrock-agentcore:InvokeAgentRuntimeWithWebSocketStream", "Resource": [arn, arn + "/runtime-endpoint/*"]}]}))
    print("DRISHTI_SONIC_RUNTIME_ARN=" + arn)


if __name__ == "__main__":
    main()
