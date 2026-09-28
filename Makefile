.PHONY: test demo compile paper-readonly

test:
	PYTHONPATH=src python3 -m unittest discover -s tests -v

demo:
	PYTHONPATH=src python3 -m signal_vault

compile:
	python3 -m compileall -q src tests

# Authenticated PAPER reads only; order POST remains disabled unless the exact paper ack env is set.
paper-readonly:
	PYTHONPATH=src python3 -m signal_vault.paper_worker
