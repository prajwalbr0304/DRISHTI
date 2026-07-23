# DRISHTI GPU worker - AWS SageMaker / AWS Batch custom inference image (G.3 / Prompt 24).
#
# Separate from the AppSail API image on purpose: this is the ONLY image with
# CUDA + torch + TabFM/TimesFM weights. It runs on AWS GPU compute (SageMaker
# asynchronous inference on ml.g4dn.2xlarge / a T4), scales to zero when idle, and
# is pushed to a PRIVATE ECR repo by immutable digest.
#
# Build (linux/amd64, on a machine/CI with Docker + buildx):
#   docker buildx build --platform linux/amd64 \
#     -f services/gpu-worker/Dockerfile -t drishti-gpu-worker:<ver> --load services/gpu-worker
#
# CUDA runtime base (cu124 matches torch==2.5.1 cu124 wheels; supports T4 sm_75 + A10G sm_86).
FROM nvidia/cuda:12.4.1-cudnn-runtime-ubuntu22.04

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    APP_PORT=8080 \
    GPU_WORKER_VERSION=0.2.0 \
    HF_HOME=/opt/ml/hf \
    HF_HUB_DISABLE_TELEMETRY=1 \
    DEBIAN_FRONTEND=noninteractive

# tabfm/timesfm require Python >= 3.11; ubuntu 22.04 ships 3.10, so install 3.11
# from deadsnakes and run everything from a venv.
RUN apt-get update && apt-get install -y --no-install-recommends \
        software-properties-common ca-certificates && \
    add-apt-repository -y ppa:deadsnakes/ppa && \
    apt-get update && apt-get install -y --no-install-recommends \
        python3.11 python3.11-venv python3.11-dev && \
    rm -rf /var/lib/apt/lists/*

ENV VIRTUAL_ENV=/opt/venv
RUN python3.11 -m venv $VIRTUAL_ENV
ENV PATH="$VIRTUAL_ENV/bin:$PATH"

WORKDIR /opt/program

COPY requirements.txt .
# CUDA (cu124) wheels for torch; the rest from PyPI.
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir \
        --extra-index-url https://download.pytorch.org/whl/cu124 \
        -r requirements.txt

# Weights are NOT baked: the real TabFM classification checkpoint alone is ~6 GB,
# so baking + pushing it from a residential link is impractical. Instead the T4
# endpoint pulls the public, Apache-2.0 Google weights from Hugging Face on first
# use (AWS bandwidth), caches them under HF_HOME, and the loader verifies the
# SHA-256 digest + licence (fail closed). This keeps the pushed image lean.
COPY schema.py backends.py handler.py _tabfm_loader.py selftest.py ./

# SageMaker starts an inference container with `docker run <image> serve`, and the
# CUDA base image's entrypoint execs that argument. Provide a `serve` launcher on
# PATH that starts gunicorn from the venv (serving /ping + /invocations on 8080).
RUN printf '#!/bin/sh\ncd /opt/program\nexec /opt/venv/bin/gunicorn -b 0.0.0.0:8080 -w 1 --timeout 900 "handler:create_app()"\n' \
        > /usr/local/bin/serve && chmod 0755 /usr/local/bin/serve

# Non-root. The venv stays root-owned but world-readable/executable (no chown of
# its ~7 GB tree, which would be slow and duplicate the layer). The worker only
# needs to OWN /opt/ml (runtime HF weight cache) + /opt/program.
RUN useradd --create-home --uid 10002 worker && \
    mkdir -p /opt/ml/hf /opt/ml/model && \
    chown -R worker:worker /opt/program /opt/ml
USER worker

EXPOSE 8080

# SageMaker runs `serve` (above). CMD is the fallback for a local `docker run`.
CMD ["/usr/local/bin/serve"]
