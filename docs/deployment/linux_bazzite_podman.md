# Deploy Otomai on Bazzite using your existing Compose workflow

Keep the workflow you already use: create the environment files, run `uv build`, then start the `app` service with `podman-compose`. Your Cockpit–Cloudflare bridge remains the management access path. The worker needs outbound exchange access and exposes no inbound port.

Run these commands from the Otomai repository on the **Bazzite host**, as the same non-root user you use in Cockpit. Keep the checkout at a stable path: Compose resolves `./data` relative to this checkout. Do not run deployment inside Distrobox or mix `podman` and `sudo podman` stores.

For a clean machine, first follow [the fresh-server Cockpit and Cloudflare runbook](bazzite_cockpit_cloudflare.md).

## Existing remote-access setup

The following records the setup you supplied; it is not a fresh inspection of the server.

```text
Remote browser → https://cockpit.otomai.fr → Cloudflare Access (email OTP)
               → encrypted Cloudflare Tunnel "cockpit"
               → host cloudflared → http://localhost:9090 → Cockpit / Podman
```

| Component | Existing value |
|---|---|
| Host OS | Bazzite |
| Public Cockpit URL | `https://cockpit.otomai.fr` |
| Podman page | `https://cockpit.otomai.fr/podman` |
| Domain registrar | IONOS; Cloudflare supplies the tunnel/public HTTPS |
| Host tunnel binary | `~/.local/bin/cloudflared` |
| Tunnel configuration | `~/.cloudflared/config.yml` |
| User systemd service | `cloudflared-cockpit.service` |
| Tunnel name / ID | `cockpit` / `30d6d1ac-ceae-42f0-8696-422af25842ab` |
| Tunnel user's home | `/home/thomasclem` as recorded in the credentials path |
| Local origin | `http://localhost:9090` |
| Access authentication | Email OTP reported working previously; separate MFA enforcement and recent OTP delivery remain unverified |

Your reported existing `~/.cloudflared/config.yml` is:

```yaml
tunnel: cockpit
credentials-file: /home/thomasclem/.cloudflared/30d6d1ac-ceae-42f0-8696-422af25842ab.json

ingress:
  - hostname: cockpit.otomai.fr
    service: http://localhost:9090
  - service: http_status:404
```

This is a reference copy, not a command to overwrite the working configuration. Keep the credentials JSON private; its contents do not belong in the repository or this guide. Preserve any working Cockpit proxy settings already in place.

The **local hop is HTTP over loopback**, while the browser uses public HTTPS and the Cloudflare-to-connector tunnel is encrypted. Cockpit permits HTTP connections from localhost, so this route does not inherently require `AllowUnencrypted=true` globally or `noTLSVerify`. Keep the existing HTTP origin; do not change it to HTTPS merely to deploy the worker. [Cockpit TLS behavior](https://docs.cockpit-project.org/cockpit-guide/main/guide/https.html), [Cloudflare origin protocols](https://developers.cloudflare.com/tunnel/troubleshooting/https-origins/).

The host `cloudflared-cockpit.service` and the Compose worker are independent. Do not put the tunnel into the trading pod, launch a second tunnel process, or replace your tunnel service as part of this deployment. Confirm the rootless Podman owner with `id -un` and Cockpit's user selection; the recorded tunnel user is `thomasclem`, but that alone does not prove which user owns every existing container.

## 1. Create the environment files once

For the new strategy:

```bash
mkdir -p env/listing_volume_short data
chmod 700 env env/listing_volume_short data

# Preserve any existing files and credentials.
for env_file in env/base.env env/listing_volume_short/prod.env; do
  if [ ! -e "$env_file" ]; then
    install -m 600 /dev/null "$env_file"
  fi
done

```

The bot trades live, so put the keys of the dedicated prod sub-account in `env/listing_volume_short/prod.env` with your editor:

```dotenv
BINGX_API_KEY=replace-in-your-editor
BINGX_SECRET=replace-in-your-editor
```

Keep secrets out of YAML, shell history and Git. The repository ignores `env/`. The app-only Compose deployment reads these two environment files; a legacy dashboard `.env.keys` file is not needed. Do not share resolved Compose configuration: it may contain injected secrets.

`env/base.env` provides common values; the strategy/environment file supplies overrides. `STRATEGY` and `ENV` on the deployment command select the files and YAML. Do not put conflicting selector values in the environment files.

## 2. Build and start

The repository includes `conf/prod/listing_volume_short.yml`. It **trades live** on the sub-account whose keys are in `prod.env`.

```bash
uv build
STRATEGY=listing_volume_short ENV=prod podman-compose up -d --build --force-recreate --no-cache app
```

Your old strategy command remains the same:

```bash
uv build
STRATEGY=dumb_rsi ENV=prod podman-compose up -d --build --force-recreate --no-cache app
```

Use the configuration for the strategy you intend to run. **Do not switch the `app` service to another strategy while the listing bot owns live positions.** Recreating the container replaces its worker; it does not close positions on the exchange. Do not scale the worker or run another Compose project against the same live account.

Run `podman-compose` directly, not through `uv run`: inside `uv run` it would start with the project's Python, which does not have it. Install it once as its own isolated tool with `uv tool install podman-compose` (add `--force` to replace a copy installed with pip, which breaks when Bazzite updates its system Python). It is not a Python runtime dependency of the bot. No host Python dependencies need to be layered with `rpm-ostree` or installed through host `dnf`.

The Dockerfile installs the wheel built by `uv build`, pins Python dependencies from `uv.lock`, checks the installed dependency set, and copies `conf/` into the image. It rejects multiple wheels instead of accidentally installing an old release. Use `uv build --clear` to replace stale distribution artifacts when needed. After changing YAML, rebuild/recreate using the same commands. `.dockerignore` keeps credentials, local state and research data out of the build context. The optional [Quadlet guide](linux_bazzite_quadlet.md) remains an alternative service manager, not a prerequisite.

### Preflight before the first start

```bash
uv build --clear
STRATEGY=listing_volume_short ENV=prod podman-compose build --no-cache app
STRATEGY=listing_volume_short ENV=prod podman-compose run --rm --no-deps app --files conf/prod/listing_volume_short.yml --check-config
STRATEGY=listing_volume_short ENV=prod podman-compose up -d --force-recreate app
```

`--check-config` validates settings without entering this strategy, initializing
its state or connecting to BingX. Start before a listing decision: several polls
are needed to bootstrap the 30-listing reference, so a lack of trades during warmup
is expected. Verify discovered listings, available history and successful poll
summaries, and that state survives a planned stop/start.

## 3. What the Compose setup handles

| Item | Behavior |
|---|---|
| Configuration | `conf/${ENV}/${STRATEGY}.yml`, resolved by Compose |
| Credentials | `env/base.env`, then `env/${STRATEGY}/${ENV}.env` |
| Container selector | The chosen `STRATEGY` is passed into the worker |
| Environment directory | `/app/env`, selected by `OTOMAI_ENV_DIR`; injected process values win |
| Entry timing | Four closed hours, then the current quote within 120 seconds |
| Persistent data | Host `./data` is mounted at `/app/data` |
| Listing state | `/app/data/listing_volume_short.live.sqlite` |
| Restart | `unless-stopped` for process exits |
| Stop | `SIGINT`, with up to five minutes to finish bookkeeping |
| SELinux | Dedicated data mount uses `:z`; environment mount is read-only with `:Z` |

The shared `:z` data label permits the existing dashboard's read-only mount. Do not mount all of your home directory or disable SELinux. The configuration's state file must remain under `/app/data` to survive container replacement. Use a local filesystem with SQLite locking; do not place live state on SMB/NFS.

One state path has one process owner. Rebuilding the image must preserve the host `data/` directory. Never delete it to retry an uncertain order.

## 4. Check it through Cockpit or the terminal

In Cockpit, view containers belonging to the same rootless user. Use the terminal commands below if its UI does not expose the Compose controls you need:

```bash
STRATEGY=listing_volume_short ENV=prod podman-compose ps
STRATEGY=listing_volume_short ENV=prod podman-compose logs -f app
```

The first cycles can have no signals while references bootstrap. Look for **successful recent cycle summaries**, not just a running container. The worker catches cycle failures and can remain running while exchange polling fails. There is currently no external heartbeat alert or HTTP health endpoint.

The installed CLI reads its mounted environment directory through `OTOMAI_ENV_DIR=/app/env`. Strategy-file values override common-file values; explicitly injected process variables take precedence. Optional missing files do not require baking credentials into an image.

Open [your existing Cockpit endpoint](https://cockpit.otomai.fr), then its Podman page. The reported bad-Origin error for `https://cockpit.otomai.fr` was already resolved; retain the accepted-origin setting. Do not replace your Cockpit configuration with a generic example. No additional public hostname or port is needed for the bot. Cloudflare management access does not determine the server's exchange egress IP.

Check the **existing tunnel** independently from the worker, from the host session belonging to `thomasclem`:

```bash
id -un
systemctl --user status cloudflared-cockpit.service
systemctl --user is-enabled cloudflared-cockpit.service
systemctl --user show cloudflared-cockpit.service -p Restart -p ActiveState
journalctl --user -u cloudflared-cockpit.service -n 100 --no-pager
loginctl show-user thomasclem -p Linger
ss -lntp 'sport = :9090'
```

These are diagnostic commands, not changes to the tunnel. A running tunnel does not prove that the Cockpit origin, Access login, WebSocket terminal and Podman page all work: check each through your normal remote browser. The earlier four registered Paris-edge connections demonstrated connector connectivity at that time. The earlier 0.091-second local and 0.046-second public curl results measured initial responses, potentially including an Access response; they did not measure authenticated page loading.

### Remaining access checks from the earlier setup

| Check | Current evidence / next verification |
|---|---|
| MFA | An Access-granted event confirms an allowed login, not a separate authenticator challenge. Verify the actual Access policy and identity-provider MFA requirement with a fresh session. Email OTP alone does not demonstrate a second factor. |
| OTP delivery | Recent missing messages were unresolved. Check the configured allowed identities/login methods and Access logs, then test with an allowed address; an arbitrary new address need not be eligible. |
| Persistence | The last status was running, but enablement, restart policy and `Linger=yes` still need checking. Test logout and a planned reboot while the bot holds no position. |
| Direct origin exposure | Earlier `*:9090` meant a wildcard listener. Inspect host firewall and router forwarding; it does not itself prove public reachability. Confirm that remote users cannot bypass Access by reaching port 9090 directly. |

If you later restrict Cockpit to loopback, use its systemd socket configuration and retain a recovery path; do not make that access change as part of the bot deploy. Ensure whichever IPv4/IPv6 loopback address `localhost` resolves to still reaches Cockpit. If you retain a forwarded-protocol header setting, trust it only from the intended proxy path. [Cockpit configuration](https://docs.cockpit-project.org/cockpit-guide/main/man/cockpit.conf.5.html).

Keep Cockpit's own login as well as the Cloudflare Access policy. Verify MFA and OTP delivery separately rather than treating the earlier successful login as evidence both are enforced. [Cloudflare OTP documentation](https://developers.cloudflare.com/cloudflare-one/integrations/identity-providers/one-time-pin/), [Access application types](https://developers.cloudflare.com/cloudflare-one/access-controls/applications/choose-application-type/).

## 5. Restore after host reboot

Detached mode handles closing the terminal; a reboot also needs Podman's boot restart integration. Your existing tunnel's user service and the worker need independent checks; enabling one does not establish the other. Check the Podman user unit on Bazzite:

```bash
systemctl --user cat podman-restart.service
sudo loginctl enable-linger "$(id -un)"
systemctl --user enable podman-restart.service
```

Use the final command only if the preceding `cat` confirms that the user unit exists. It restores eligible restart-policy containers for **this user**, not only Otomai. Do not substitute the root system unit for a rootless deployment. If your installed version lacks the user unit, use the optional [Quadlet setup](linux_bazzite_quadlet.md) for explicit boot management; do not have Compose and Quadlet start separate workers for the same account.

Podman's `unless-stopped` boot behavior varies across versions, so test logout and a planned reboot **while the bot holds no position**, then confirm that polling resumes. See [Podman's restart policy reference](https://docs.podman.io/en/latest/markdown/podman-run.1.html). Keep host time synchronized and disable automatic desktop sleep. A host waiting for disk unlock after power loss cannot restart the worker unattended.

## 6. Stop, back up and update

```bash
STRATEGY=listing_volume_short ENV=prod podman-compose stop app

umask 077
backup_file="../otomai-state-$(date -u +%Y%m%dT%H%M%SZ).tar.gz"
tar -czf "$backup_file" data conf docker-compose.yml

STRATEGY=listing_volume_short ENV=prod podman-compose start app
```

Back up credentials separately with encryption. Copy backups off the server. Stop before copying the entire SQLite data directory, including sidecars. In live operation, first plan the interruption and verify protection: stopping does not close positions, and local deadline exits do not run while stopped.

For updates, take the backup, deploy the intended checkout, then run your original build/start commands. Keep the same host data path. If rolling back code, retain the **current** state where the older version supports its schema. Restoring an old live database can lose knowledge of orders already submitted; reconcile against the exchange before doing that.

## 7. Live trading

The configuration trades live from the first start. Use a dedicated one-way BingX
sub-account per strategy and environment, isolated margin and 1× leverage, with
exactly one worker.

Known engineering limits remain: no explicit fee reserve, batch-level account snapshots rather than fresh checks before every POST, and no account-wide coordination across bots. Container deployment does not remove those limits. An entry marked `uncertain` requires reconciliation, not resetting state or launching another worker.

See the [strategy operations guide](../strategies/listing_volume_short.md) for protection, deadlines and recovery semantics. Bazzite's recommended optional systemd integration is documented in its [Quadlet guide](https://docs.bazzite.gg/Installing_and_Managing_Software/Quadlet/).

## Validation limits

The Compose app selectors, YAML configurations and Markdown shell syntax were checked locally. The Cockpit/tunnel details above come from your supplied setup summary; their current live status was not checked remotely. Podman image build, server connectivity, reboot recovery and the Cockpit bridge must still be verified on your Bazzite host. This guide does not start containers or submit orders by itself.
