# Database migrations

This project does not currently use a migration framework. Apply SQL migrations
to a backed-up database during deployment, not as part of application startup.

`001_add_premium_tables.sql` is additive and idempotent. It creates only the
Premium entitlement and access-request tables and their indexes; it does not
modify existing user or learning records. On SQLite, run it with:

```text
sqlite3 path\to\placeiq.db ".read backend\migrations\001_add_premium_tables.sql"
```

The application also creates missing tables from SQLAlchemy metadata on startup.
The migration is provided for explicit deployment and upgrade workflows.

`002_add_premium_payment_tables.sql` is an additive, idempotent migration for
Razorpay Test Mode order, payment-attempt, and webhook-event records. Before
manual application, stop the backend and make a timestamped backup from the
repository root:

```powershell
$stamp = Get-Date -Format "yyyyMMdd-HHmmss"
Copy-Item backend\placeiq.db "backend\placeiq.db.backup-$stamp"
sqlite3 backend\placeiq.db ".read backend\migrations\002_add_premium_payment_tables.sql"
```

Check the `sqlite3` exit code and inspect the new tables before restarting the
application. Do not apply this migration to the development database as part of
tests. It never drops or rewrites existing tables.
