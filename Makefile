.PHONY: test demo compile

test:
	PYTHONPATH=src python3 -m unittest discover -s tests -v

demo:
	PYTHONPATH=src python3 -m signal_vault

compile:
	python3 -m compileall -q src tests
