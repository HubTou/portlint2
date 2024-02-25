NAME=portlint2

# Default action is to show this help message:
.help:
	@echo "Possible targets:"
	@echo "  check-code     Verify PEP 8 compliance (lint)"
	@echo "  check-security Verify security issues (audit)"
	@echo "  check-unused   Find unused code"
	@echo "  check-version  Find required Python version"
	@echo "  check-sloc     Count Single Lines of Code"
	@echo "  checks         Make all the previous tests"
	@echo "  install        Install software (as root)"
	@echo "  uninstall      Uninstall software (as root) (deinstall)"
	@echo "  distclean      Remove all generated files (clean)"

check-code: /usr/local/bin/pylint
	-pylint ${NAME}.py

lint: check-code

check-security: /usr/local/bin/bandit
	-bandit -r ${NAME}.py

audit: check-security

check-unused: /usr/local/bin/vulture
	-vulture --sort-by-size ${NAME}.py

check-version: /usr/local/bin/vermin
	-vermin ${NAME}.py

check-sloc: /usr/local/bin/pygount
	-pygount --format=summary .

checks: check-code check-security check-unused check-version check-sloc

love:
	@echo "Not war!"

${NAME}.8.gz: ${NAME}.8
	@gzip -k9c ${NAME}.8 > ${NAME}.8.gz

install: ${NAME}.8.gz
	install -m 755 ${NAME}.py /usr/local/bin/${NAME}
	install -m 644 ${NAME}.8.gz /usr/local/man/man8

uninstall:
	rm -f /usr/local/bin/${NAME}
	rm -f /usr/local/man/man8/${NAME}.8.gz

deinstall: uninstall

distclean:
	rm -f ${NAME}.8.gz

clean: distclean

