"""
EduSyncra — public launcher (app + Cloudflare tunnel) in one command:

    python app_production.py

What it does:
  1. Serves the app with a production WSGI server (waitress) on localhost:PORT.
  2. Starts `cloudflared` and prints the public HTTPS demo URL to share with
     teachers — no shared Wi-Fi needed, works over their mobile data.

Two URL modes (chosen automatically):
  • SHORT, STABLE url on YOUR domain  → set CLOUDFLARE_TUNNEL (and optionally
    CLOUDFLARE_HOSTNAME) in .env, or have ~/.cloudflared/config.yml.
    Gives e.g. https://posy.yourschool.ng  — one-time setup in docs/PHONE_PILOT.md.
  • INSTANT url, zero setup            → used when no named tunnel is configured.
    Gives a random https://<words>.trycloudflare.com  (longer, changes each run).

To run WITHOUT Cloudflare (local only):  python app.py
"""
import os
import re
import shutil
import socket
import subprocess
import sys
import threading
import time

# We always sit behind the Cloudflare proxy here, so trust forwarded headers
# (gives correct HTTPS detection for secure cookies). Set before importing app.
os.environ.setdefault('TRUST_PROXY', '1')

HOST = '127.0.0.1'
PORT = int(os.environ.get('PORT', '5000'))


def _tcp_open(host, port, timeout=1):
    with socket.socket() as s:
        s.settimeout(timeout)
        return s.connect_ex((host, port)) == 0


def _local_pg_target(uri):
    """(host, port) when the configured DB is a PostgreSQL on this machine,
    else None. A SQLite file or a remote/managed Postgres is left alone — we
    only ever try to start a database we're hosting locally."""
    if not uri.startswith('postgresql'):
        return None
    from urllib.parse import urlparse
    p = urlparse(uri)
    host = p.hostname or '127.0.0.1'
    if host not in ('127.0.0.1', 'localhost', '::1'):
        return None
    return host, (p.port or 5432)


def _have_user(name):
    try:
        import pwd
        pwd.getpwnam(name)
        return True
    except KeyError:
        return False


def _start_postgres(port):
    """Best-effort start of a local PostgreSQL.

    First the Debian/Ubuntu registered-cluster path (service / pg_ctlcluster).
    If that doesn't bind the port — common on phone/proot installs where
    /etc/postgresql has no cluster registered — fall back to starting an
    existing data directory directly as the 'postgres' user, mirroring the
    manual recovery (recreate the tmpfs socket dir, clear a stale lock, run
    pg_ctl as postgres). We only reach here when nothing is listening, so
    removing a leftover postmaster.pid is safe.
    """
    import glob
    cmds = [['service', 'postgresql', 'start']]
    for d in sorted(glob.glob('/etc/postgresql/*/main')):
        # /etc/postgresql/<version>/main -> pg_ctlcluster <version> main start
        cmds.append(['pg_ctlcluster', d.split('/')[3], 'main', 'start'])
    for cmd in cmds:
        if not shutil.which(cmd[0]):
            continue
        try:
            subprocess.run(cmd, capture_output=True, text=True, timeout=30)
        except Exception:
            continue

    # Fresh install with no cluster at all ("No PostgreSQL clusters exist"):
    # neither /etc/postgresql nor a data dir holds one. Create + start one with
    # pg_createcluster so a brand-new phone/proot box is genuinely one-command.
    have_cluster = bool(glob.glob('/etc/postgresql/*/main') or [
        d for d in glob.glob('/var/lib/postgresql/*/main')
        if os.path.exists(os.path.join(d, 'PG_VERSION'))])
    if (not _tcp_open('127.0.0.1', port) and not have_cluster
            and shutil.which('pg_createcluster')):
        versions = sorted(p.split('/')[4]
                          for p in glob.glob('/usr/lib/postgresql/*/bin/pg_ctl'))
        if versions:
            print(f'No PostgreSQL cluster exists — creating one (v{versions[-1]})...')
            try:
                subprocess.run(['pg_createcluster', versions[-1], 'main', '--start'],
                               capture_output=True, text=True, timeout=120)
            except Exception:
                pass

    if _tcp_open('127.0.0.1', port) or not _have_user('postgres'):
        return

    # Fallback: an unregistered data dir at the standard path. Ensure the
    # runtime socket dir exists (it lives on tmpfs and vanishes on restart).
    try:
        os.makedirs('/var/run/postgresql', exist_ok=True)
        shutil.chown('/var/run/postgresql', 'postgres', 'postgres')
    except Exception:
        pass
    for d in sorted(glob.glob('/var/lib/postgresql/*/main')):
        if not os.path.exists(os.path.join(d, 'PG_VERSION')):
            continue
        pg_ctl = f"/usr/lib/postgresql/{d.split('/')[3]}/bin/pg_ctl"
        if not os.path.exists(pg_ctl):
            continue
        try:
            os.remove(os.path.join(d, 'postmaster.pid'))  # stale lock
        except OSError:
            pass
        print(f'Starting unregistered PostgreSQL data dir {d} as postgres...')
        try:
            subprocess.run(
                ['su', '-s', '/bin/sh', 'postgres', '-c',
                 f'{pg_ctl} -D {d} -l {d}/server.log start'],
                capture_output=True, text=True, timeout=30)
        except Exception:
            pass
        if _tcp_open('127.0.0.1', port):
            return


def _ensure_database():
    """Make sure the configured database is reachable before the app connects.

    For a locally-hosted PostgreSQL that isn't up yet, try to start it and wait
    until it accepts connections — so `python app_production.py` is genuinely a
    one-command launch. No-op for SQLite or a remote database.
    """
    from config import Config            # loads .env + resolves DATABASE_URL
    target = _local_pg_target(Config.SQLALCHEMY_DATABASE_URI)
    if not target:
        return
    host, port = target
    if _tcp_open(host, port):
        return                           # already running
    print(f'PostgreSQL not reachable on {host}:{port} — starting it...')
    _start_postgres(port)
    for _ in range(60):                  # wait up to ~30s for it to accept conns
        if _tcp_open(host, port):
            print('PostgreSQL is up.')
            return
        time.sleep(0.5)
    sys.exit(
        f'ERROR: PostgreSQL did not come up on {host}:{port}.\n'
        f'Start it manually and retry:\n'
        f'  service postgresql start      (or: pg_ctlcluster <version> main start)\n'
        f'  # if it says "No PostgreSQL clusters exist", create one first:\n'
        f'  pg_createcluster $(ls /usr/lib/postgresql) main --start\n'
        f'  pg_isready -h {host} -p {port}\n'
        f'If it refuses to start, check the log: '
        f'/var/lib/postgresql/<version>/main/server.log')


# Bring the database up first, then import the app (which connects on import).
_ensure_database()

from app import app  # noqa: E402  — the configured application instance


def _serve_app():
    """Run the WSGI app. Prefer waitress; fall back to Flask's server.

    A bind failure (e.g. the port already in use) is recorded in
    ``_serve_error`` so the main thread can fail loudly instead of carrying on
    and pointing the tunnel at a stale instance.
    """
    global _serve_error
    try:
        try:
            from waitress import serve
            serve(app, host=HOST, port=PORT, threads=8)
        except ImportError:
            print("(waitress not installed — using the built-in server; "
                  "`pip install waitress` for a sturdier demo)")
            app.run(host=HOST, port=PORT, threaded=True, use_reloader=False)
    except OSError as e:
        _serve_error = e


def _port_in_use():
    with socket.socket() as s:
        s.settimeout(1)
        return s.connect_ex((HOST, PORT)) == 0


_serve_error = None


def _wait_until_up(timeout=60):
    for _ in range(timeout * 2):
        with socket.socket() as s:
            s.settimeout(1)
            if s.connect_ex((HOST, PORT)) == 0:
                return True
        time.sleep(0.5)
    return False


# The school's domain (already on Cloudflare). Override via .env if it changes.
DOMAIN = os.environ.get('CLOUDFLARE_HOSTNAME', 'edusyncra.site')
TUNNEL = os.environ.get('CLOUDFLARE_TUNNEL', 'edusyncra')


def _tunnel_exists(exe, name):
    """True if a named cloudflared tunnel exists on this machine's account."""
    try:
        out = subprocess.run([exe, 'tunnel', 'list'], capture_output=True,
                             text=True, timeout=20).stdout
        return name in out
    except Exception:
        return False


def _print_named_setup():
    print('\nTo serve at https://%s you need a ONE-TIME tunnel setup:' % DOMAIN)
    print('  cloudflared tunnel login                # authorize %s in the browser' % DOMAIN)
    print('  cloudflared tunnel create %s' % TUNNEL)
    print('  cloudflared tunnel route dns %s %s' % (TUNNEL, DOMAIN))
    print('Then run this script again. Falling back to a temporary URL for now...\n')


def _cloudflared_command():
    """Return (cmd, hostname_for_banner) or (None, None) if cloudflared missing."""
    exe = shutil.which('cloudflared')
    if not exe:
        return None, None
    config = os.path.expanduser('~/.cloudflared/config.yml')
    if _tunnel_exists(exe, TUNNEL):  # the named tunnel for the school domain
        return [exe, 'tunnel', 'run', '--url', f'http://{HOST}:{PORT}', TUNNEL], DOMAIN
    if os.path.exists(config):       # named tunnel via config.yml
        return [exe, 'tunnel', '--config', config, 'run'], os.environ.get('CLOUDFLARE_HOSTNAME')
    # Named tunnel not set up yet: print the exact commands, use a quick tunnel.
    _print_named_setup()
    return [exe, 'tunnel', '--url', f'http://{HOST}:{PORT}', '--no-autoupdate'], None


def _banner(url):
    line = '=' * 60
    print('\n' + line)
    print('  PUBLIC DEMO URL:  ' + url)
    print('  Share this link with your teachers (works on mobile data).')
    print('  Keep this window open. Press Ctrl-C to stop.')
    print(line + '\n', flush=True)


def main():
    print('Starting EduSyncra app server...')
    # If the port is already taken, another instance is almost certainly still
    # running. Bail out clearly rather than start a tunnel to the stale app.
    if _port_in_use():
        sys.exit(
            f"ERROR: port {PORT} is already in use — another EduSyncra instance "
            f"is probably still running.\n"
            f"Free it and try again:  fuser -k {PORT}/tcp"
            f"   (or: pkill -f app_production.py)")
    server = threading.Thread(target=_serve_app, daemon=True)
    server.start()
    if not _wait_until_up() or _serve_error is not None or not server.is_alive():
        msg = f'ERROR: the app did not start on http://{HOST}:{PORT}'
        if _serve_error is not None:
            msg += f'\n{type(_serve_error).__name__}: {_serve_error}'
        sys.exit(msg)
    print(f'App is running locally at http://{HOST}:{PORT}')

    cmd, hostname = _cloudflared_command()
    if cmd is None:
        print('\ncloudflared is not installed, so there is no public URL.')
        print('Install it (see docs/PHONE_PILOT.md) or use it on the LAN.')
        print('The app is running locally. Press Ctrl-C to stop.')
        _idle()
        return

    if hostname:
        # Named tunnel: the hostname is fixed, show it straight away.
        _banner('https://' + hostname.lstrip('https://').lstrip('/'))

    quick_url = re.compile(r'https://[-a-z0-9]+\.trycloudflare\.com')
    print('Starting Cloudflare tunnel...')
    proc = None
    try:
        while True:
            proc = subprocess.Popen(cmd, stdout=subprocess.PIPE,
                                    stderr=subprocess.STDOUT, text=True, bufsize=1)
            shown = hostname is not None
            for line in proc.stdout:
                if not shown:
                    m = quick_url.search(line)
                    if m:
                        _banner(m.group(0))
                        shown = True
            proc.wait()
            print('\nTunnel dropped — restarting in 5s (Ctrl-C to quit)...',
                  flush=True)
            time.sleep(5)
    except KeyboardInterrupt:
        print('\nShutting down...')
    finally:
        if proc and proc.poll() is None:
            proc.terminate()


def _idle():
    try:
        while True:
            time.sleep(3600)
    except KeyboardInterrupt:
        print('\nStopped.')


if __name__ == '__main__':
    main()
