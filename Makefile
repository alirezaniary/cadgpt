# The whole interface of this repository.
#
# `verify` runs the gate registry in tools/verify.py. It is stdlib-only on purpose:
# the runner has to be able to run before and without the rest of the toolchain,
# and every gate brings its own tooling when it is registered (DEC-0022).

PYTHON ?= python3

.PHONY: verify

verify:
	$(PYTHON) -m tools.verify
