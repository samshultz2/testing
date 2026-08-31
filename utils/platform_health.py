"""Platform health checks for the operator console.

Deliberately cheap and side-effect-free: reachability of the control plane and
tenant databases (a ``SELECT 1``), whether the background scheduler is running,
and whether the payment gateway / email are configured. No external network
calls are made — a health page must never hang on a third party — so gateway and
email report *configuration* status, not a live round-trip.
"""
from __future__ import annotations


def _check_control_plane():
    from utils import tenancy
    try:
        n = len(tenancy.list_tenants())
        return ('Control plane database', 'ok', f'reachable · {n} tenant record(s)')
    except Exception:
        return ('Control plane database', 'bad', 'unreachable')


def _check_tenant_dbs():
    from utils import tenancy
    from utils.tenant_runtime import _engine_for
    from sqlalchemy import text
    try:
        tenants = [t for t in tenancy.list_tenants()
                   if t.status == 'active' and t.database_url]
    except Exception:
        return ('Tenant databases', 'warn', 'could not enumerate tenants')
    total = len(tenants)
    if total == 0:
        return ('Tenant databases', 'ok', 'no active schools yet')
    reachable = 0
    for t in tenants:
        try:
            with _engine_for(t.database_url).connect() as c:
                c.execute(text('SELECT 1'))
                reachable += 1
        except Exception:
            pass
    if reachable == total:
        return ('Tenant databases', 'ok', f'{reachable}/{total} reachable')
    if reachable:
        return ('Tenant databases', 'warn', f'{reachable}/{total} reachable')
    return ('Tenant databases', 'bad', 'none reachable')


def _check_scheduler():
    # Two valid topologies: jobs in-process (the web worker owns the scheduler), or
    # the web/jobs split (RUN_INPROCESS_JOBS=0) where a dedicated worker owns it.
    # In the split, the web worker serving this page never sets the in-process flag,
    # so we fall back to the shared job-timing sidecar: a recent tick proves the
    # dedicated worker is alive.
    import os
    import time
    try:
        import app as _appmod
        if bool(getattr(_appmod, '_scheduler_started', False)):
            return ('Background scheduler', 'ok', 'running (in-process)')
    except Exception:
        pass
    inproc = os.environ.get('RUN_INPROCESS_JOBS', '1').strip().lower() \
        not in ('0', 'false', 'no', 'off')
    if not inproc:
        try:
            from utils import sys_metrics
            tick = sys_metrics.request_metrics().get('jobs', {}).get('scheduled_tick')
            if tick and (time.time() - tick.get('at', 0)) < 180:
                return ('Background scheduler', 'ok', 'running (dedicated worker)')
            # The worker records a tick within ~60s of starting; give it a moment.
            return ('Background scheduler', 'warn', 'dedicated worker: awaiting first tick')
        except Exception:
            return ('Background scheduler', 'warn', 'status unknown')
    return ('Background scheduler', 'warn', 'not started')


def _check_config(current_app):
    cfg = current_app.config
    out = []
    pay = cfg.get('PLATFORM_PAYSTACK_SECRET_KEY') or cfg.get('PAYSTACK_SECRET_KEY')
    out.append(('Payment gateway (Paystack)', 'ok' if pay else 'warn',
                'configured' if pay else 'not configured'))
    email = cfg.get('SMTP_HOST') and cfg.get('SMTP_FROM')
    out.append(('Email (SMTP)', 'ok' if email else 'warn',
                'configured' if email else 'not configured'))
    return out


def health_checks(current_app):
    """List of {name, status: ok|warn|bad, detail} for the health panel."""
    rows = [_check_control_plane(), _check_tenant_dbs(), _check_scheduler()]
    rows += _check_config(current_app)
    return [{'name': n, 'status': s, 'detail': d} for n, s, d in rows]


def overall(rows):
    """Roll-up status for the header badge."""
    states = {r['status'] for r in rows}
    if 'bad' in states:
        return 'bad'
    if 'warn' in states:
        return 'warn'
    return 'ok'
