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
}
