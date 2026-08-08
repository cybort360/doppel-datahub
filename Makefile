.PHONY: install dev test run demo fixture datahub-bootstrap clean

install:
	python -m pip install -r requirements.txt

dev:
	python -m pip install -r requirements-dev.txt

test:
	pytest

run:
	uvicorn app.main:app --reload

demo:
	python -m app.cli generate --asset healthcare --scale 1 --seed 42 --expiry-days 30 --publish

fixture:
	python scripts/create_fixture.py

datahub-bootstrap:
	python scripts/bootstrap_datahub.py

clean:
	find artifacts/runs -mindepth 1 ! -name .gitkeep -delete
