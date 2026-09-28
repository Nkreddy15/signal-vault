.PHONY: test demo compile

test:
	PYTHONPATH=src python3 -m unittest discover -s tests -v

demo:
	PYTHONPATH=src python3 -m signal_vault

compile:
	python3 -m compileall -q src tests

fake-scenario:
	PYTHONPATH=src python3 -m signal_vault.fake_paper_scenario

init-local:
	PYTHONPATH=src python3 -m signal_vault.init_local --db .data/offline-paper.sqlite3

local-dashboard:
	PYTHONPATH=src python3 -m signal_vault.dashboard --db .data/offline-paper.sqlite3

smoke: test fake-scenario compile
