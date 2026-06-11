"""
PosyHub — public launcher (app + Cloudflare tunnel) in one command:

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


def _cloudflared_command():
    """Return (cmd, hostname_for_banner) or (None, None) if cloudflared missing."""
    exe = shutil.which('cloudflared')
    if not exe:
        return None, None
    tunnel = os.environ.get('CLOUDFLARE_TUNNEL')
    hostname = os.environ.get('CLOUDFLARE_HOSTNAME')
    config = os.path.expanduser('~/.cloudflared/config.yml')
    if tunnel:                       # named tunnel by name
        return [exe, 'tunnel', 'run', tunnel], hostname
    if os.path.exists(config):       # named tunnel via config.yml
        return [exe, 'tunnel', '--config', config, 'run'], hostname
    # Quick tunnel — no Cloudflare account or domain required.
    return [exe, 'tunnel', '--url', f'http://{HOST}:{PORT}', '--no-autoupdate'], None


def _banner(url):
    line = '=' * 60
    print('\n' + line)
    print('  PUBLIC DEMO URL:  ' + url)
    print('  Share this link with your teachers (works on mobile data).')
    print('  Keep this window open. Press Ctrl-C to stop.')
    print(line + '\n', flush=True)


def main():
    print('Starting PosyHub app server...')
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
