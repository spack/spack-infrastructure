FROM fedora:40

WORKDIR /app/

# python dependencies
COPY requirements.txt /app/setup/requirements.txt
COPY setup.sh /app/setup/setup.sh
RUN /app/setup/setup.sh

# Install pruning app
COPY __init__.py ./
COPY ci_buildcache_prune.py ./
COPY pruner.py ./
COPY buildcache.py ./
COPY helper.py ./
COPY entrypoint.sh ./

WORKDIR /work/

ENTRYPOINT [ "bash", "/app/entrypoint.sh"]
