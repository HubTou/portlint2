# portlint2(8)

## NAME
portlint2 - yet another lint for FreeBSD ports Index and Makefiles

## SYNOPSIS
**portlint2**
\[--check-host|-h\]
\[--check-url|-u\]
\[--show-cat|-C\]
\[--show-mnt|-M\]
\[--cat|-c LIST\]
\[--mnt|-m LIST\]
\[--port|-p LIST\]
\[--debug\]
\[--help|-?\]
\[--info\]
\[--version\]
\[--\]

## DESCRIPTION
The **portlint2** utility checks the FreeBSD port tree Index
and some part of the port's Makefiles for errors and warnings.

By default it will scan the whole port tree, but you can select
a subset of the ports with the options *--cat|-c* for categories,
*--mnt|-m* for maintainers and *--port|-p* for ports.
All these options expect a parameter which can be a single item
or a comma-separated list of items.
If you combine several of these operators they will perform as
a logical AND.

In order to know which categories or maintainers are available
for selection, you can use the *--show-cat|-C* and *--show-mnt|-M*
options to view all the categories and maintainers with their
number of associated ports.

The two costlier analysis are disabled by default.
You can check if the port's www sites hostnames are resolvable
with the *--check-host|-h* option (takes about 15 minutes on the
whole port tree).
And you can check if the port's www sites URL are available
with the *--check-url|-u* option, which implies the previous one
(takes about 6 hours on the whole port tree).

### OPTIONS
Options | Use
------- | ---
--check-host\|-h|Enable checking hostname resolution (long!)
--check-url\|-u|Enable checking URL (very long!)
--show-cat\|-C|Show categories with ports count
--show-mnt\|-M|Show maintainers with ports count
--cat\|-c LIST|Select only the comma-separated categories in LIST
--mnt\|-m LIST|Select only the comma-separated maintainers in LIST
--port\|-p LIST|Select only the comma-separated ports in LIST
--debug|Enable logging at debug level
--help\|-?|Print usage and this help message and exit
--info|Enable logging at info level
--version|Print version and exit
--|Options processing terminator

## FILES
[/usr/ports/INDEX-xx](https://wiki.freebsd.org/Ports/INDEX)
- where xx is the major version of FreeBSD that you are using (as I write this xx=14)

The whole port tree under /ports/INDEX-xx
- as root, get the last version with "cd /usr/ports ; make fetchindex"

## EXIT STATUS
The **portlint2** utility exits 0 on success, and >0 if an error occurs.

## EXAMPLES
To analyze the full port tree in the background, do:
```Shell
$ nohup portlint2 --info -hu > stdout.txt 2> stderr.txt &
```
Results for this example are available there:
* [stdout output](https://www.frbsd.org/xch/stdout.txt),
* [stderr output](https://www.frbsd.org/xch/stderr.txt) for details.

To analyze the ports of a specific maintainer identified by id@domain, do:
```Shell
$ portlint2 --info -m id@domain
```

## SEE ALSO
[lint(1)](https://man.freebsd.org/cgi/man.cgi?query=lint&manpath=Unix+Seventh+Edition),
[portlint(1)](https://www.freshports.org/ports-mgmt/portlint/)

## STANDARDS
The **portlint2** utility is not a standard UNIX command.

This implementation tries to follow the [PEP 8](https://www.python.org/dev/peps/pep-0008/) style guide for [Python](https://www.python.org/) code.

## PORTABILITY
None. Works only on FreeBSD, but who needs anything else?

## HISTORY
While working on the 4th version of the [pysec2vuxml](https://github.com/HubTou/pysec2vuxml) tool,
I noticed there were errors in the FreeBSD port Index,
so I built this tool to analyze this more thoroughly...

It was a rainy Saturday anyway :-)

## LICENSE
It is available under the [3-clause BSD license](https://opensource.org/licenses/BSD-3-Clause).

## AUTHORS
[Hubert Tournier](https://github.com/HubTou)

## CAVEATS
Requires Python 3.6 or more.
