FROM python:3.14-slim

WORKDIR /app/

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    git \
    jq \
    && rm -rf /var/lib/apt/lists/*

# Don't write .pyc files to disk
ENV PYTHONDONTWRITEBYTECODE=1
# Don't buffer Python output
ENV PYTHONUNBUFFERED=1

# Install Python dependencies
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

# Clone a particular commit of spack
RUN mkdir spack                                                        && \
  cd spack                                                             && \
  git init                                                             && \
  git remote add origin https://github.com/spack/spack.git             && \
  git fetch --depth 1 origin 70a3efe51dbe487e47be5db943f04e92485928ab  && \
  git checkout FETCH_HEAD

COPY entrypoint.sh ./
COPY fetch_keeplists.py ./
COPY prune.py ./
COPY prune_pr_mirrors.py ./

WORKDIR /app/

ENTRYPOINT [ "bash", "/app/entrypoint.sh" ]
