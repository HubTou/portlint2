# portlint2 TODOLIST

## Probable evolutions
* Checking reported vulnerabilities with my [vuxml](https://github.com/HubTou/vuxml) library
  * Would introduce and external dependency, and thus motivate turning this standalone program
    into a Python package

## Possible evolutions
* Checking the existence of domains in maintainer's email addresses
* Checking the depends fields (extract/patch/fetch/build/run):
  * between the Index and the Makefiles
  * against the existence of the dependencies
* Other Makefiles related checks
* Adding an option to notice port maintainers by email (but I don't want to harrass them...)
* Configuration file
  * Exclusion of ports, maintainers, categories

## Unprobable evolutions
* Checking reported vulnerabilities in dependencies
* Checking unavailable ports in dependencies

Feel free to submit your own ideas!
