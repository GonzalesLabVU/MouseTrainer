# Vercel Deployment

This web app is now designed to run as a Vercel Python project with persistent status storage in Redis.

## What changed

- The public site and API are served from the `webapp/` directory.
- The browser UI is served from `webapp/public/`.
- The API still uses the same client publishing contract:
  - `GET /api/bootstrap`
  - `GET /api/status`
  - `POST /api/client-status`
- For production, the status store should use a Redis integration exposed through:
  - `KV_REST_API_URL` and `KV_REST_API_TOKEN`, or
  - `UPSTASH_REDIS_REST_URL` and `UPSTASH_REDIS_REST_TOKEN`

## Vercel setup

### Option A: local-folder deploy with Vercel CLI

1. Install Node.js if it is not already installed.
2. Install the Vercel CLI:

```powershell
npm install -g vercel
```

3. Deploy from the `webapp` folder:

```powershell
cd webapp
vercel --prod
```

4. When prompted:
   - choose your Vercel account/team
   - create a new project
   - pick a stable project name such as `mousetrainer-status`
   - keep the code directory as `./`

The production URL will then be stable at `https://<project-name>.vercel.app`.

### Option B: Git-connected project

If you later push this repository to GitHub/GitLab/Bitbucket and import it in the Vercel dashboard, set the project Root Directory to `webapp`.

## Dashboard steps you still need to do

1. Open the Vercel dashboard and select the new project.
2. Add a Redis integration from the Marketplace.
3. Confirm that the Redis integration injected credentials into the project environment.
4. Add these project environment variables:
   - `WEBAPP_STATUS_API_KEY`: the shared key the desktop clients will send
   - `WEBAPP_STATUS_STALE_AFTER_S`: optional override, for example `10`
   - `WEBAPP_REDIS_KEY_PREFIX`: optional override if you want a different Redis namespace
5. Redeploy the project after changing environment variables.
6. Optional: add a custom domain under Settings > Domains.

## Client configuration

After the first production deploy, update the desktop client config once:

```json
{
  "enabled": true,
  "base_url": "https://<your-production-domain>",
  "api_key": "<same WEBAPP_STATUS_API_KEY value>"
}
```

Use the production domain, not a preview deployment URL. That keeps the client config stable across future redeploys.

You can update the real client config file with:

```powershell
.\tools\set_remote_status_base_url.ps1 -BaseUrl https://<your-production-domain>
```

## Local testing

You can still run the web app locally:

```powershell
.\webapp\deploy.ps1
.\webapp\start_webapp.ps1
```

Without Redis credentials, the app falls back to an in-memory store for local testing only.
