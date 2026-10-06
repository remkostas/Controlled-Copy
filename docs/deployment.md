# Deployment

One small Linux server with Docker, the app container and Caddy in front of it. Caddy obtains the TLS certificate; the app is reachable only through Caddy on an internal network.

## 1. Server

- A current Ubuntu LTS (or Debian) server with 2 vCPU and 4 GB RAM is enough.
- Firewall: inbound TCP 22, 80 and 443 only (cloud firewall and `ufw`).
- SSH with keys only, no root login, no password authentication; `fail2ban` and `unattended-upgrades` on.
- Docker Engine with the Compose plugin. A dedicated deploy user in the `docker` group (that group is root-equivalent, so use a single-purpose server).

## 2. DNS

An `A` record for the site name pointing at the server, not proxied, so Caddy can complete the ACME challenge.

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
| `APP_ACCESS_CODE` | 12 or more characters; what visitors type |
| `APP_SECRET_KEY` | The 64 characters printed above |
| `APP_MODE` | `deploy` (Compose reads it from `.env`; the example says `local`) |
| `SITE_ADDRESS` | The site name, for example `demo.example.org` |
| `PUBLISH_ADDRESS` | `0.0.0.0` |
| `FEATURE_GOVERNANCE`, `FEATURE_MODEL_PICKER` | `true` to switch the optional layers on |

In deploy mode the app refuses to start without a strong access code and secret key, with debug on, or with the fake model provider.

## 4. Start

```
docker compose build --pull
docker compose up -d --wait
docker compose ps
curl -sI https://<site>/healthz | head -1
```

Expected: both containers running, the app `healthy`, `HTTP/2 200`. If the certificate fails, check the DNS record (not proxied) and then `docker compose restart caddy`.

## 5. Checks after the first start

```
sudo ufw status verbose
sudo ss -tlnp
sudo sshd -T | grep -E "^(passwordauthentication|permitrootlogin)"
docker compose ps --format "{{.Name}} {{.Ports}}"
docker run --rm -v /var/run/docker.sock:/var/run/docker.sock aquasec/trivy:latest image --scanners vuln --severity HIGH,CRITICAL --ignore-unfixed controlled-copy:latest
```

Expected: only 22, 80 and 443 open; password and root login off; only Caddy publishes ports; no fixable HIGH or CRITICAL findings.

Then run the live checks from any machine with the development dependencies installed:

```
LIVE_URL=https://<site> LIVE_ACCESS_CODE='<code>' python -m pytest -m smoke_live tests/live -v
```

TC-LIVE-001 checks health, headers, TLS and the HTTP redirect without model calls; TC-LIVE-002 drives both journeys with the real model (a few cents).

## 6. Operating it

- **Update:** `git pull && docker compose build --pull && docker compose up -d --wait`. Rebuild at least monthly so the base images and Debian packages pick up security fixes.
- **Logs:** `docker compose logs --tail 100 app`. Logs are content-free (IDs, sizes, durations); Docker keeps at most 30 MB per container.
- **Data:** the SQLite database and uploads live in the `app-data` volume. Sessions not seen for `RETENTION_HOURS` (default 7 days) are purged hourly with everything in them. The demo holds synthetic data only, so there is no backup; for real data, back up the volume and keep the backup inside the same retention promise.
- **Costs:** model calls are limited per visitor per hour and per day (`MODEL_CALLS_PER_VISITOR_HOUR`, `MODEL_CALLS_PER_DAY`); the credit limit on the OpenRouter key is the final stop. Larger models in `MODEL_CHOICES` cost more per call.
- **Remove everything:** `docker compose down -v`, then revoke the OpenRouter key.
