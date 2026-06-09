# PostgreSQL on Termux + proot Ubuntu

How to get a working PostgreSQL 16 server running for PosyHub inside a
**proot Ubuntu** distro on Termux (Android). This setup has no systemd, and
`sudo` does not work, so the standard Debian/Ubuntu instructions need a couple
of adjustments. These are the exact steps that worked.

## 0. Make sure you are inside proot Ubuntu

The biggest source of confusion is running these commands in Termux's *native*
environment instead of the proot distro. In native Termux, `/var` is read-only
and `pg_ctlcluster` does not exist.

```bash
proot-distro login ubuntu
```

Confirm you're in the right place:

```bash
echo $PREFIX          # should be EMPTY inside proot (not a /data/data/... path)
cat /etc/os-release   # should say Ubuntu
```

Your prompt should look like `root@localhost`.

## 1. Install PostgreSQL

```bash
apt update && apt install -y postgresql postgresql-contrib
ls /usr/lib/postgresql/   # the folder name is your version (e.g. 16)
```

## 2. Create the socket directory proot often misses

```bash
mkdir -p /var/run/postgresql
chown postgres:postgres /var/run/postgresql
```

## 3. Initialize and start the cluster (the part that needs the workaround)

`pg_createcluster` / `pg_ctlcluster` **fail under proot** with:

```
FATAL:  data directory ".../16/main" has wrong ownership
HINT:   The server must be started by the user that owns the data directory.
```

This is because the wrapper switches users in a way proot doesn't fully
emulate, so the bootstrap backend's UID doesn't match the (faked) directory
ownership. `sudo` also fails here ("No superuser binary detected. Are you
rooted?").

**The fix: become the `postgres` user with `su` (not `sudo`) and run `initdb`
/ `pg_ctl` directly.** When everything runs *as* postgres, owner and process
UIDs match.

```bash
# clean slate + correct ownership
rm -rf /var/lib/postgresql/16/main
mkdir -p /var/lib/postgresql/16/main
chown -R postgres:postgres /var/lib/postgresql

# switch INTO the postgres user (su, NOT sudo)
su postgres
```

Now, **as the `postgres` user** (prompt shows `postgres@localhost`):

```bash
# initialize the data dir
/usr/lib/postgresql/16/bin/initdb -D /var/lib/postgresql/16/main

# start the server
/usr/lib/postgresql/16/bin/pg_ctl -D /var/lib/postgresql/16/main -l /tmp/pg.log start
```

## 4. Create the app database and user

Still as the `postgres` user:

```bash
psql -c "CREATE USER posyhub WITH PASSWORD 'posyhub';"
psql -c "CREATE DATABASE posyhub OWNER posyhub;"
```

Then return to root:

```bash
exit
```

## 5. Point PosyHub at the database

`DATABASE_URL` set inside the `postgres` shell does **not** survive `exit`.
Set it in the shell where you actually run the app:

```bash
export DATABASE_URL="postgresql+psycopg://posyhub:posyhub@localhost:5432/posyhub"
```

Sanity check the connection:

```bash
psql "postgresql://posyhub@localhost:5432/posyhub" -c "\conninfo"
```

> `initdb` defaults to `trust` auth for local connections, so the password may
> not be checked locally — fine for local dev.

## Every session afterwards

There is no systemd, so Postgres does **not** auto-start. Each time you
re-enter proot:

```bash
su postgres -c "/usr/lib/postgresql/16/bin/pg_ctl -D /var/lib/postgresql/16/main -l /tmp/pg.log start"
```

Make `DATABASE_URL` persistent so you don't re-export it each time:

```bash
echo 'export DATABASE_URL="postgresql+psycopg://posyhub:posyhub@localhost:5432/posyhub"' >> ~/.bashrc
```

To stop the server:

```bash
su postgres -c "/usr/lib/postgresql/16/bin/pg_ctl -D /var/lib/postgresql/16/main stop"
```

## Optional: a start-db.sh helper

```bash
cat > ~/start-db.sh <<'EOF'
#!/usr/bin/env bash
su postgres -c "/usr/lib/postgresql/16/bin/pg_ctl -D /var/lib/postgresql/16/main -l /tmp/pg.log start"
EOF
chmod +x ~/start-db.sh
```

## Troubleshooting

- **`has wrong ownership` even as postgres** → proot UID emulation issue; relaunch
  the distro with `proot-distro login ubuntu --link2symlink` and retry step 3.
- **`pg_ctlcluster: command not found`** → you're in native Termux, not proot. Go
  back to step 0.
- **`/var` read-only** → same as above, you're not inside proot.
- **`No superuser binary detected. Are you rooted?`** → you used `sudo`; use `su`
  instead.
