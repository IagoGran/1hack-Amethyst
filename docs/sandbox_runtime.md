# Workstream B Sandbox Runtime and Acceptance

## Selected profile

The implementation uses **Docker Engine with Linux containers and the `runc` runtime**, an explicit local Unix socket, and a trusted image pinned by SHA-256 digest. The profile identifier is `docker-runc-readonly-v1`. Docker Engine 25 or later is the feature floor for non-recursive bind mounts, not a security-patch policy: the installed Engine, runc, and kernel must receive supported security updates. The reference configuration uses cgroup v2, working memory/CPU/PID controllers, and Docker's built-in seccomp profile.

The target configurations are Ubuntu 24.04 LTS x86-64 and an Ubuntu 24.04 distribution inside Windows 11 WSL2, with the Linux daemon and workspace in that distribution. WSL workspaces should reside on the distribution's Linux filesystem. Docker Desktop, remote daemons, alternate runtimes, rootless resource-controller configurations, and Windows-mounted workspaces are not validated reference configurations. Their acceptance remains Pending.

The runtime is **disabled by default**. The trusted application bootstrap may pass `enabled=True` only after the configured host and image pass acceptance. This switch is not a model tool or a permission grant. The current provisional launcher does not enable Docker automatically. The acceptance suite explicitly enables disposable sandboxes to test a candidate configuration; passing unit tests is not host acceptance.

## Enforcement and threat boundary

- Each command requires one exact-action approval. Its fingerprint binds arguments, working directory, image digest, network scope, timeout, and output limit. Reuse, revocation, changed proposals, and task/session expiry prevent execution.
- Only the approved workspace is bind-mounted, read-only and non-recursively. Commands cannot edit source files; approved changes use `Workspace` and the reviewed-diff path. The image filesystem is read-only. Bounded `/tmp` scratch space is ephemeral, `nosuid`, `nodev`, and `noexec`; normal container-managed device/runtime mounts also exist.
- The default network is `none`. An explicitly reviewed network-enabled request uses `bridge`, is high impact, and changes the approval fingerprint. Bridge authorization allows outbound networking; it is not a destination allowlist.
- The profile drops all capabilities, enables `no-new-privileges`, fixes `runc`, and uses private IPC and cgroup namespaces. It retains Docker's normal PID isolation, masked system paths, and built-in seccomp policy. It runs with the host user's numeric UID/GID and limits memory to 512 MiB, CPU to one core, and processes to 128.
- The image must already exist locally and declare no `VOLUME` entries. Image health checks are disabled. These restrictions prevent implicit persistent volumes and unrequested background health commands.
- Docker logging is disabled with `--log-driver none`, so raw stdout/stderr is not retained in daemon container logs. The transport captures bounded output; the application redacts it before publishing or saving conversation messages. Docker may retain operational metadata and command arguments while a container exists; command arguments must not contain credentials.
- A complete create/start/inspect operation shares the command deadline. The adapter requires a confirmed exited state and a valid exit code. Timeout, cancellation, and uncertain results never trigger automatic re-execution. Removal stops the container and removes anonymous volumes, including after repeated cancellation. Unconfirmed cleanup is reported as an unknown outcome.
- The Docker CLI receives a fixed local socket and a minimal environment; arbitrary Docker contexts, remote-host variables, and host credentials are not inherited. There is no host-command fallback or automatic image pull.

The host kernel, Docker daemon/client, runtime, configured image, bootstrap, and local workspace owner are trusted. Containers share the host kernel; this profile is not a VM boundary and does not defend against kernel/runtime vulnerabilities or a malicious host administrator. A local socket must actually reach the local trusted daemon, not a forwarding proxy. Host validation must be repeated after relevant runtime, image, kernel, or profile changes. Workspace approval includes every file visible in that workspace; use a scoped workspace without secrets or host service sockets.

Tests that write caches or artifacts must direct them to disposable scratch space, for example pytest's `--basetemp=/tmp/pytest -p no:cacheprovider`. The trusted image must already include the development tools and dependencies. Native executables generated in the `noexec` scratch area cannot be run under this profile.

Docker references: [bind mounts](https://docs.docker.com/engine/storage/bind-mounts/), [Engine 25 mount changes](https://docs.docker.com/engine/release-notes/25.0/), [container security options](https://docs.docker.com/reference/cli/docker/container/run/), and [seccomp](https://docs.docker.com/engine/security/seccomp/).

## Run the live acceptance suite

Provision a trusted Linux image containing `python` (Python 3), with no declared volumes, and record its actual repository digest. Image selection/provisioning and daemon installation are operator actions; the tests do not install, pull, build, or change the daemon. Do not use the placeholder digest below literally.

```bash
export AMETHYST_LIVE_SANDBOX=1
export AMETHYST_SANDBOX_IMAGE='repository@sha256:<actual-local-digest>'
export AMETHYST_DOCKER_SOCKET='/var/run/docker.sock'
# On WSL2, record the Windows host build in addition to the Linux metadata.
export AMETHYST_WINDOWS_BUILD='<Windows 11 build, or N/A on native Ubuntu>'
uv run pytest tests/integration/test_live_sandbox.py -v --junitxml=/tmp/amethyst-sandbox.xml
```

These variables configure the acceptance tests, not production application settings. Without `AMETHYST_LIVE_SANDBOX=1`, the suite skips without accessing Docker. After opt-in, missing configuration, unavailable Docker, unsupported profile settings, and failed probes fail the run. The suite never deletes unrelated containers. It records the host distribution/kernel, Docker version/security settings, architecture, image digest, profile, and optional Windows build as JUnit suite properties. Keep the report with the platform acceptance record.

The probes exercise the production transport, approval engine, and sandbox against disposable workspaces:

1. Read an allowed file; reject existing/new file writes and image filesystem writes.
2. Attempt sibling-path, symlink, and `/proc/1/root` access to a host-only marker; confirm the Docker socket is absent; attempt a privileged mount.
3. Confirm dropped capabilities, no-new-privileges, seccomp, loopback-only interfaces, and lack of an external route.
4. Return a nonzero command exit accurately; bound stdout/stderr; enforce a timeout.
5. Reject approval reuse, revocation, and a changed network scope before container creation.
6. Cancel an actually running container and confirm test-owned containers are removed after every outcome.

These are regression probes for the stated boundary, not proof against every container escape. Unit tests additionally cover disabled runtimes, malformed requests/metadata, image-volume rejection, uncertain state, failed cleanup, repeated cancellation, and sanitized subprocess environments.

## Acceptance record

| Configuration | Result |
|---|---|
| Development host: Ubuntu 22.04.5, x86-64, kernel 6.8.0-138-generic | Deterministic tests pass. Docker client 29.9.3 is present, but local socket access is denied; no live container test ran. This host is outside the approved platform matrix. |
| Ubuntu 24.04 LTS x86-64 | Pending: execute live suite with provisioned image and retain report. |
| Windows 11 / WSL2 / Ubuntu 24.04 | Pending: execute live suite, record Windows build, and retain report. |
| Workstream A desktop + Workstream C adapters | Pending: integrated smoke checks described in `tests/integration/README.md`. |

Do not mark B4 platform acceptance or the overall MVP complete until both target-platform runs and the remaining integrated checks pass.
