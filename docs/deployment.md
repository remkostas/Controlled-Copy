# Deployment

One small Linux server with Docker, the app container and Caddy in front of it. Caddy obtains the TLS certificate; the app is reachable only through Caddy on an internal network.

## 1. Server

- A current Ubuntu LTS (or Debian) server with 2 vCPU and 4 GB RAM is enough.
- Firewall: inbound TCP 22, 80 and 443 only (cloud firewall and `ufw`).
- SSH with keys only, no root login, no password authentication; `fail2ban` and `unattended-upgrades` on.
- Docker Engine with the Compose plugin. A dedicated deploy user in the `docker` group (that group is root-equivalent, so use a single-purpose server).

## 2. DNS

An `A` record for the site name pointing at the server, not proxied, so Caddy can complete the ACME challenge. No `AAAA` record: Caddy publishes on IPv4 only, and an IPv6 address would send the certificate check and IPv6 visitors to a closed port.

## 3. Code and settings

```
git clone <repository URL> controlled-copy && cd controlled-copy
cp .env.example .env && chmod 600 .env
python3 -c "import secrets; print(secrets.token_urlsafe(48))"   # for APP_SECRET_KEY
```

Set at least these values in `.env`:

| Variable | Value |
| :--- | :--- |
| `OPENROUTER_API_KEY` | A key with a credit limit and privacy settings that deny training |
| `APP_ACCESS_CODE` | 12 or more characters (deploy mode refuses shorter ones); what visitors type |
| `APP_SECRET_KEY` | The 64 characters printed above |
| `SITE_ADDRESS` | The site name, for example `demo.example.org` |
| `PUBLISH_ADDRESS` | `0.0.0.0` |
| `FEATURE_GOVERNANCE` | `true` for the governed-documents layer (Stage 2) |
| `FEATURE_MODEL_PICKER` | `true` for the model picker (Stage 3; ignored before that layer is merged) |

Compose runs the app in deploy mode unless `.env` sets `APP_MODE` (leave it out on a server). In deploy mode the app refuses to start without an access code of at least 12 characters and a secret key of at least 32, with debug on, or with the fake model provider.

## 4. Start

```
docker compose pull --ignore-buildable
docker compose build --pull
docker compose up -d --wait
docker compose images
curl -fsS https://<site>/healthz
```

Expected: both containers running, the app `healthy`, and `{"status":"ok"}` from the health check (`-f` makes curl fail loudly on any error status). `pull --ignore-buildable` fetches the newest Caddy image; `build --pull` rebuilds the app on the newest Python base; `docker compose images` records which images now run. If the certificate fails, check the DNS record (not proxied) and then `docker compose restart caddy`.

## 5. Checks after the first start

```
sudo ufw status verbose
sudo ss -tlnp
sudo sshd -T | grep -E "^(passwordauthentication|permitrootlogin)"
docker compose ps --format "{{.Name}} {{.Ports}}"
for image in controlled-copy:latest caddy:2.11; do
  docker save "$image" -o /tmp/scan.tar
  docker run --rm -v /tmp/scan.tar:/image.tar:ro aquasec/trivy:0.75.0@sha256:af6acf9a6b85dfe389a1941505c0ce9efef52a4719635e1a962f022a3d855daa image --input /image.tar --scanners vuln --severity HIGH,CRITICAL --ignore-unfixed --exit-code 1 && echo "$image: clean"
  rm /tmp/scan.tar
done
```

Expected: only 22, 80 and 443 open; password and root login off; only Caddy publishes ports; both images clean (no fixable HIGH or CRITICAL findings). The scanner is pinned by digest (the same Trivy version as CI) and reads saved copies of the images actually running here, so it never gets the Docker socket.

Then run the live checks from any machine with the development dependencies installed:

```
LIVE_URL=https://<site> LIVE_ACCESS_CODE='<code>' python -m pytest -m smoke_live tests/live -v
```

TC-LIVE-001 checks health, headers, TLS and the HTTP redirect without model calls; TC-LIVE-002 drives both journeys with the real model (a few cents).

## 6. Operating it

- **Update:** `git pull && docker compose pull --ignore-buildable && docker compose build --pull && docker compose up -d --wait`, then the image scan from section 5. Do it at least monthly so Caddy, the Python base and the Debian packages pick up security fixes (a plain `build --pull` refreshes only the app's base, not Caddy).
- **Uptime:** an external monitor (any uptime service) on `https://<site>/healthz`. Compose restarts a container that exits, not one that is up but unhealthy, so the monitor is what tells you.
- **Logs:** `docker compose logs --tail 100 app`. Logs are content-free (event names, hashed session IDs, route templates, sizes, durations); the app server keeps no access log, so no URLs or client addresses; Caddy writes no access log either. Docker keeps at most 30 MB per container.
- **Storage:** raw uploads are limited per visitor and in total (`MAX_VISITOR_UPLOAD_MB`, `MAX_TOTAL_UPLOAD_MB`), and nothing is accepted when the volume has less than `MIN_FREE_DISK_MB` free; viewing keeps working.
- **Deletion:** a deleted source is gone from every table and search index at once; its bytes leave the database file at the next completed checkpoint, which runs after each deletion and in the hourly purge (another visitor's long read can delay it).
- **Data:** the SQLite database and uploads live in the `app-data` volume. Sessions not seen for `RETENTION_HOURS` (default 7 days) are purged hourly with everything in them. The demo holds synthetic data only, so there is no backup; for real data, back up the volume and keep the backup inside the same retention promise.
- **Costs:** model calls are limited per visitor per hour and per day (`MODEL_CALLS_PER_VISITOR_HOUR`, `MODEL_CALLS_PER_DAY`), the day is also limited in dollars (`MAX_USD_PER_DAY`, default 5: every call reserves a conservative amount when it starts and settles to the cost OpenRouter reports; failed, timed-out and embedding calls keep their reservation), and no request routes to an endpoint above `MAX_PRICE_PROMPT_PER_MILLION` / `MAX_PRICE_COMPLETION_PER_MILLION`. The credit limit on the OpenRouter key is the last stop, not the first. Larger models in `MODEL_CHOICES` (model picker) cost more per call.
- **Remove everything:** `docker compose down -v`, then revoke the OpenRouter key.
