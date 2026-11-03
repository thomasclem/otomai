# Optional: deploy Otomai with Quadlet on Bazzite

For the existing `uv build` / `podman-compose` workflow, use [the Compose deployment guide](linux_bazzite_podman.md). This optional alternative deploys **ListingVolumeShortStrategy** as a rootless Podman container managed by systemd/Quadlet. It **trades live** on a dedicated BingX sub-account. Cockpit remains accessible through your existing Cloudflare bridge/tunnel. The bot itself exposes no HTTP service and needs no inbound port.

Run host commands on **Bazzite**, through Cockpit's terminal or a normal login, as the **same non-root Linux user** throughout. Do not run these commands inside Distrobox or use `sudo podman`: that creates a different container store. Commands using `sudo` are called out separately.

Bazzite recommends Quadlet for containerized services. Keep Python and its dependencies inside the image; no host `dnf install` or Python package layering is needed. See [Bazzite's Quadlet guide](https://docs.bazzite.gg/Installing_and_Managing_Software/Quadlet/) and [software installation guidance](https://docs.bazzite.gg/Installing_and_Managing_Software/software-intro/).

## 1. Deployment layout

```text
Browser → Cloudflare Access → existing tunnel/bridge → Cockpit on Bazzite
                                                    └─ user systemd → Otomai container
                                                                       ├─ outbound BingX HTTPS
                                                                       ├─ read-only configuration
                                                                       └─ persistent SQLite directory
```

The Cloudflare connector and Cockpit stay separate from the bot. A Cockpit session closing, or a Cloudflare outage, must not stop trading. Exchange access goes directly through the server's outbound connection; the Cloudflare tunnel does not supply the bot's exchange egress IP.

| Host path | Purpose | Container path |
|---|---|---|
| `~/src/otomai` | Checkout containing the new strategy and refactor | Used only during image build |
| `~/.local/share/otomai/build` | Explicit image-build context, without credentials or state | Build only |
| `~/.local/share/otomai/config` | Strategy YAML and runtime overrides | `/app/config`, read-only |
| `~/.local/share/otomai/data` | Durable state, lock and database sidecars | `/app/data`, writable |
| `~/.config/otomai/runtime.env` | Runtime environment, including live credentials if enabled later | Environment injection |
| `~/.config/containers/systemd/otomai-listing.container` | Service definition | Managed by Quadlet |

A single container is sufficient. Section 8 shows how to place it in a Podman pod if you want pod grouping in Cockpit. Do not run a second replica or a second state file against the same live account.

## 2. Check the host

```bash
cat /etc/os-release
podman --version
podman info --format '{{.Host.CgroupsVersion}}'
systemctl --user status
loginctl show-user "$(id -un)" -p Linger
timedatectl status
```

Cgroups must be v2. Use the host's installed `man podman-systemd.unit` for version-specific support. This guide uses modern Podman/Quadlet, with Podman 5 or newer as the deployment baseline. Check the actual version rather than installing a second Podman through Homebrew.

Enable the user manager at boot and after logout:

```bash
sudo loginctl enable-linger "$(id -un)"
```

Ensure host time is synchronized, automatic desktop sleep is disabled, and the machine remains powered/networked. Plan Bazzite updates and reboots as maintenance: a container cannot execute deadline exits while the host is asleep or rebooting. Boot must reach the user manager unattended; encrypted disks may still require an unlock after power loss.

Create private runtime directories:

```bash
install -d -m 700 "$HOME/.local/share/otomai/build"
install -d -m 700 "$HOME/.local/share/otomai/config"
install -d -m 700 "$HOME/.local/share/otomai/data"
install -d -m 700 "$HOME/.local/share/otomai/backups"
install -d -m 700 "$HOME/.config/otomai"
install -d -m 700 "$HOME/.config/containers/systemd"
```

## 3. Put the intended checkout on the server

Transfer your current Otomai checkout to `~/src/otomai`, or deploy a Git revision containing **all** the new files. The changes may still be uncommitted locally; cloning the old default branch alone will not include them. Do not transfer `.venv`, exchange credentials, research datasets or a running SQLite database as part of the source checkout.

Your existing browser route to Cockpit does not automatically provide SSH/SCP access. Use your configured file-transfer route, LAN SSH if available, or Git after committing the intended source.

Verify on Bazzite:

```bash
cd "$HOME/src/otomai"
test -f uv.lock
test -f src/otomai/strategies/listing_volume_short/strategy.py
test -f src/otomai/strategies/listing_volume_short/lifecycle.py
test -f conf/dev/listing_volume_short.yml
```

## 4. Build an image from the dependency lock

The existing root `Dockerfile` expects a prebuilt wheel and installs its dependencies from `uv.lock`. The Compose guide preserves that workflow. This optional runbook uses its own source-based build context instead.

Use `uv` to export the lock. If it is not installed, Bazzite recommends Homebrew for CLI tools; with Homebrew available, install it using `brew install uv`. Export on the server, or export on your development machine and transfer the resulting file to the build directory. The export retains platform markers and hashes.

```bash
cd "$HOME/src/otomai"
uv export --locked --no-dev --no-emit-project \
  --output-file "$HOME/.local/share/otomai/build/requirements.lock" >/dev/null

cp pyproject.toml README.md "$HOME/.local/share/otomai/build/"
# Copy the current source, including files not yet committed to Git.
cp -a src "$HOME/.local/share/otomai/build/"
```

If repeating the build after deleting or renaming source modules, first remove only the old build-context `src` copy, then copy it again. Never clean the adjacent `data` directory. If `uv export --locked` reports that the lock is stale, resolve it in development and review the dependency change; do not silently update production dependencies.

Create `~/.local/share/otomai/build/Containerfile`:

```dockerfile
FROM docker.io/library/python:3.12-slim
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    TZ=UTC
WORKDIR /build
COPY requirements.lock /build/requirements.lock
RUN pip install --no-cache-dir --require-hashes -r /build/requirements.lock
COPY pyproject.toml README.md /build/
COPY src /build/src
RUN pip install --no-cache-dir --no-deps /build && rm -rf /build
WORKDIR /app
ENTRYPOINT ["otomai"]
```

Only explicit source files enter this context; no `env/`, `.env`, `data/` or host socket is copied or mounted. Python is versioned by minor release here. For reproducible releases, record/pin the base-image digest too; hash-locked Python dependencies alone do not make the whole image reproducible.

Build on Bazzite so the architecture matches the server. Run this as the same user who will own the service:

```bash
podman build --pull=always \
  -f "$HOME/.local/share/otomai/build/Containerfile" \
  -t localhost/otomai:listing-1 \
  "$HOME/.local/share/otomai/build"

podman image inspect localhost/otomai:listing-1 --format '{{.Id}}'
podman run --rm --network none localhost/otomai:listing-1 --help
```

Record the image ID with your release notes. Dependencies are installed during build; starting the service does not install packages. The project currently includes notebook/dashboard dependencies, so the image will be larger than a dedicated minimal runtime image.

## 5. Prepare configuration

```bash
cd "$HOME/src/otomai"
cp conf/prod/listing_volume_short.yml \
  "$HOME/.local/share/otomai/config/listing_volume_short.yml"

cat > "$HOME/.local/share/otomai/config/runtime.yml" <<'YAML'
strategy:
  strategy_params:
    state_path: /app/data/listing_volume_short.live.sqlite
YAML

# Create once; do not overwrite this file when updating an existing deployment.
if [ ! -e "$HOME/.config/otomai/runtime.env" ]; then
  install -m 600 /dev/null "$HOME/.config/otomai/runtime.env"
fi
```

Keep the checked-in strategy defaults unless you deliberately review a rule change. The important operational settings are:

| Setting | Default |
|---|---|
| Poll interval | 30 seconds |
| Position limit | 6 |
| Entry notional | Up to 5% of current equity per candidate |
| Gross admission cap | 30% |
| Same-listing-day admission cap | 10% |
| Stop / target | 20% / 60% |
| Maximum holding period | 504 hours |

Edit `~/.config/otomai/runtime.env` with a local editor; do not enter secrets in shell commands or Git:

```dotenv
BINGX_API_KEY=replace-in-your-editor
BINGX_SECRET=replace-in-your-editor
```

Keep mode `0600`. Values are injected by Podman; do not `source` this file and do not add literal quotes unless they belong to the secret. Use the keys of the dedicated sub-account only. The console notifier needs no token; Telegram is optional.

SQLite state is stored on the host bind mount, not in the disposable container layer. Persist the **whole data directory**, including lock files and any SQLite sidecars, on a local filesystem supporting SQLite locking; do not put live state on an SMB/NFS share.

## 6. Validate the configuration

Validate the merged settings without network access or entering the strategy context:

```bash
podman run --rm --network none \
  -v "$HOME/.local/share/otomai/config:/app/config:ro,Z" \
  --entrypoint python localhost/otomai:listing-1 -c '
from otomai import configs
from otomai.settings import MainSettings
files = [configs.parse_file(p) for p in ["/app/config/listing_volume_short.yml", "/app/config/runtime.yml"]]
s = MainSettings.model_validate(configs.to_object(configs.merge_configs(files)))
assert s.strategy.strategy_params.state_path == "/app/data/listing_volume_short.live.sqlite"
print("Configuration validated")
'
```

The `:Z` suffix applies a private SELinux label to these dedicated mount directories. Do not apply it to your entire home directory or share these directories with another active container. See the [Podman container-unit reference](https://docs.podman.io/en/latest/markdown/podman-container.unit.5.html).

The first cycles can legitimately produce no trades while historical listing references bootstrap. Missing historical data must block the affected signals. Never bake secrets into the image.

## 7. Install the persistent Quadlet service

Save the following as `~/.config/containers/systemd/otomai-listing.container`:

```ini
[Unit]
Description=Otomai listing-volume short (live)
StartLimitIntervalSec=300
StartLimitBurst=5

[Container]
Image=localhost/otomai:listing-1
Pull=never
ContainerName=otomai-listing
WorkingDir=/app
Exec=--files /app/config/listing_volume_short.yml /app/config/runtime.yml
Environment=PYTHONUNBUFFERED=1
Environment=PYTHONDONTWRITEBYTECODE=1
Environment=TZ=UTC
EnvironmentFile=%h/.config/otomai/runtime.env
Volume=%h/.local/share/otomai/config:/app/config:ro,Z
Volume=%h/.local/share/otomai/data:/app/data:Z
ReadOnly=true
Tmpfs=/tmp:rw,nosuid,nodev,size=128m
DropCapability=all
NoNewPrivileges=true
LogDriver=journald
StopSignal=SIGINT
StopTimeout=300

[Service]
Restart=always
RestartSec=15
TimeoutStartSec=180
TimeoutStopSec=330

[Install]
WantedBy=default.target
```

The process runs as root inside a **rootless** user namespace, mapped to your unprivileged host account, so it can write the owner-only data directory without host-root privileges. All capabilities are dropped. No host network, privileged mode, Docker/Podman socket, or published port is required.

`SIGINT` lets Python's `asyncio.run()` cancel the loop and lets the current cycle finish its bookkeeping before the context closes SQLite. The stop timeout is an allowance, not a guarantee: a forced kill can still leave an ambiguous exchange request requiring reconciliation. Restarting uses the existing state; it must never reset it.

Load, inspect and start:

```bash
systemctl --user daemon-reload
systemctl --user cat otomai-listing.service
systemctl --user start otomai-listing.service
systemctl --user status otomai-listing.service
journalctl --user -u otomai-listing.service -n 100 --no-pager
```

Quadlet's `[Install]` section handles boot attachment during generation; **do not run `systemctl --user enable` on the generated service**. Lingering keeps the user manager alive after logout. This behavior and generator diagnostics are described in the [Quadlet reference](https://docs.podman.io/en/latest/markdown/podman-systemd.unit.5.html).

A network outage can occur even after startup. The bot logs cycle failures and retries; an active service is not evidence of successful exchange polling.

## 8. Optional: group the container in a pod

This is optional for one worker. To have a visible Podman pod, create `~/.config/containers/systemd/otomai.pod`:

```ini
[Pod]
PodName=otomai
ExitPolicy=continue
```

Add this line inside the existing container's `[Container]` section:

```ini
Pod=otomai.pod
```

Then stop the existing service, reload and start it again:

```bash
systemctl --user stop otomai-listing.service
systemctl --user daemon-reload
systemctl --user start otomai-listing.service
podman pod ps
```

The `.container` depends on the `.pod`; starting the worker creates its pod. Keep the worker as the service you manage. Do not create a second copy from Cockpit's container wizard. Keep Cockpit and the Cloudflare connector outside this trading pod. See [Podman pod units](https://docs.podman.io/en/latest/markdown/podman-pod.unit.5.html).

## 9. Use Cockpit through your existing Cloudflare access

Keep your existing host `cloudflared-cockpit.service`, `~/.cloudflared/config.yml` and HTTP origin `http://localhost:9090`. Open `https://cockpit.otomai.fr` and log in as the user owning the rootless deployment. The recorded tunnel user is `thomasclem`; verify the container owner rather than inferring it from the tunnel. The [Compose guide](linux_bazzite_podman.md#existing-remote-access-setup) records the supplied access setup and remaining checks. In Cockpit's Podman view, select that user's containers. Root-owned containers and another user's containers are separate stores; an empty view often indicates a user mismatch. If your Cockpit build does not expose user services directly, use its terminal with the `systemctl --user` commands above.

Use systemd as the lifecycle owner. In Cockpit, inspect container logs/details, but start, stop and update the service through `systemctl --user` rather than duplicating it or changing its command through the container UI.

For the remote access path:

- Keep the Cockpit hostname behind an allow-listed Cloudflare Access policy and retain Cockpit's own login. A tunnel route alone is not an identity access policy. [Cloudflare Access application types](https://developers.cloudflare.com/cloudflare-one/access-controls/applications/choose-application-type/).
- The bot has no web UI or health endpoint to publish. It does not need an additional tunnel route or a firewall opening.
- If Cockpit works already, no proxy changes are needed. For rejected WebSocket origins, the Cockpit `Origins` setting must include the **exact HTTPS public origin**; merge it into the existing `[WebService]` configuration rather than overwriting the file. Use `ProtocolHeader = X-Forwarded-Proto` only where a trusted proxy controls that header and the origin cannot be reached through an untrusted bypass. [Cockpit configuration](https://docs.cockpit-project.org/cockpit-guide/362/guide/cockpit-manual.html).
- Your existing connector runs on the host and uses HTTP over loopback to Cockpit; the public browser connection and Cloudflare tunnel remain encrypted. Preserve that working route. Local-origin TLS verification applies only if you deliberately migrate that local hop to HTTPS; it is not an instruction to change the existing route. [Cloudflare origin protocols](https://developers.cloudflare.com/tunnel/troubleshooting/https-origins/).

Losing Cockpit/Cloudflare access does not stop the service. Losing the server's outbound exchange connection does affect execution. Retain a recovery path to the host for maintenance.

## 10. Daily operation and monitoring

```bash
# Follow worker logs.
journalctl --user -u otomai-listing.service -f

# Inspect the service and container without printing their environment.
systemctl --user status otomai-listing.service
podman ps --filter name=otomai-listing

# Restart using the same configuration and state.
systemctl --user restart otomai-listing.service

# Stop the worker deliberately; systemd will not undo a manual stop.
systemctl --user stop otomai-listing.service
```

`WantedBy=default.target` still starts it at the next boot. To keep it stopped across boots, remove that `[Install]` attachment from the Quadlet and run `systemctl --user daemon-reload` after stopping it. Restoring the attachment and reloading restores boot startup.

Watch for recent successful cycle summaries at roughly the configured poll interval, repeated cycle errors, `uncertain` states, missing protection and restarts. The runner can remain active while every cycle fails. There is currently **no external heartbeat alert or health endpoint**, so configure your monitoring separately; do not use an HTTP healthcheck against a nonexistent port or let every transient exchange failure trigger a restart.

Logs go to journald; choose retention using the host's journal configuration. Do not share `podman inspect`, environment dumps or credential files: injected secrets can be visible to the owning user and administrators.

For a read-only state inspection while the service is running, execute Python inside the existing container (this does not start another strategy process):

```bash
podman exec otomai-listing python -c '
import sqlite3
with sqlite3.connect("file:/app/data/listing_volume_short.live.sqlite?mode=ro", uri=True) as db:
    print(db.execute("SELECT status, count(*) FROM listings GROUP BY status").fetchall())
    print(db.execute("SELECT symbol, status FROM listings WHERE status = ?", ("uncertain",)).fetchall())
'
```

Stopping the service does **not** flatten exchange positions or cancel orders. Server-side protective orders may remain active, but local deadline exits cannot execute while stopped.

## 11. Back up, update and roll back

Stop the worker before copying state. In live operation, first verify protection and plan the interruption; never stop a worker with open positions and assume maintenance is risk-free.

```bash
systemctl --user stop otomai-listing.service
backup_file="$HOME/.local/share/otomai/backups/$(date -u +%Y%m%dT%H%M%SZ).tar.gz"
umask 077
tar -czf "$backup_file" \
  -C "$HOME/.local/share/otomai" data config \
  -C "$HOME/.config/containers/systemd" otomai-listing.container
systemctl --user start otomai-listing.service
```

If you added a pod definition, back up `otomai.pod` too. Save `runtime.env` separately in an encrypted secrets backup. Keep the exact image ID/tag and dependency lock with the release. Keep an encrypted backup off the server; the local archive alone does not protect against disk loss.

For an application update:

1. Build and smoke-test a **new image tag**, such as `localhost/otomai:listing-2`, before interrupting the existing service. Never mount active state into a second runner.
2. Stop, back up and change only the `Image=` line in the Quadlet. Keep the configuration and state directory in place.
3. Run `systemctl --user daemon-reload`, then `systemctl --user start otomai-listing.service`. Inspect logs and state transitions.
4. Roll back code by stopping the service, restoring the previous image tag, reloading and starting **against the current state**, provided that version can read the current state schema.

Do not restore an old live database merely to roll back code: the exchange may have received orders after that snapshot. Reconcile persisted client IDs, fills, positions and protective orders first. State identity freezes mode, account and signal/risk rules; incompatible changes fail rather than silently changing an open portfolio. A new state file is not a recovery mechanism for an existing live account.

Application auto-update is intentionally absent. Bazzite OS updates are separate; verify the worker after scheduled reboots and test boot recovery while the bot holds no position.

## 12. Live operation

The current code has known admission limitations: no explicit fee reserve, and account checks use a batch snapshot rather than a fresh snapshot before every POST. Mock tests and this runbook do not remove them.

Use a dedicated BingX **one-way** futures sub-account, isolated margin and 1× leverage. Keep other bots and manual orders off it. Run exactly one worker. Check the account's applicable API permissions and, if using an API IP allow-list, use the server's actual outbound IP—not the Cloudflare hostname/IP.

The state identity records a key fingerprint, so credential rotation needs a new `state_path`; open positions are then adopted from the exchange. Inspect the first cycles and confirm margin/mode setup, entries, protection and deadline handling against the exchange before relying on unattended execution. An `uncertain` entry blocks admission and requires reviewing its client ID; never clear it or retry it by deleting state.

For signal rules, recovery semantics and operational limitations, see [the listing-volume strategy guide](../strategies/listing_volume_short.md).

## Troubleshooting

| Symptom | Check / action |
|---|---|
| Service not found | Run `systemctl --user daemon-reload`; check the filename ends in `.container`, and manage `.service`. Inspect generator errors with `/usr/libexec/podman/quadlet -user -dryrun` on Bazzite; upstream installations may use `/usr/lib/systemd/system-generators/podman-system-generator --user --dryrun`. |
| Container invisible in Cockpit | Verify you are viewing the same user's rootless store; compare `podman ps` in that user's host terminal. |
| Permission denied on `/app/data` | Check the directory owner, dedicated `:Z` mount, and that the service is rootless under the intended account. Do not use `chmod 777` or disable SELinux. |
| Works until logout or reboot | Check lingering, `[Install] WantedBy=default.target`, host sleep and disk unlock. |
| `Another runner owns ...` | Find and stop the duplicate runner. A SQLite process lock ends when the owner exits; deleting a `.lock` file while a process is running can defeat coordination. |
| State identity mismatch | Restore the original account/rules and reconcile; do not reset state for an existing live position. |
| Service active, repeated errors | Inspect successful summaries, exchange connectivity, DNS, clock sync, credentials and API responses; process liveness is insufficient. |
| Start limit reached | Fix the underlying failure, then run `systemctl --user reset-failed otomai-listing.service` and start it again. |
| No signals after startup | Allow reference bootstrap; inspect history errors and expired entry windows. Do not relax missing-history validation to force trades. |
| Container image build fails | Check lock compatibility, registry/package connectivity and architecture. Do not remove version pins or hashes to force a build. |
| Cockpit login works, terminal disconnects | Inspect WebSocket/origin/proxy configuration; keep bot service management independent of browser connectivity. |

## What was verified when writing this guide

Repository CLI arguments, YAML merging, state paths/locking, credential names, log output and the lock export were inspected locally. Official Bazzite, Podman, Cockpit and Cloudflare documentation is linked above. Container build, Quadlet generation, reboot recovery and the Cockpit tunnel still need validation on your Bazzite host; they were not executed on your server while writing this document.
