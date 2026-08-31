// Build the per-page React bundles with React/ReactDOM EXTERNALISED to a single
// shared UMD runtime (static/vendor/react*.js, loaded once by the page shell).
//
// Why: previously each of the ~28 entry points `--bundle`d its own copy of React
// + ReactDOM, so finance-app.js alone was 340 KB and the framework was shipped
// ~28 times and re-downloaded on every cross-module navigation. Mapping the bare
// react imports to the `window.React` / `window.ReactDOM` globals lets the browser
// download React once and cache it, and shrinks every app bundle to just its own
// code + shared components.
import { build } from 'esbuild';
import { createHash } from 'node:crypto';
import { readdirSync, readFileSync, writeFileSync, statSync } from 'node:fs';
import { join } from 'node:path';

const ENTRIES = [
  'spike', 'attendance', 'attendance-app', 'dashboard-app', 'students-app',
  'student-view-app', 'student-form-app', 'student-trash-app', 'sales-app',
  'library-app', 'events-app', 'admissions-app', 'reports-app', 'promotion-app',
  'mock-jamb-app', 'comms-app', 'hr-app', 'finance-app', 'subjects-app',
  'results-app', 'cbt-app', 'academics-app', 'settings-app', 'users-app',
  'contributions-app', 'timetable-app', 'scratchcards-app', 'parent-app',
].map((n) => `src/${n}.jsx`);

// Map the bare React specifiers to the globals exposed by the vendored UMD bundles.
const GLOBALS = { react: 'React', 'react-dom': 'ReactDOM', 'react-dom/client': 'ReactDOM' };
const externalGlobals = {
  name: 'external-globals',
  setup(b) {
    const filter = /^(react|react-dom|react-dom\/client)$/;
    b.onResolve({ filter }, (args) => ({ path: args.path, namespace: 'global-shim' }));
    b.onLoad({ filter: /.*/, namespace: 'global-shim' }, (args) => ({
      contents: `module.exports = window.${GLOBALS[args.path]};`, loader: 'js',
    }));
  },
};

// Stamp static/js/sw.js's CACHE_VERSION from a content hash of everything the
// service worker caches (the built React bundles, our top-level scripts and the
// CSS). The React bundles keep stable filenames, so without this a deploy that
// changes their *contents* would not change the SW file — clients would keep
// serving the old JS until someone remembered to hand-bump the version. Hashing
// the assets makes the version change automatically whenever any of them does.
function stampServiceWorker() {
  const root = '../static';
  const dirs = ['js/react', 'js', 'css'];
  const files = [];
  for (const d of dirs) {
    const abs = join(root, d);
    let names = [];
    try { names = readdirSync(abs); } catch { continue; }
    for (const n of names.sort()) {
      if (!/\.(js|css)$/.test(n)) continue;
      if (d === 'js' && n === 'sw.js') continue;     // never hash the SW itself
      const p = join(abs, n);
      try { if (statSync(p).isFile()) files.push(p); } catch { /* skip */ }
    }
  }
  const h = createHash('sha256');
  for (const p of files) h.update(readFileSync(p));
  const version = 'b-' + h.digest('hex').slice(0, 12);

  const swPath = join(root, 'js/sw.js');
  const src = readFileSync(swPath, 'utf8');
  const next = src.replace(/const CACHE_VERSION = '[^']*';/,
                           `const CACHE_VERSION = '${version}';`);
  if (next !== src) {
    writeFileSync(swPath, next);
    console.log(`service worker CACHE_VERSION → ${version} (${files.length} assets hashed)`);
  } else {
    console.log(`service worker CACHE_VERSION unchanged (${version})`);
  }
}

const watch = process.argv.includes('--watch');
const ctx = {
  entryPoints: ENTRIES,
  bundle: true,
  minify: !watch,
  format: 'iife',
  target: 'es2018',
  outdir: '../static/js/react',
  plugins: [externalGlobals],
  logLevel: 'info',
};

if (watch) {
  const esbuild = await import('esbuild');
  const c = await esbuild.context(ctx);
  await c.watch();
  console.log('watching…');
} else {
  await build(ctx);
  stampServiceWorker();
}
