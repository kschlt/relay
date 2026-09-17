# The contract suite runs on a bare Python 3 with nothing installed. That is
# deliberate: an adapter author in another language should be able to clone this
# repository and check their own output without adopting a Python toolchain.

PYTHON ?= python3

.PHONY: check test fixtures schema help

help:
	@echo "make check     run the contract suite (the default gate)"
	@echo "make test      alias for check"
	@echo "make fixtures  run the conformance CLI over the fixture corpus"
	@echo "make schema    confirm the published schema parses"

check:
	$(PYTHON) -m unittest discover -s tests -t . -v

test: check

fixtures:
	$(PYTHON) -m relay_intake.conformance fixtures/valid

schema:
	$(PYTHON) -c "import json; json.load(open('schema/intake-envelope-v1.schema.json')); print('schema parses')"
