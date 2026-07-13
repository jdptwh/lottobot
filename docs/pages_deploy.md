# Deploying the Maine Scratch EV Ranker to GitHub Pages

This guide enables the public-facing site at GitHub Pages. The site reads `../data/latest.json` at runtime, so deployment configuration must match this relative-path requirement.

## Enabling GitHub Pages (one-time setup)

1. Go to your repository's **Settings** → **Pages**.
2. Under "Build and deployment", select **"Deploy from a branch"**.
3. Choose:
   - **Branch:** `master`
   - **Folder:** `/` (root)
4. Click **Save**.

The site will publish to:
```
https://<owner>.github.io/lottobot/site/
```

## Critical: Root publishing is REQUIRED

The site's code fetches `../data/latest.json` using a relative path. This path resolves correctly **only** when publishing from the repository **root** (`/`).

Do **not** use the `/docs` folder option. Doing so will break the data fetch and render the page inoperable.

## Private repository note

If your repository is private, GitHub Pages is not available in the free tier. Upgrade to GitHub Pro or make the repository public to enable Pages.

## Local preview (before deployment)

To preview the site locally before enabling Pages:

1. From the repository root, start a local web server:
   ```bash
   python -m http.server 8208
   ```

2. Open your browser to:
   ```
   http://localhost:8208/site/
   ```

The page will load and fetch data from the local `../data/latest.json`.

**Note:** `fetch()` fails on `file://` URLs (browser security), so the HTTP server is required even for local testing. Port 8207 is reserved for the panel dashboard in development, so use 8208.

## After enabling Pages

Once Pages is enabled, the live rankings will be updated automatically by the scheduled GitHub Actions workflow (see `.github/workflows/` for the daily-run configuration).
