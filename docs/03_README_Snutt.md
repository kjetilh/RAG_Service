# README-snutt (valgfri)

Lim inn dette i repoets README for en “happy path”:

```bash
make venv
make deps
cp .env.example .env
make db-up
make rebuild
make ingest PAPERS=../papers AUTHOR="Test" YEAR=2024
make api
```
