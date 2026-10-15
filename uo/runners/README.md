# University of Oregon GitLab runners

The UO runner fleet is described compactly in [`fleet.toml`](./fleet.toml). Each
host's full gitlab-runner `config.toml` is produced from that source by
[`generate.py`](./generate.py) — the boilerplate that is identical across every
runner (docker/cache blocks, the pre-build bootstrap script, the session server)
lives in the generator, so it is defined once instead of copied per runner.

## Editing the fleet

Edit `fleet.toml`. Per-host you set `concurrent` (and optionally
`connection_max_age`); per-runner you set `name`, `id`, `limit`, and an optional
`environment` list. Everything else is fleet-wide boilerplate baked into the
templates in `generate.py`.

## Generating configs to apply

```bash
# print one host's config, with the real token injected, ready to drop on the machine
GITLAB_TOKEN=glrt-xxxx python3 generate.py --host athena --stdout

# write every <host>.config.toml into this directory (uses the %%GITLAB_TOKEN%% placeholder)
python3 generate.py

# write one host to a specific location
python3 generate.py --host athena --out-dir /etc/gitlab-runner
```

If `--token`/`$GITLAB_TOKEN` is not supplied the `token` field is left as the
`%%GITLAB_TOKEN%%` placeholder, so a real token never has to live in the repo.

The original per-host configs this source was derived from are kept for
comparison under [`reference/`](./reference).
