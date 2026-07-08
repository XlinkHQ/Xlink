.PHONY: help install up down logs deploy migrate cli shell ps test

help:
	@echo "XLink — common tasks:"
	@echo "  make install   first-time setup (.env + secrets + build + up)"
	@echo "  make up        start the full stack (api + web + db + redis)"
	@echo "  make down      stop the stack"
	@echo "  make deploy    rebuild + migrate + restart"
	@echo "  make migrate   apply pending DB migrations"
	@echo "  make logs      tail api logs"
	@echo "  make cli c='user list'   run an XLink CLI command"
	@echo "  make ps        service status"
	@echo "  make test      run the backend test suite"

install:
	./xlink.sh install pull

up:
	docker compose up -d

down:
	docker compose down

deploy:
	./xlink.sh install pull

migrate:
	docker compose run --rm migrate

logs:
	docker compose logs -f api

cli:
	docker compose exec -T api python -m app.cli.main $(c)

shell:
	docker compose exec api bash

ps:
	docker compose ps

test:
	docker compose exec -T api pytest -q

test-pg:
	docker compose exec -T postgres psql -U xlink -d xlink -c "DROP DATABASE IF EXISTS xlink_test;" >/dev/null
	docker compose exec -T postgres psql -U xlink -d xlink -c "CREATE DATABASE xlink_test;" >/dev/null
	XLINK_TEST_DATABASE_URL=postgresql+asyncpg://xlink:$(or $(XLINK_POSTGRES_PASSWORD),change_me_in_production)@127.0.0.1:$(or $(XLINK_POSTGRES_PORT),5434)/xlink_test \
		uv run pytest app/tests/test_pg_concurrency.py app/tests/test_refresh_concurrency.py app/tests/test_db_pool.py -q
