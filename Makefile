.PHONY: test demo compile paper-readonly paper-daemon init-paper preflight monitor backup

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

# Local-only tooling, no broker calls. These commands NEVER enable real or paper POST.
init-paper:
	PYTHONPATH=src python3 -m signal_vault.init_paper

preflight:
	PYTHONPATH=src python3 -m signal_vault.preflight

monitor:
	PYTHONPATH=src python3 -m signal_vault.operator_server

backup:
	@test -n "$(BACKUP_DEST)" || (echo "Set BACKUP_DEST=private/path/file.sqlite3" >&2; exit 2)
	PYTHONPATH=src python3 -m signal_vault.local_backup --destination "$(BACKUP_DEST)"
