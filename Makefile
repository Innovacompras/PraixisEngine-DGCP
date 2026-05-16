up:
	docker compose up --build

up-local:
	docker compose -f docker-compose.yml -f docker-compose.local.yml up --build

down:
	docker compose down

down-local:
	docker compose -f docker-compose.yml -f docker-compose.local.yml down
