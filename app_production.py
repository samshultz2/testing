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

from app import app  # noqa: E402  — the configured application instance

HOST = '127.0.0.1'
PORT = int(os.environ.get('PORT', '5000'))


def _serve_app():
    """Run the WSGI app. Prefer waitress; fall back to Flask's server."""
    try:
        from waitress import serve
        serve(app, host=HOST, port=PORT, threads=8)
    except ImportError:
        print("(waitress not installed — using the built-in server; "
              "`pip install waitress` for a sturdier demo)")
        app.run(host=HOST, port=PORT, threaded=True, use_reloader=False)


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
    threading.Thread(target=_serve_app, daemon=True).start()
    if not _wait_until_up():
        sys.exit(f'ERROR: the app did not start on http://{HOST}:{PORT}')
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
