# School subscription billing (multi-tenancy)

Every **new** school gets a free trial; after it ends they must pay to keep
access, and if they stay unpaid past a grace period their database is deleted.
**Your own school is exempt** — it's adopted as `plan='owner'` and stays free
forever, never trial-limited and never reaped.

## The lifecycle

```
register + verify → provision → TRIAL (TENANT_TRIAL_DAYS, default 3)
   pay  → paid_until extended by TENANT_PLAN_DAYS (default 30), access continues
   no pay after trial → LOCKED (every page redirects to /billing)
   still no pay after TENANT_BILLING_GRACE_DAYS (default 7) → database DELETED
```

State is derived from dates in the registry (`trial_ends_at`, `paid_until`), so
it is always correct — no job has to flip a status to lock a school out. The
lock is enforced by `enforce_billing` (a `before_request`); the deletion is done
by `scripts/reap_unpaid_tenants.py` (run daily).

`utils/billing.py` is the single source of truth: `is_active`, `is_blocked`,
`is_reapable`, `days_left`, `record_payment`, `start_trial`.

## Payments (Paystack)

Subscriptions are collected into a **platform** Paystack account (separate from
each school's own parent-payment keys):

- `PLATFORM_PAYSTACK_SECRET_KEY`, `PLATFORM_PAYSTACK_PUBLIC_KEY`
- `TENANT_PRICE_KOBO` — the amount per period, in kobo (e.g. `5000000` = ₦50,000)

Flow: `/billing` shows status → **Pay** initialises a Paystack transaction (with
`metadata.subdomain`) → the school pays on Paystack → the **webhook**
`/billing/webhook` (HMAC-SHA512 verified, CSRF-exempt) is the authoritative
confirmation and calls `record_payment`, extending `paid_until`. The
`/billing/callback` return URL also verifies as a fallback.

In Paystack, set the webhook URL to `https://<any-school>.edusyncra.site/billing/webhook`
(the app routes it to the right school from the payment metadata).

## Testing the whole flow without real money

Set `BILLING_TEST_MODE=1` (dev only — it is **forced off** in production). Then
the **Pay** button applies a simulated payment so you can walk trial → lock →
pay → restored access end to end:

```bash
MULTI_TENANT=1 TENANT_BASE_DOMAIN=lvh.me BILLING_TEST_MODE=1 \
  TENANT_TRIAL_DAYS=3 python app.py
# 1. onboard a school at http://signup.lvh.me:PORT/register  (dev shows the verify link)
# 2. click verify → school is live at http://<school>.lvh.me:PORT/
# 3. to see the lock immediately, shorten the trial: TENANT_TRIAL_DAYS=0
# 4. any page redirects to /billing; click Pay (test) → access restored
```

To test the reaper: expire a school and run
`python scripts/reap_unpaid_tenants.py --dry-run` (report) then without
`--dry-run` (delete). The owner school is always skipped.

## Tuning
| Env | Default | Meaning |
|-----|---------|---------|
| `TENANT_TRIAL_DAYS` | 3 | free trial length |
| `TENANT_PLAN_DAYS` | 30 | days added per payment |
| `TENANT_BILLING_GRACE_DAYS` | 7 | unpaid days after expiry before deletion |
| `TENANT_PRICE_KOBO` | 0 | monthly base price (kobo) — the **seed** price |
| `BILLING_TEST_MODE` | off | simulate payments (never in production) |

### Editing prices live (no redeploy)

The env vars above only **seed** the tiers. Day-to-day, prices are edited from
the platform console at **`/platform/pricing`** (Monthly / Termly / Annual: price,
duration, label, badge, on/off). The edit is stored in the control-plane DB and
takes effect immediately everywhere the tiers appear — the marketing homepage,
the sign-up page, and each school's billing page (all read `utils.plans.tenant_plans`).

The price is captured at checkout, so **a price change only affects future
payments** — schools that already paid keep the access they bought; the new
price applies the next time they renew. The Monthly tier is the anchor (it sets
every other tier's savings % and the homepage headline price) and can't be
switched off.
