.PHONY: test demo compile paper-readonly paper-daemon

test:
	PYTHONPATH=src python3 -m unittest discover -s tests -v

demo:
	PYTHONPATH=src python3 -m signal_vault

compile:
	python3 -m compileall -q src tests

# Authenticated PAPER reads only; order POST remains disabled unless the exact paper ack env is set.
paper-readonly:
	PYTHONPATH=src python3 -m signal_vault.paper_worker

# Long-running ALPACA PAPER-only loop. POST still needs the exact paper-only acknowledgement.
paper-daemon:
	PYTHONPATH=src python3 -m signal_vault.paper_daemon
