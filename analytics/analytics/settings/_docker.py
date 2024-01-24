from pathlib import Path


def _is_docker() -> bool:
    """Determine whether the current environment is within a Docker container."""
    # https://tuhrig.de/how-to-know-you-are-inside-a-docker-container/
    # However, this does not work on Debian 11+ containers: https://stackoverflow.com/q/69002675
    cgroup_file = Path("/proc/self/cgroup")
    # The cgroup file may not even exist on macOS
    if cgroup_file.exists():
        with cgroup_file.open() as cgroup_stream:
            # This file should be small enough to fully read into memory
            if "docker" in cgroup_stream.read():
                return True

    # An alternative detection method, but this is deprecated by Docker:
    # https://stackoverflow.com/q/67155739
    if Path("/.dockerenv").exists():
        return True

    return False


class _AlwaysContains:
    """An object which always returns True for `x in _AlwaysContains()` operations."""

    def __contains__(self, item) -> bool:
        # https://stackoverflow.com/a/49818040
        return True
