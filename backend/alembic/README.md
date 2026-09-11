# Database migrations

The project currently keeps startup `create_all` and additive SQLite compatibility
for existing local databases. Alembic is now scaffolded for new revisions:

```powershell
cd backend
alembic revision --autogenerate -m "describe change"
alembic upgrade head
```

Do not remove the startup compatibility block until an initial baseline revision
has been generated and verified against existing SQLite and PostgreSQL databases.
