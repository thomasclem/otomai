# Recreate the Bazzite server's Cockpit and Cloudflare access

Use this runbook after installing Bazzite on a new server. It rebuilds the management access used for Otomai; deploying the trading worker is a separate final step.

**Reference values:** Linux user `thomasclem`, domain `otomai.fr`, public hostname `cockpit.otomai.fr`, tunnel name `cockpit`, and systemd user service `cloudflared-cockpit.service`. Substitute your new username or domain where necessary. Commands run on the **Bazzite host**, not in Distrobox. No commands in this document were run on your server while writing it.

## Target architecture

```text
Remote browser
  → https://cockpit.otomai.fr
  → Cloudflare Access: allowed identity + configured MFA
  → encrypted Cloudflare Tunnel
  → cloudflared on the Bazzite host (user service)
  → http://127.0.0.1:9090
  → Cockpit login → host administration / rootless Podman
```

Your previous origin was `http://localhost:9090`. This clean-install example uses explicit IPv4 loopback to match its restricted listener and avoid IPv4/IPv6 resolution ambiguity. Public HTTPS and tunnel encryption remain in place; only the host-local hop uses HTTP.

| Component | Installation / persistence |
|---|---|
| Cockpit web service and Podman plugin | Host RPMs, integrated with Bazzite's system services |
| Cockpit listener | System `cockpit.socket`, restricted to `127.0.0.1:9090` |
| Cockpit proxy settings | `/etc/cockpit/cockpit.conf` |
| Tunnel executable | `~/.local/bin/cloudflared` |
| Tunnel configuration / credentials | `~/.cloudflared/config.yml` and `<UUID>.json` |
| Tunnel service | `~/.config/systemd/user/cloudflared-cockpit.service` |
| Boot without interactive login | User lingering, plus enabled tunnel service |
| Bot | Separate rootless Podman/Compose worker, not part of the tunnel service |

## 1. Establish local recovery access first

Finish the Bazzite installation, create your normal administrator account, connect the network and confirm you can log in locally. Keep a local console or an already-working independent host-access route until the entire rebuild is tested. Do not make your first successful tunnel session the only way to repair it.

```bash
cat /etc/os-release
id -un
id -nG
printf 'Home: %s\n' "$HOME"
podman --version
timedatectl status
```

Use the same non-root user for the tunnel and the intended rootless Podman deployment. A fresh server may have a different UID or home directory; Bazzite may resolve `/home` through `/var/home`. Generate paths from the new host instead of restoring old absolute paths blindly. Ensure time synchronization, reliable power/network, and disabled automatic sleep. An encrypted disk that requires a manual unlock still needs that unlock after a cold boot.

## 2. Install Cockpit and its Podman page

Check what the selected Bazzite image already contains:

```bash
rpm -q cockpit-ws cockpit-system cockpit-podman
systemctl cat cockpit.socket
```

If Cockpit and its Podman plugin are missing, layer the needed host packages and reboot:

```bash
sudo rpm-ostree install cockpit cockpit-podman
sudo systemctl reboot
```

Run the install only for packages not already supplied/requested by the image. If a package cannot be resolved on your Bazzite release, check its current supported host-package route before proceeding. Do not install Cockpit inside Distrobox and expect it to administer the host.

This is a deliberate system-integration use of package layering. Keep the bot's Python dependencies in its container. [Bazzite package layering](https://docs.bazzite.gg/Installing_and_Managing_Software/rpm-ostree/), [Cockpit installation](https://cockpit-project.org/running).

After reboot, confirm `cockpit.socket` exists before continuing. Cockpit is socket-activated: the listener is the unit you enable; `cockpit.service` can be inactive when nobody is using it.

## 3. Configure a loopback-only Cockpit listener

On the fresh server, before publishing any tunnel route:

```bash
sudo install -d -m 755 /etc/systemd/system/cockpit.socket.d
sudo tee /etc/systemd/system/cockpit.socket.d/listen.conf >/dev/null <<'UNIT'
[Socket]
ListenStream=
ListenStream=127.0.0.1:9090
UNIT

sudo install -d -m 755 /etc/cockpit
sudo tee /etc/cockpit/cockpit.conf >/dev/null <<'INI'
[WebService]
Origins = https://cockpit.otomai.fr http://127.0.0.1:9090 http://localhost:9090
ProtocolHeader = X-Forwarded-Proto
INI

sudo systemctl daemon-reload
sudo systemctl enable --now cockpit.socket
```

These file-creation commands assume a fresh installation. On a restored host, back up and **merge** existing settings instead of replacing them. The empty `ListenStream=` clears Cockpit's default wildcard listener. Port 9090 stays unchanged, so no custom SELinux port label is needed. Do not disable SELinux or add a public firewall opening for Cockpit. [Cockpit socket configuration](https://docs.cockpit-project.org/cockpit-guide/main/guide/listen.html).

The public origin prevents the earlier `received request from bad Origin: https://cockpit.otomai.fr` failure. `ProtocolHeader` trusts the forwarded scheme from the intended local proxy; the loopback-only listener prevents a remote direct request from supplying that header. Other local processes remain inside that trust boundary. Cockpit permits localhost HTTP without globally enabling `AllowUnencrypted`. [Cockpit proxy settings](https://docs.cockpit-project.org/cockpit-guide/main/man/cockpit.conf.5.html), [localhost HTTP behavior](https://docs.cockpit-project.org/cockpit-guide/main/guide/https.html).

Verify on the host:

```bash
systemctl status cockpit.socket --no-pager
ss -lntp 'sport = :9090'
curl --fail --silent --show-error http://127.0.0.1:9090/ping
```

Expect a listener on **127.0.0.1:9090**, not `*:9090`, `0.0.0.0:9090` or `[::]:9090`. For a local browser test, open `http://127.0.0.1:9090` on the server itself. Use the normal Linux account to log in; a root login or disabling authentication is unnecessary.

If you already started Cockpit before creating the socket drop-in, apply it from your local/recovery session: stop `cockpit.service`, restart `cockpit.socket`, then repeat the listener check. This interrupts any existing Cockpit session.

For explicit rootless Podman API socket activation under the same user:

```bash
systemctl --user enable --now podman.socket
systemctl --user status podman.socket --no-pager
podman info --format '{{.Host.Security.Rootless}}'
```

The socket is local Unix IPC, normally under `/run/user/<UID>/podman/podman.sock`. It is not a public TCP service and needs no Cloudflare route. Podman's service can become inactive between calls while its socket stays active. [Podman socket activation](https://docs.podman.io/en/latest/markdown/podman-system-service.1.html).

## 4. Prepare the domain and Access policy

Keep `otomai.fr` registered at IONOS. If reusing the existing Cloudflare account and active zone, there is no need to change nameservers again. For a completely new zone, add the domain to Cloudflare, preserve existing DNS records—especially mail records—and set IONOS to the nameservers Cloudflare assigns. Wait for the zone to become active before routing the hostname. Do not replace working DNS with an empty zone.

Create the Access application **before connecting the public hostname to a running origin**:

1. In Cloudflare Zero Trust, open **Access controls → Applications** and create a self-hosted application with public hostname `cockpit.otomai.fr`. Protect the whole hostname, without a path restriction.
2. Add an **Allow** policy limited to your intended administrator email addresses. Do not use an Everyone or Bypass policy.
3. Choose its login method. To reproduce email codes, explicitly add **One-time PIN** under **Integrations → Identity providers** and select it for the application. New accounts may default to the Cloudflare identity provider instead.
4. Choose a session duration, for example one hour, and save the application and policy.

[Access application setup](https://developers.cloudflare.com/cloudflare-one/access-controls/applications/http-apps/self-hosted-public-app/), [OTP login configuration](https://developers.cloudflare.com/cloudflare-one/integrations/identity-providers/one-time-pin/).

### Make MFA an explicit setting

Email OTP is the initial login method; receiving a code is not proof of an independent second factor. To enforce an authenticator challenge directly through Access:

1. Under **Access controls → Access settings**, enable independent MFA methods, such as a TOTP authenticator or a browser-supported security key, and choose its authentication duration.
2. Apply the MFA requirement to the Cockpit application/policy, using its MFA settings or the selected global defaults. Organization-level availability alone does not establish that this application requires MFA.
3. Enroll the required authenticator through the Access enrollment flow/App Launcher. Store recovery information separately from the server.
4. Test a fresh login without a reusable MFA session and confirm the challenge occurs before Cockpit. A valid cached MFA session can legitimately avoid another prompt.

Use the settings available in your account; UI labels and availability can change. If your chosen configuration cannot enforce the intended second factor, use an appropriately configured MFA-capable identity provider rather than assuming email OTP provides it. Cockpit's own Linux login remains a separate authentication layer. [Independent MFA configuration](https://developers.cloudflare.com/cloudflare-one/access-controls/access-settings/independent-mfa/).

## 5. Install the host `cloudflared` binary

Reproduce your previous user-local installation instead of relying on a Bazzite RPM for this tool. Download from Cloudflare's official GitHub release assets:

```bash
install -d -m 700 "$HOME/.local/bin" "$HOME/.cloudflared"

case "$(uname -m)" in
  x86_64) cloudflared_arch=amd64 ;;
  aarch64|arm64) cloudflared_arch=arm64 ;;
  *) echo 'Check the official download for this architecture.' >&2; exit 1 ;;
esac

cloudflared_download="$(mktemp)"
curl --fail --location --retry 3 \
  "https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-${cloudflared_arch}" \
  --output "$cloudflared_download"
install -m 700 "$cloudflared_download" "$HOME/.local/bin/cloudflared"
rm "$cloudflared_download"
"$HOME/.local/bin/cloudflared" --version
```

Record the installed version for future rebuilds. For a pinned release, use its official versioned asset URL instead of `latest`; keep the binary supported and maintain it through planned updates. [Official cloudflared downloads](https://developers.cloudflare.com/tunnel/downloads/).

## 6. Restore an existing tunnel OR create a replacement

Your previous tunnel UUID was `30d6d1ac-ceae-42f0-8696-422af25842ab`. That value is historical: a newly created tunnel gets a different UUID. **Choose one path below.**

### A. Restore the existing tunnel

Use this when it still exists in the same Cloudflare account and you have its credentials JSON in an encrypted backup:

- Restore that JSON into `~/.cloudflared/` on the new host, owner-readable only.
- Keep the same tunnel UUID and existing DNS route.
- Regenerate the local config in section 7 so its credentials path matches the new host.
- Stop the retired connector during the planned cutover. Two connectors for one tunnel can both receive requests; an old origin must not keep serving unexpectedly.

The JSON lets a process run that tunnel; possession of its UUID alone does not. You do not need the account-wide `cert.pem` merely to run a restored tunnel. If you cannot restore valid tunnel credentials, use path B; do not invent a credentials file. [Tunnel credential scopes](https://developers.cloudflare.com/tunnel/features/locally-managed-tunnels/tunnel-permissions/).

### B. Create a new tunnel

```bash
"$HOME/.local/bin/cloudflared" tunnel login

cockpit_tunnel_name=cockpit
"$HOME/.local/bin/cloudflared" tunnel create "$cockpit_tunnel_name"
"$HOME/.local/bin/cloudflared" tunnel list
```

Open the login URL in your trusted browser, authorize the correct account/zone, and let the command finish on the server. It creates an account management certificate; tunnel creation produces a separate tunnel-specific JSON.

If `cockpit` already exists and you are replacing it, choose an unused name such as `cockpit-rebuild` **before** the create command. Do not delete the old tunnel until the replacement is verified. Record the newly returned UUID and credentials path. [Locally managed tunnel creation](https://developers.cloudflare.com/tunnel/features/locally-managed-tunnels/create-local-tunnel/).

## 7. Write and validate the local tunnel configuration

Use the UUID from your selected restore/create path:

```bash
read -r -p 'Cockpit tunnel UUID: ' cockpit_tunnel_id

test -f "$HOME/.cloudflared/${cockpit_tunnel_id}.json" || {
  echo 'Tunnel credentials JSON not found; check the selected UUID and restore/create step.' >&2
  exit 1
}

umask 077
cat > "$HOME/.cloudflared/config.yml" <<YAML
tunnel: ${cockpit_tunnel_id}
credentials-file: ${HOME}/.cloudflared/${cockpit_tunnel_id}.json

ingress:
  - hostname: cockpit.otomai.fr
    service: http://127.0.0.1:9090
  - service: http_status:404
YAML

chmod 600 "$HOME/.cloudflared/config.yml" \
  "$HOME/.cloudflared/${cockpit_tunnel_id}.json"

"$HOME/.local/bin/cloudflared" tunnel --config "$HOME/.cloudflared/config.yml" ingress validate
"$HOME/.local/bin/cloudflared" tunnel --config "$HOME/.cloudflared/config.yml" ingress rule https://cockpit.otomai.fr
```

Expect the hostname to match the Cockpit ingress rule. The final catch-all denies unmatched hostnames. No local certificate, `noTLSVerify`, new router port-forward or global `AllowUnencrypted` setting is needed for this loopback HTTP origin. The connector needs outbound connectivity, including Cloudflare Tunnel's required port 7844; do not open inbound Cockpit ports. [Ingress configuration and validation](https://developers.cloudflare.com/tunnel/features/locally-managed-tunnels/configuration-file/), [tunnel connectivity prerequisites](https://developers.cloudflare.com/tunnel/get-started/).

For a **new** tunnel, create its DNS route after the Access application is saved:

```bash
"$HOME/.local/bin/cloudflared" tunnel route dns "$cockpit_tunnel_id" cockpit.otomai.fr
```

If replacing an old route, this may report that the DNS record already exists. Deliberately replace only the old `cockpit` record with the new tunnel's CNAME target, `<NEW-UUID>.cfargotunnel.com`, in Cloudflare DNS; keep it proxied. Do not change unrelated records. A restored tunnel with its original DNS route needs no replacement. The route command requires management credentials such as the `cert.pem` generated by login; runtime needs only the tunnel JSON.

## 8. Create the persistent user service

Create `~/.config/systemd/user/cloudflared-cockpit.service`:

```bash
install -d -m 700 "$HOME/.config/systemd/user"
cat > "$HOME/.config/systemd/user/cloudflared-cockpit.service" <<'UNIT'
[Unit]
Description=Cloudflare Tunnel for Cockpit

[Service]
Type=simple
ExecStart=%h/.local/bin/cloudflared tunnel --no-autoupdate --config %h/.cloudflared/config.yml run
Restart=always
RestartSec=5
TimeoutStopSec=30
UMask=0077
NoNewPrivileges=true

[Install]
WantedBy=default.target
UNIT

systemctl --user daemon-reload
sudo loginctl enable-linger "$(id -un)"
systemctl --user enable --now cloudflared-cockpit.service
systemctl --user status cloudflared-cockpit.service --no-pager
journalctl --user -u cloudflared-cockpit.service -n 100 --no-pager
```

This is a regular user service, so `enable` is correct. It is separate from generated Quadlet units. `%h` expands to the owning user's home. Start it from a normal host login where `systemctl --user` works; if the user bus is unavailable through an administrative shell, log in as that user rather than enabling an unrelated root service.

`--no-autoupdate` makes executable updates a planned maintenance action instead of an in-process replacement. Use the official binary download process to update, then restart the service. The connector reconnects if the network is not ready yet. A system-level `network-online.target` is not a reliable dependency inside a user manager. [cloudflared run parameters](https://developers.cloudflare.com/cloudflare-one/networks/connectors/cloudflare-tunnel/configure-tunnels/run-parameters/).

Do not also run `cloudflared tunnel run` manually in another terminal or install a second `cloudflared.service` for the same purpose. Expected logs contain registered tunnel connections; a particular edge city or exactly four connections is not a requirement for acceptance.

## 9. Verify the complete access path

From outside your home network, for example with a phone on mobile data:

1. Open `https://cockpit.otomai.fr` in a fresh browser session. Verify Access authentication and the intended MFA behavior.
2. Confirm an unapproved identity cannot reach Cockpit. Then log in with the intended Linux account.
3. Open Cockpit's terminal and `/podman` page. Check that the browser stays connected; this exercises WebSockets, not just the first HTTP response.
4. In the terminal, compare `id -un` and `podman ps` with the user shown in the Podman view. Rootless containers belong to their owner; `sudo podman ps` is a different store.
5. Confirm the server's LAN/public address on port 9090 does not provide an alternate path around Access. The configured loopback listener should make direct remote connections impossible; also remove any old router forwarding for 9090.

On the server:

```bash
systemctl is-enabled cockpit.socket
systemctl --user is-enabled podman.socket
systemctl --user is-enabled cloudflared-cockpit.service
systemctl --user show cloudflared-cockpit.service -p Restart -p ActiveState
loginctl show-user "$(id -un)" -p Linger
ss -lntp 'sport = :9090'
```

Expected: Cockpit socket enabled, tunnel enabled/active, restart `always`, lingering `yes`, and loopback-only port 9090. Log out and retest. During a planned maintenance window, reboot and verify remote access again before calling the rebuild complete. A running connector or a fast `curl` response does not prove Access, MFA and the full Cockpit session work.

## 10. Diagnose the earlier failure modes

| Symptom | Where to look |
|---|---|
| `bad Origin` / terminal disconnect | Exact `https://cockpit.otomai.fr` in Cockpit `Origins`; preserve the trusted proxy scheme header. Check `journalctl -u cockpit.service` and browser WebSocket errors. |
| Redirect loop | Origin must remain `http://127.0.0.1:9090` for this design. Do not route the tunnel back to its own public hostname. |
| Cloudflare 502 | Check local `/ping`, listener address and connector logs; healthy tunnel connections do not prove the origin works. |
| Origin TLS handshake error | You likely selected `https://...` for the local hop; this runbook uses loopback HTTP. Do not add `noTLSVerify` to mask an accidental protocol change. |
| Access login has no new log entry | Email submission alone does not necessarily create an authentication log entry; Cloudflare records OTP authentication after code submission. |
| OTP email missing | Confirm the email is allowed and OTP is selected; inspect spam/mail filtering for `noreply@notify.cloudflare.com`. The UI can say a code was sent even when the identity is blocked. |
| OTP says already used | Request a fresh code; mail link scanning can consume it. New requests invalidate older codes. |
| MFA never requested | Verify application/policy enforcement, enrollment and session duration; repeat without a cached MFA session. |
| Everything stops after logout | Check user lingering and that the tunnel was enabled under the intended user. |
| Podman page empty | Verify `cockpit-podman` is installed and select the correct user's container store. |
| New server refuses tunnel name | An old tunnel still owns it; restore its JSON or create a replacement name, then deliberately update DNS. |

The OTP-specific behavior is documented in [Cloudflare's OTP guide](https://developers.cloudflare.com/cloudflare-one/integrations/identity-providers/one-time-pin/); it explains why the earlier missing emails and absent log events did not establish a working authentication flow.

Useful read-only diagnostics:

```bash
journalctl --user -u cloudflared-cockpit.service -f
journalctl -u cockpit.service -n 100 --no-pager
curl --silent --show-error --output /dev/null \
  --write-out 'Local HTTP %{http_code}, %{time_total}s\n' http://127.0.0.1:9090/
curl --silent --show-error --output /dev/null \
  --write-out 'Public HTTP %{http_code}, %{time_total}s\n' https://cockpit.otomai.fr/
```

A public login redirect is not a performance test of the authenticated dashboard. Cloudflare outage or tunnel failure affects management access; it must not stop an already-running bot with working exchange connectivity.

## 11. Preserve the rebuild material

Keep an encrypted off-server backup of the tunnel JSON, config, user service, Cockpit configuration/socket drop-in, Access policies/MFA settings, relevant DNS records and binary version. The account `cert.pem` is more powerful than the tunnel JSON: it can manage tunnels and is not required for day-to-day runtime. Protect or remove it from the runtime host according to your recovery plan; keep a secure management route available for future changes.

Record which tunnel UUID is current, which machine owns the active connector, and how to recover Access if your authenticator or email is unavailable. Credentials copied from the old server remain credentials on that server; retire the old connector and rotate/recreate credentials if its trust is uncertain. Never commit JSON credentials, `cert.pem`, authenticator enrollment material or tokens into the Otomai repository.

When management access is stable, deploy Otomai using the separate [Bazzite Compose deployment guide](linux_bazzite_podman.md). Its normal command remains:

```bash
uv build
STRATEGY=listing_volume_short ENV=prod uv run podman-compose up -d --build --force-recreate --no-cache app
```

The tunnel, Cockpit socket and trading worker each have their own restart/persistence requirements. Recreating management access does not restore a lost trading database or reconcile exchange orders.

## Validation of this document

Official Bazzite, Cockpit and Cloudflare sources were checked when writing this runbook. Shell syntax, embedded YAML and INI structure were checked locally; systemd semantics were checked against documentation rather than executed on this macOS machine. Package availability, account settings, tunnel creation, external authentication and reboot recovery still require execution and verification on the fresh host. The existing server was not modified.
