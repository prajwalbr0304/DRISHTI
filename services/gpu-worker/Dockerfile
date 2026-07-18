# DRISHTI GPU worker — AWS SageMaker / AWS Batch custom inference image (G.3).
#
# Separate from the AppSail API image on purpose: this is the ONLY image with
# CUDA + torch + TabFM/TimesFM weights. It runs on AWS GPU compute (SageMaker
# async / Batch Transform / AWS Batch), scales to zero when idle, and is pushed
# to a PRIVATE ECR repo by immutable digest.
#
# Build (linux/amd64, on a machine/CI with Docker + buildx):
#   docker buildx build --platform linux/amd64 \
#     -f services/gpu-worker/Dockerfile -t drishti-gpu-worker:<ver> --load services/gpu-worker
#
# CUDA runtime base (cu124 matches torch==2.5.1 cu124 wheels).
FROM nvidia/cuda:12.4.1-cudnn-runtime-ubuntu22.04

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    APP_PORT=8080 \
    GPU_WORKER_VERSION=0.1.0 \
    TABFM_WEIGHTS_DIR=/opt/ml/model/tabfm

RUN apt-get update && apt-get install -y --no-install-recommends \
        python3.11 python3-pip ca-certificates && \
    rm -rf /var/lib/apt/lists/*

WORKDIR /opt/program

COPY requirements.txt .
# CUDA (cu124) wheels for torch; the rest from PyPI.
RUN python3 -m pip install --no-cache-dir --extra-index-url https://download.pytorch.org/whl/cu124 \
        -r requirements.txt

COPY schema.py backends.py handler.py _tabfm_loader.py ./

# Non-root.
RUN useradd --create-home --uid 10002 worker && \
    mkdir -p /opt/ml/model && chown -R worker:worker /opt/program /opt/ml
USER worker

EXPOSE 8080

# SageMaker invokes /ping and /invocations. gunicorn serves the Flask app.
# Weights are loaded once per warm worker (cold start reported separately).
CMD ["gunicorn", "-b", "0.0.0.0:8080", "-w", "1", "--timeout", "900", "handler:create_app()"]
