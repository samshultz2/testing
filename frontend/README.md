# Frontend build

The React "islands" are bundled by `build.mjs` (esbuild) into
`../static/js/react/*.js`. React/ReactDOM are externalised to the vendored UMD
runtime, so each app bundle is just its own code + shared components.

## Commands

```sh
cd frontend
node build.mjs            # one-off production build
node build.mjs --watch    # rebuild on change (dev)
```

A production build also **stamps the service worker**: `build.mjs` writes
`static/js/sw.js`'s `CACHE_VERSION` from a content hash of the built bundles +
CSS (`b-<hash>`). Because the bundles keep stable filenames, this is what makes a
deploy actually reach clients — the version changes whenever an asset changes, so
there is no manual bump to forget. `/sw.js` is served `no-cache`, so the new
worker is picked up on the next load.

## Pre-commit hook (run once per clone)

Keep the committed bundles and the SW version in sync automatically:

```sh
git config core.hooksPath .githooks
```

After that, committing a change under `frontend/src/`, `static/css/` or
`static/js/` rebuilds and re-stamps the service worker, then re-stages the
result — so you never commit source without its matching bundle + cache version.
