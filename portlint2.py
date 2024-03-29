#!/usr/bin/env python3
""" portlint2 - FreeBSD ports tree lint (standalone version)
License: 3-clause BSD (see https://opensource.org/licenses/BSD-3-Clause)
Author: Hubert Tournier
"""

import datetime
import getopt
import logging
import os
import re
import signal
import socket
import sys
import textwrap
import urllib.request

# Version string used by the what(1) and ident(1) commands:
ID = "@(#) $Id: portlint2 - FreeBSD ports tree lint v1.1.1 (March 1st, 2024) by Hubert Tournier $"

# Headers and timeout delay for HTTP(S) requests:
HTTP_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:123.0) Gecko/20100101 Firefox/123.0",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en,en-US;q=0.8",
    "Accept-Encoding": "none",
    "Connection": "keep-alive",
}
CONNECTION_TIMEOUT = 10 # seconds

PORT_CATEGORIES = [
    "accessibility", "afterstep", "arabic", "archivers", "astro", "audio", "benchmarks", "biology",
    "cad", "chinese", "comms", "converters", "databases", "deskutils", "devel", "dns", "docs",
    "editors", "education", "elisp", "emulators", "enlightenment", "finance", "french", "ftp",
    "games", "geography", "german", "gnome", "gnustep", "graphics", "hamradio", "haskell", "hebrew",
    "hungarian", "irc", "japanese", "java", "kde", "kde-applications", "kde-frameworks",
    "kde-plasma", "kld", "korean", "lang", "linux", "lisp", "mail", "mate", "math", "mbone", "misc",
    "multimedia", "net", "net-im", "net-mgmt", "net-p2p", "net-vpn", "news", "parallel", "pear",
    "perl5", "plan9", "polish", "ports-mgmt", "portuguese", "print", "python", "ruby", "rubygems",
    "russian", "scheme", "science", "security", "shells", "spanish", "sysutils", "tcl", "textproc",
    "tk", "ukrainian", "vietnamese", "wayland", "windowmaker", "www", "x11", "x11-clocks",
    "x11-drivers", "x11-fm", "x11-fonts", "x11-servers", "x11-themes", "x11-toolkits", "x11-wm",
    "xfce", "zope",
]

# Default parameters. Can be overcome by command line options:
parameters = {
    "Show categories": False,
    "Show maintainers": False,
    "Checks": {
        "Hostnames": False,
        "URL": False,
    },
    "Limits": {
        "PLIST abuse": 7, # entries
        "BROKEN since": 6 * 30, # days
        "FORBIDDEN since": 3 * 30, # days
        "DEPRECATED since": 6 * 30, # days
        "Unchanged since": 3 * 365, # days
    },
    "Categories": [],
    "Maintainers": [],
    "Ports": [],
}

# Global dictionary of counters:
counters = {
    "FreeBSD ports": 0,
    "Selected ports": 0,
    "Nonexistent Makefile": 0,
    "Nonexistent port-path": 0,
    "Unusual installation-prefix": 0,
    "Too long comments": 0,
    "Uncapitalized comments": 0,
    "Dot-ended comments": 0,
    "Diverging comments": 0,
    "Nonexistent description-file": 0,
    "URL ending description-file": 0,
    "description-file same as comment": 0,
    "Too short description-file": 0,
    "Nonexistent pkg-plist": 0,
    "PLIST_FILES abuse": 0,
    "Diverging maintainers": 0,
    "Unofficial categories": 0,
    "Diverging categories": 0,
    "Empty www-site": 0,
    "Unresolvable www-site": 0,
    "Unaccessible www-site": 0,
    "Diverging www-site": 0,
    "Marked as BROKEN": 0,
    "Marked as BROKEN for too long": 0,
    "Marked as FORBIDDEN": 0,
    "Marked as FORBIDDEN for too long": 0,
    "Marked as IGNORE": 0,
    "Marked as DEPRECATED": 0,
    "Marked as DEPRECATED for too long": 0,
    "Unchanged for a long time": 0,
}

# Global dictionary of notifications to port maintainers:
notifications = {}


####################################################################################################
def _display_help():
    """ Display usage and help """
    #pylint: disable=C0301
    print("usage: portlint2 [--show-cat|-C] [--show-mnt|-M]", file=sys.stderr)
    print("        [--cat|-c LIST] [--mnt|-m LIST] [--port|-p LIST] [--plist NUM]", file=sys.stderr)
    print("        [--broken NUM] [--deprecated NUM] [--forbidden NUM] [--unchanged NUM]", file=sys.stderr)
    print("        [--check-host|-h] [--check-url|-u]", file=sys.stderr)
    print("        [--debug] [--help|-?] [--info] [--version] [--]", file=sys.stderr)
    print("  ------------------  -------------------------------------------------------", file=sys.stderr)
    print("  --show-cat|-C       Show categories with ports count", file=sys.stderr)
    print("  --show-mnt|-M       Show maintainers with ports count", file=sys.stderr)
    print("  --cat|-c LIST       Select only the comma-separated categories in LIST", file=sys.stderr)
    print("  --mnt|-m LIST       Select only the comma-separated maintainers in LIST", file=sys.stderr)
    print("  --port|-p LIST      Select only the comma-separated ports in LIST", file=sys.stderr)
    print("  --plist NUM         Set PLIST_FILES abuse to NUM files", file=sys.stderr)
    print("  --broken NUM        Set BROKEN since to NUM days", file=sys.stderr)
    print("  --deprecated NUM    Set DEPRECATED since to NUM days", file=sys.stderr)
    print("  --forbidden NUM     Set FORBIDDEN since to NUM days", file=sys.stderr)
    print("  --unchanged NUM     Set Unchanged since to NUM days", file=sys.stderr)
    print("  --check-host|-h     Enable checking hostname resolution (long!)", file=sys.stderr)
    print("  --check-url|-u      Enable checking URL (very long!)", file=sys.stderr)
    print("  --debug             Enable logging at debug level", file=sys.stderr)
    print("  --info              Enable logging at info level", file=sys.stderr)
    print("  --version           Print version and exit", file=sys.stderr)
    print("  --help|-?           Print usage and this help message and exit", file=sys.stderr)
    print("  --                  Options processing terminator", file=sys.stderr)
    print(file=sys.stderr)
    #pylint: enable=C0301


####################################################################################################
def _initialize_debugging(program_name):
    """ Set up debugging """
    console_log_format = program_name + ": %(levelname)s: %(message)s"
    logging.basicConfig(format=console_log_format, level=logging.DEBUG)
    logging.disable(logging.INFO)


####################################################################################################
def _handle_interrupt_signals(handler_function):
    """ Process interrupt signals """
    signal.signal(signal.SIGINT, handler_function)
    if os.name == "posix":
        signal.signal(signal.SIGPIPE, handler_function)


####################################################################################################
def _handle_interrupts(signal_number, current_stack_frame):
    """ Prevent SIGINT signals from displaying an ugly stack trace """
    print(" Interrupted!\n", file=sys.stderr)
    sys.exit(0)


####################################################################################################
def _process_command_line():
    """ Process command line options """
    #pylint: disable=C0103, W0602
    global parameters
    #pylint: enable=C0103, W0602

    # option letters followed by : expect an argument
    # same for option strings followed by =
    character_options = "CMc:hm:p:u?"
    string_options = [
        "broken=",
        "cat=",
        "check-host",
        "check-url",
        "debug",
        "deprecated=",
        "forbidden=",
        "help",
        "info",
        "mnt=",
        "port=",
        "plist=",
        "show-cat",
        "show-mnt",
        "unchanged=",
        "version",
    ]

    try:
        options, remaining_arguments = getopt.getopt(
            sys.argv[1:], character_options, string_options
        )
    except getopt.GetoptError as error:
        logging.critical("Syntax error: %s", error)
        _display_help()
        sys.exit(1)

    for option, argument in options:
        if option == "--debug":
            logging.disable(logging.NOTSET)

        elif option in ("--help", "-?"):
            _display_help()
            sys.exit(0)

        elif option == "--info":
            logging.disable(logging.DEBUG)

        elif option == "--version":
            print(ID.replace("@(" + "#)" + " $" + "Id" + ": ", "").replace(" $", ""))
            sys.exit(0)

        elif option == "--broken":
            try:
                parameters["Checks"]["BROKEN since"] = int(argument)
            except ValueError:
                logging.critical("Syntax error: expecting a number of days after the broken option")
                sys.exit(1)
            if parameters["Checks"]["BROKEN since"] < 30:
                logging.critical("The number of days after the broken option must be >= 30")
                sys.exit(1)

        elif option in ("--cat", "-c"):
            parameters["Categories"] = argument.lower().split(",")

        elif option in ("--check-host", "-h"):
            parameters["Checks"]["Hostnames"] = True

        elif option in ("--check-url", "-u"):
            parameters["Checks"]["Hostnames"] = True
            parameters["Checks"]["URL"] = True

        elif option == "--deprecated":
            try:
                parameters["Checks"]["DEPRECATED since"] = int(argument)
            except ValueError:
                logging.critical("Syntax error: expecting a number of days after the deprecated option")
                sys.exit(1)
            if parameters["Checks"]["DEPRECATED since"] < 30:
                logging.critical("The number of days after the deprecated option must be >= 30")
                sys.exit(1)

        elif option == "--forbidden":
            try:
                parameters["Checks"]["FORBIDDEN since"] = int(argument)
            except ValueError:
                logging.critical("Syntax error: expecting a number of days after the forbidden option")
                sys.exit(1)
            if parameters["Checks"]["FORBIDDEN since"] < 30:
                logging.critical("The number of days after the forbidden option must be >= 30")
                sys.exit(1)

        elif option in ("--mnt", "-m"):
            parameters["Maintainers"] = argument.lower().split(",")

        elif option == "--plist":
            try:
                parameters["Checks"]["PLIST abuse"] = int(argument)
            except ValueError:
                logging.critical("Syntax error: expecting a number of files after the plist option")
                sys.exit(1)
            if parameters["Checks"]["PLIST abuse"] < 3:
                logging.critical("The number of files after the plist option must be >= 3")
                sys.exit(1)

        elif option in ("--port", "-p"):
            parameters["Ports"] = argument.split(",")

        elif option in ("--show-cat", "-C"):
            parameters["Show categories"] = True
            parameters["Show maintainers"] = False

        elif option in ("--show-mnt", "-M"):
            parameters["Show maintainers"] = True
            parameters["Show categories"] = False

        elif option == "--unchanged":
            try:
                parameters["Checks"]["Unchanged since"] = int(argument)
            except ValueError:
                logging.critical("Syntax error: expecting a number of days after the unchanged option")
                sys.exit(1)
            if parameters["Checks"]["Unchanged since"] < 30:
                logging.critical("The number of days after the unchanged option must be >= 30")
                sys.exit(1)

    return remaining_arguments


####################################################################################################
def load_freebsd_ports_dict():
    """ Returns a dictionary of FreeBSD ports """
    ports = {}

    # Are we running on FreeBSD?
    operating_system = sys.platform
    if not operating_system.startswith("freebsd"):
        raise SystemError

    # On which version?
    os_version = operating_system.replace("freebsd", "")

    # Is the ports list installed?
    ports_index = "/usr/ports/INDEX-" + os_version
    if not os.path.isfile(ports_index):
        raise FileNotFoundError

    # Loading the ports list:
    with open(ports_index, encoding='utf-8', errors='ignore') as file:
        lines = file.read().splitlines()

    for line in lines:
        # The file format is described at: https://wiki.freebsd.org/Ports/INDEX
        fields = line.split('|')
        if len(fields) != 13:
            logging.error("Ports index line '%s' has %d fields instead of the expected 13. Line ignored", line, len(fields))
        elif fields[0] in ports:
            logging.error("Ports index line '%s' refers to a duplicate distribution-name. Line ignored", line)
        else:
            ports[fields[0]] = \
                {
                    "port-path": fields[1],
                    "installation-prefix": fields[2],
                    "comment": fields[3],
                    "description-file": fields[4],
                    "maintainer": fields[5].lower(),
                    "categories": fields[6],
                    "extract-depends": fields[7],
                    "patch-depends": fields[8],
                    "www-site": fields[9],
                    "fetch-depends": fields[10],
                    "build-depentds": fields[11],
                    "run-depends": fields[12],
                }

    counters["FreeBSD ports"] = len(ports)
    logging.info("Loaded %d ports from the FreeBSD Ports INDEX file", len(ports))
    return ports


####################################################################################################
def print_categories(ports):
    """ Pretty prints port categories """
    categories = {}
    for _, port in ports.items():
        for category in port["categories"].split():
            if category in categories:
                categories[category] += 1
            else:
                categories[category] = 1

    sorted_categories = dict(sorted(categories.items()))
    all_categories = ""
    for category, count in sorted_categories.items():
        all_categories += f"{category}({count}), "
    all_categories = all_categories[:-2]

    print(f"Showing {len(categories)} categories with ports counts:\n")
    for line in textwrap.wrap(all_categories, width=80, break_on_hyphens=False):
        print(line)


####################################################################################################
def print_maintainers(ports):
    """ Pretty prints port maintainers """
    maintainers = {}
    for _, port in ports.items():
        if port["maintainer"] in maintainers:
            maintainers[port["maintainer"]] += 1
        else:
            maintainers[port["maintainer"]] = 1

    sorted_maintainers = dict(sorted(maintainers.items()))
    all_maintainers = ""
    for maintainer, count in sorted_maintainers.items():
        all_maintainers += f"{maintainer}({count}), "
    all_maintainers = all_maintainers[:-2]

    print(f"Showing {len(maintainers)} maintainers with ports counts:\n")
    for line in textwrap.wrap(all_maintainers, width=80, break_on_hyphens=False):
        print(line)


####################################################################################################
def filter_ports(ports, selected_categories, selected_maintainers, selected_ports):
    """ Filters the list of ports to the specified categories AND maintainers"""
    if selected_categories or selected_maintainers or selected_ports:
        all_ports = " ".join(ports.keys())
        for port in all_ports.split():
            if selected_maintainers:
                if ports[port]["maintainer"] not in selected_maintainers:
                    del ports[port]
                    continue
            if selected_categories:
                match = False
                for category in ports[port]["categories"].split():
                    if category in selected_categories:
                        match = True
                        break
                if not match:
                    del ports[port]
                    continue
            if selected_ports:
                port_id = re.sub(r".*/", "", ports[port]["port-path"])
                if port_id not in selected_ports:
                    del ports[port]

    counters["Selected ports"] = len(ports)
    logging.info("Selected %d ports", len(ports))
    return ports


####################################################################################################
def notify_maintainer(maintainer, error, port):
    """ Notify a maintainer about an error related to a port """
    if maintainer in notifications:
        if error in notifications[maintainer]:
            if port not in notifications[maintainer][error]:
                notifications[maintainer][error].append(port)
        else:
            notifications[maintainer][error] = [port]
    else:
        notifications[maintainer] = {error: [port]}


####################################################################################################
def update_with_makefiles(ports):
    """ Loads selected part of port's Makefiles for cross-checking things """
    for name, port in ports.items():
        if not os.path.isdir(port["port-path"]):
            continue

        port_makefile = port["port-path"] + os.sep + 'Makefile'
        if not os.path.isfile(port_makefile):
            logging.error("Nonexistent Makefile for port %s", name)
            counters["Nonexistent Makefile"] += 1
            notify_maintainer(port["maintainer"], "Nonexistent Makefile", name)
        else:
            # Getting the port last modification datetime:
            ports[name]["Last modification"] = datetime.datetime.fromtimestamp(os.path.getmtime(port_makefile)).replace(tzinfo=datetime.timezone.utc)

            with open(port_makefile, encoding='utf-8', errors='ignore') as file:
                lines = file.read().splitlines()

            previous_lines = ""
            for line in lines:
                if not "#" in line:
                    line = previous_lines + line.strip()
                elif "\\#" in line:
                    line = re.sub(r"\\#", "²", line) # horrible kludge!
                    line = previous_lines + re.sub(r"[ 	]*#.*", "", line.strip()) # remove comments
                    line = re.sub(r"²", "\\#", line)
                else:
                    line = previous_lines + re.sub(r"[ 	]*#.*", "", line.strip()) # remove comments
                previous_lines = ""

                if not line:
                    continue

                if line.endswith("\\"): # Continued line
                    previous_lines = re.sub(r"\\$", "", line)
                    continue

                group = re.match(r"^([A-Z_]+)=[ 	]*(.*)", line)
                if group is not None: # Makefile variable
                    ports[name][group[1]] = group[2]

    logging.info("Found %d ports with nonexistent Makefile", counters["Nonexistent Makefile"])
    return ports


####################################################################################################
def check_port_path(ports):
    """ Checks the port-path field existence """
    for name, port in ports.items():
        if not os.path.isdir(port["port-path"]):
            logging.error("Nonexistent port-path '%s' for port %s", port["port-path"], name)
            counters["Nonexistent port-path"] += 1
            notify_maintainer(port["maintainer"], "Nonexistent port-path", name)

    logging.info("Found %d ports with nonexistent port-path", counters["Nonexistent port-path"])


####################################################################################################
def check_installation_prefix(ports):
    """ Checks the installation-prefix field usualness """
    for name, port in ports.items():
        if port["installation-prefix"] == "/usr/local":
            pass
        elif port["installation-prefix"] == "/compat/linux" and name.startswith("linux"):
            pass
        elif port["installation-prefix"] == "/usr/local/FreeBSD_ARM64" and "-aarch64-" in name:
            pass
        elif port["installation-prefix"].startswith("/usr/local/android") and "droid" in name:
            pass
        elif port["installation-prefix"] == "/var/qmail" and "qmail" in name or name.startswith("queue-fix"):
            pass
        elif port["installation-prefix"] == "/usr" and name.startswith("global-tz-") or name.startswith("zoneinfo-"):
            pass
        else:
            logging.warning("Unusual installation-prefix '%s' for port %s", port["installation-prefix"], name)
            counters["Unusual installation-prefix"] += 1
            notify_maintainer(port["maintainer"], "Unusual installation-prefix", name)

    logging.info("Found %d ports with unusual installation-prefix", counters["Unusual installation-prefix"])


####################################################################################################
def check_comment(ports):
    """ Cross-checks the comment field with the Makefile and compliance with rules
    Rules at https://docs.freebsd.org/en/books/porters-handbook/makefiles/#makefile-comment
    """
    for name, port in ports.items():
        if len(port["comment"]) > 70:
            logging.warning("Over 70 characters comment for port %s", name)
            counters["Too long comments"] += 1
            notify_maintainer(port["maintainer"], "Too long comments", name)

        if 'a' <= port["comment"][0] <= 'z':
            logging.error("Uncapitalized comment for port %s", name)
            counters["Uncapitalized comments"] += 1
            notify_maintainer(port["maintainer"], "Uncapitalized comments", name)

        if port["comment"].endswith('.'):
            logging.error("Dot-ended comment for port %s", name)
            counters["Dot-ended comments"] += 1
            notify_maintainer(port["maintainer"], "Dot-ended comments", name)

        if "COMMENT" in port:
            if '$' in port["COMMENT"]:
                continue # don't try to resolve embedded variables. Ignore check

            # Do not take into escaping backslashes which are used inconsistently
            # in both fields
            if port["comment"].replace("\\", "") != port["COMMENT"].replace("\\", ""):
                logging.error("Diverging comments between Index and Makefile for port %s", name)
                logging.error("... Index:comment    '%s'", port["comment"])
                logging.error("... Makefile:COMMENT '%s'", port["COMMENT"])
                counters["Diverging comments"] += 1
                notify_maintainer(port["maintainer"], "Diverging comments", name)

    logging.info("Found %d ports with too long comments", counters["Too long comments"])
    logging.info("Found %d ports with uncapitalized comments", counters["Uncapitalized comments"])
    logging.info("Found %d ports with dot-ended comments", counters["Dot-ended comments"])
    logging.info("Found %d ports with diverging comments", counters["Diverging comments"])


####################################################################################################
def check_description_file(ports):
    """ Checks the description-file field consistency and existence """
    for name, port in ports.items():
        nonexistent = False
        if not port["description-file"].startswith(port["port-path"]):
            if not os.path.isfile(port["description-file"]):
                nonexistent = True
        elif not os.path.isdir(port["port-path"]):
            pass # already reported
        elif not os.path.isfile(port["description-file"]):
            nonexistent = True

        if nonexistent:
            logging.error("Nonexistent description-file '%s' for port %s", port["description-file"], name)
            counters["Nonexistent description-file"] += 1
            notify_maintainer(port["maintainer"], "Nonexistent description-file", name)
        else:
            try:
                with open(port["description-file"], encoding="utf-8", errors="ignore") as file:
                    lines = file.read().splitlines()
            except:
                lines = []

            if lines:
                if lines[-1].strip().startswith("https://") or lines[-1].strip().startswith("http://"):
                    logging.error("URL '%s' ending description-file for port %s", lines[-1].strip(), name)
                    counters["URL ending description-file"] += 1
                    notify_maintainer(port["maintainer"], "URL ending description-file", name)
                    del lines[-1]

                text = " ".join(lines)
                text = text.strip()
                if port["comment"] == text:
                    logging.error("description-file content is identical to comment for port %s", name)
                    counters["description-file same as comment"] += 1
                    notify_maintainer(port["maintainer"], "description-file same as comment", name)
                elif len(text) <= len(port["comment"]):
                    logging.error("description-file content is no longer than comment for port %s", name)
                    counters["Too short description-file"] += 1
                    notify_maintainer(port["maintainer"], "Too short description-file", name)

    logging.info("Found %d ports with nonexistent description-file", counters["Nonexistent description-file"])
    logging.info("Found %d ports with URL ending description-file", counters["URL ending description-file"])
    logging.info("Found %d ports with description-file identical to comment", counters["description-file same as comment"])
    logging.info("Found %d ports with too short description-file", counters["Too short description-file"])


####################################################################################################
def check_plist(ports, plist_abuse):
    """ Checks the package list existence and compliance with rules
    Rules at https://docs.freebsd.org/en/books/porters-handbook/book/#porting-pkg-plist
    """
    for name, port in ports.items():
        if os.path.isdir(port["port-path"]):
            if not os.path.isfile(port["port-path"] + os.sep + "pkg-plist"):
                if not "PLIST_FILES" in port:
                    if not "PLIST" in port and not "PLIST_SUB" in port:
                        logging.info("Nonexistent pkg-plist/PLIST_FILES/PLIST/PLIST_SUB for port %s", name)
                        counters["Nonexistent pkg-plist"] += 1
                        # Don't notify maintainers because there are too many cases I don't understand!
                else:
                    plist_entries = len(port["PLIST_FILES"].split())
                    if plist_entries >= plist_abuse:
                        logging.warning("PLIST_FILES abuse at %d entries for port %s", plist_entries, name)
                        counters["PLIST_FILES abuse"] += 1
                        notify_maintainer(port["maintainer"], "PLIST_FILES abuse", name)

    logging.info("Found %d ports with nonexistent pkg-plist", counters["Nonexistent pkg-plist"])
    logging.info("Found %d ports with PLIST_FILES abuse", counters["PLIST_FILES abuse"])


####################################################################################################
def check_maintainer(ports):
    """ Cross-checks the maintainer field with the Makefile and compliance with rules
    Rules at https://docs.freebsd.org/en/books/porters-handbook/makefiles/#makefile-maintainer
    """
    for name, port in ports.items():
        if "MAINTAINER" in port:
            if '$' in port["MAINTAINER"]:
                continue # don't try to resolve embedded variables. Ignore check

            if port["maintainer"] != port["MAINTAINER"].lower():
                logging.error("Diverging maintainers between Index and Makefile for port %s", name)
                logging.error("... Index:maintainer    '%s'", port["maintainer"])
                logging.error("... Makefile:MAINTAINER '%s'", port["MAINTAINER"])
                counters["Diverging maintainers"] += 1
                notify_maintainer(port["maintainer"], "Diverging maintainers", name)
                notify_maintainer(port["MAINTAINER"], "Diverging maintainers", name)

    logging.info("Found %d ports with diverging maintainers", counters["Diverging maintainers"])


####################################################################################################
def check_categories(ports):
    """ Cross-checks the categories field with the Makefile and compliance with rules
    Rules at https://docs.freebsd.org/en/books/porters-handbook/makefiles/#makefile-categories-definition
    """
    for name, port in ports.items():
        for category in port["categories"].split():
            if category not in PORT_CATEGORIES:
                logging.warning("Unofficial category '%s' in Index for port %s", category, name)
                counters["Unofficial categories"] += 1
                notify_maintainer(port["maintainer"], "Unofficial category", name)

        if "CATEGORIES" in port:
            if '$' in port["CATEGORIES"]:
                continue # don't try to resolve embedded variables. Ignore check

            if port["categories"] != port["CATEGORIES"]:
                logging.error("Diverging categories between Index and Makefile for port %s", name)
                logging.error("... Index:categories    '%s'", port["categories"])
                logging.error("... Makefile:CATEGORIES '%s'", port["CATEGORIES"])
                counters["Diverging categories"] += 1
                notify_maintainer(port["maintainer"], "Diverging categories", name)

            for category in port["CATEGORIES"].split():
                if category not in PORT_CATEGORIES:
                    logging.warning("Unofficial category '%s' in Makefile for port %s", category, name)
                    counters["Unofficial categories"] += 1
                    notify_maintainer(port["maintainer"], "Unofficial category", name)

    logging.info("Found %d ports with unofficial categories", counters["Unofficial categories"])
    logging.info("Found %d ports with diverging categories", counters["Diverging categories"])


####################################################################################################
def _resolve_hostname(hostname):
    """ Resolve the hostname into an IP address or raise a NameError exception """
    try:
        ip_address = socket.gethostbyname(hostname)
    except socket.gaierror as error:
        error_message = re.sub(r".*] ", "", str(error))
        raise NameError(error_message) from error

    return ip_address


####################################################################################################
def _handle_url_errors(port_name, www_site, error, maintainer):
    """ Decides what to do with the multiple possible fetching errors """
    is_unaccessible = False
    reason = "Unaccessible www-site"
    if error.lower().startswith("http error"):
        error_code = re.sub(r"http error ","", error.lower())
        error_message = re.sub(r".*: *", "", error_code)
        error_code = re.sub(r":.*","", error_code)
        if error_code == "404":
            reason = "HTTP Error 404 (Not found) on www-site"
            logging.error("%s '%s' for port %s", reason, www_site, port_name)
            is_unaccessible = True
        elif error_code == "410":
            reason = "HTTP Error 410 (Gone) on www-site"
            logging.error("%s '%s' for port %s", reason, www_site, port_name)
            is_unaccessible = True
        elif error_code == "401":
            reason = "HTTP Error 401 (Unauthorized) on www-site"
            logging.error("%s '%s' for port %s", reason, www_site, port_name)
            is_unaccessible = True
        elif error_code == "451":
            reason = "HTTP Error 451 (Unavailable for legal reasons) on www-site"
            logging.error("%s '%s' for port %s", reason, www_site, port_name)
            is_unaccessible = True
        elif error_code == "301":
            reason = "HTTP Error 301 (Moved permanently) on www-site"
            logging.info("%s '%s' for port %s", reason, www_site, port_name)
        elif error_code == "308":
            reason = "HTTP Error 308 (Permanent redirect) on www-site"
            logging.info("%s '%s' for port %s", reason, www_site, port_name)
        else:
            # we don't consider 3xx, 5xx, and remaining 4xx errors to be a reliable sign
            # of a definitive www-site issue
            reason = "HTTP Error " + error_code + " (" + error_message + ") on www-site"
            logging.warning("%s '%s' for port %s", reason, www_site, port_name)
    elif error == "<urlopen error [Errno 8] Name does not resolve>":
        reason = "Unresolvable www-site"
        logging.error("%s '%s' for port %s", reason, www_site, port_name)
        counters["Unresolvable www-site"] += 1
    else:
        logging.debug("%s (%s) '%s' for port %s", reason, error, www_site, port_name)

    if is_unaccessible:
        notify_maintainer(maintainer, reason, port_name)

    return is_unaccessible


####################################################################################################
def check_www_site(ports, check_host, check_url):
    """ Checks the www-site field existence
    Rules at https://docs.freebsd.org/en/books/porters-handbook/makefiles/#makefile-www
    """
    unresolvable_hostnames = []
    url_ok = []
    url_ko = {}
    for name, port in ports.items():
        if port["www-site"] == "":
            logging.error("Empty www-site for port %s", name)
            counters["Empty www-site"] += 1
            notify_maintainer(port["maintainer"], "Empty www-site", name)

        elif check_host:
            hostname = re.sub(r"http[s]*://", "", port["www-site"])
            hostname = re.sub(r"/.*", "", hostname)
            hostname = re.sub(r":[0-9]*", "", hostname)
            resolvable = True
            if hostname in unresolvable_hostnames:
                resolvable = False
            else:
                try:
                    _ = _resolve_hostname(hostname)
                except NameError:
                    resolvable = False
                    unresolvable_hostnames.append(hostname)

            if not resolvable:
                logging.error("Unresolvable www-site '%s' for port %s", hostname, name)
                counters["Unresolvable www-site"] += 1
                notify_maintainer(port["maintainer"], "Unresolvable www-site", name)

            elif port["www-site"] in url_ok:
                pass

            elif port["www-site"] in url_ko:
                if _handle_url_errors(name, port["www-site"], url_ko[port["www-site"]], port["maintainer"]):
                    counters["Unaccessible www-site"] += 1

            elif check_url:
                request = urllib.request.Request(port["www-site"], headers=HTTP_HEADERS)
                try:
                    with urllib.request.urlopen(request, timeout=CONNECTION_TIMEOUT) as http:
                        _ = http.read()
                    url_ok.append(port["www-site"])
                except Exception as error:
                    url_ko[port["www-site"]] = str(error)
                    if _handle_url_errors(name, port["www-site"], str(error), port["maintainer"]):
                        counters["Unaccessible www-site"] += 1

        if "WWW" in port:
            if '$' in port["WWW"]:
                continue # don't try to resolve embedded variables. Ignore check

            if port["www-site"] not in port["WWW"].split():
                logging.error("Diverging www-site between Index and Makefile for port %s", name)
                logging.error("... Index:www-site '%s'", port["www-site"])
                logging.error("... Makefile:WWW   '%s'", port["WWW"])
                counters["Diverging www-site"] += 1
                notify_maintainer(port["maintainer"], "Diverging www-site", name)

    logging.info("Found %d ports with empty www-site", counters["Empty www-site"])
    if check_host:
        logging.info("Found %d ports with unresolvable www-site", counters["Unresolvable www-site"])
        if check_url:
            logging.info("Found %d ports with unaccessible www-site", counters["Unaccessible www-site"])
    logging.info("Found %d ports with diverging www-site", counters["Diverging www-site"])


####################################################################################################
def check_marks(ports, limits):
    """ Checks the existence of BROKEN, IGNORE, FORBIDDEN and DEPRECATED variables in Makefiles """
    for name, port in ports.items():
        today = datetime.datetime.now(datetime.timezone.utc)

        if "BROKEN" in port:
            logging.info("BROKEN mark '%s' for port %s", port["BROKEN"], name)
            if port["Last modification"] < today - datetime.timedelta(days=limits["BROKEN since"]):
                counters["Marked as BROKEN for too long"] += 1
                notify_maintainer(port["maintainer"], "Marked as BROKEN for too long", name)
            else:
                counters["Marked as BROKEN"] += 1
                notify_maintainer(port["maintainer"], "Marked as BROKEN", name)

        if "IGNORE" in port:
            logging.debug("IGNORE mark '%s' for port %s", port["IGNORE"], name)
            counters["Marked as IGNORE"] += 1
            # Don't notify maintainers because these variables frequently appear with conditions
            # that we don't take into account here...

        if "FORBIDDEN" in port:
            logging.info("FORBIDDEN mark '%s' for port %s", port["FORBIDDEN"], name)
            if port["Last modification"] < today - datetime.timedelta(days=limits["FORBIDDEN since"]):
                counters["Marked as FORBIDDEN for too long"] += 1
                notify_maintainer(port["maintainer"], "Marked as FORBIDDEN for too long", name)
            else:
                counters["Marked as FORBIDDEN"] += 1
                notify_maintainer(port["maintainer"], "Marked as FORBIDDEN", name)

        if "DEPRECATED" in port:
            logging.info("DEPRECATED mark '%s' for port %s", port["DEPRECATED"], name)
            if port["Last modification"] < today - datetime.timedelta(days=limits["DEPRECATED since"]):
                counters["Marked as DEPRECATED for too long"] += 1
                notify_maintainer(port["maintainer"], "Marked as DEPRECATED for too long", name)
            else:
                counters["Marked as DEPRECATED"] += 1
                notify_maintainer(port["maintainer"], "Marked as DEPRECATED", name)


####################################################################################################
def check_static_ports(ports, unchanged_days):
    """ Checks if the port has been unmodified for too long """
    for name, port in ports.items():
        today = datetime.datetime.now(datetime.timezone.utc)
        if "Last modification" in port:
            if port["Last modification"] < today - datetime.timedelta(days=unchanged_days):
                logging.info("No modification since more than %d days for port %s", unchanged_days, name)
                counters["Unchanged for a long time"] += 1
                notify_maintainer(port["maintainer"], "Unchanged for a long time", name)


####################################################################################################
def print_notifications():
    """ Pretty prints notifications """
    sorted_notifications = dict(sorted(notifications.items()))
    print("\nIssues per maintainer:")
    for maintainer, details in sorted_notifications.items():
        print(f"  {maintainer}:")
        for issue, ports in details.items():
            print(f"    {issue}:")
            all_ports = " ".join(ports)
            for line in textwrap.wrap(all_ports, width=74, break_on_hyphens=False):
                print(f"      {line}")
        print()


####################################################################################################
def _conditional_print(counter, message):
    """ Print a message if the counter is non zero """
    if counters[counter]:
        value = counters[counter]
        print(f"  {value} port{'' if value == 1 else 's'} {message}")


####################################################################################################
def print_summary(limits):
    """ Pretty prints a summary of findings """
    print(f'\nSelected {counters["Selected ports"]} ports out of {counters["FreeBSD ports"]} in the FreeBSD port tree, and found:')
    _conditional_print("Nonexistent port-path", "with non existent port-path")
    _conditional_print("Nonexistent Makefile", "without Makefile")
    _conditional_print("Unusual installation-prefix", "with unusual installation-prefix (warning)")
    _conditional_print("Too long comments", "with a comment string exceeding 70 characters (warning)")
    _conditional_print("Uncapitalized comments", "with an uncapitalized comment")
    _conditional_print("Dot-ended comments", "comment ending with a dot")
    _conditional_print("Diverging comments", "with a comment different between the Index and Makefile")
    _conditional_print("Nonexistent description-file", "with non existent description-file")
    _conditional_print("URL ending description-file", "with URL ending description-file")
    _conditional_print("description-file same as comment", "with description-file identical to comment")
    _conditional_print("Too short description-file", "with description-file no longer than comment")
    _conditional_print("Nonexistent pkg-plist", "without pkg-plist/PLIST_FILES/PLIST/PLIST_SUB (info)")
    _conditional_print("PLIST_FILES abuse", f"abusing PLIST_FILES with more than {limits['PLIST abuse'] - 1} entries (warning)")
    _conditional_print("Diverging maintainers", "with a maintainer different between the Index and Makefile")
    _conditional_print("Unofficial categories", "referring to unofficial categories (warning)")
    _conditional_print("Diverging categories", "with categories different between the Index and Makefile")
    _conditional_print("Empty www-site", "with no www-site")
    _conditional_print("Unresolvable www-site", "with an unresolvable www-site hostname")
    _conditional_print("Unaccessible www-site", "with an unaccessible www-site")
    _conditional_print("Diverging www-site", "with a www-site different betwwen the Index and makefile")
    _conditional_print("Marked as BROKEN", "with a BROKEN mark")
    _conditional_print("Marked as BROKEN for too long", f"with a BROKEN mark older than {limits['BROKEN since']} days")
    _conditional_print("Marked as IGNORE", "with a IGNORE mark in some cases (info)")
    _conditional_print("Marked as FORBIDDEN", "with a FORBIDDEN mark")
    _conditional_print("Marked as FORBIDDEN for too long", f"with a FORBIDDEN mark older than {limits['FORBIDDEN since']} days")
    _conditional_print("Marked as DEPRECATED", "with a DEPRECATED mark")
    _conditional_print("Marked as DEPRECATED for too long", f"with a DEPRECATED mark older than {limits['DEPRECATED since']} days")
    _conditional_print("Unchanged for a long time", f"with a last modification older than {limits['Unchanged since']} days (info)")


####################################################################################################
def main():
    """ The program's main entry point """
    program_name = os.path.basename(sys.argv[0])
    _initialize_debugging(program_name)
    _handle_interrupt_signals(_handle_interrupts)
    _ = _process_command_line()

    # Load the FreeBSD ports INDEX file
    # and verify structural integrity (ie: 13 pipe-separated fields)
    # and unicity of distribution-names
    try:
        ports = load_freebsd_ports_dict()
    except SystemError:
        logging.critical("This program will only run on a FreeBSD operating system")
        sys.exit(1)
    except FileNotFoundError:
        logging.critical("The ports tree is missing. Please install and update it as root ('portsnap fetch extract')")
        sys.exit(1)

    if parameters["Show categories"]:
        # Only print port categories with count of associated ports
        print_categories(ports)
    elif parameters["Show maintainers"]:
        # Only print port maintainers with count of associated ports
        print_maintainers(ports)
    else:
        ports = filter_ports(ports, parameters["Categories"], parameters["Maintainers"], parameters["Ports"])

        # Check the existence of port Makefile and load its variables
        ports = update_with_makefiles(ports)

        # Check the existence of port-path
        check_port_path(ports)

        # Check unusual installation-prefix
        check_installation_prefix(ports)

        # Cross-check comment identity between Index and Makefile
        check_comment(ports)

        # Check the existence of description-file
        check_description_file(ports)

        # Check the package list
        check_plist(ports, parameters["Limits"]["PLIST abuse"])

        # Cross-check maintainer identity between Index and Makefile
        check_maintainer(ports)

        # Cross-check categories identity between Index and Makefile
        # and belonging to the official list of categories
        check_categories(ports)

        # Check that www-site is not empty, that the hostnames exist,
        # that the URL is accessible, and identity between Index and Makefile
        check_www_site(ports, parameters["Checks"]["Hostnames"], parameters["Checks"]["URL"])

        # Check the existence of BROKEN, IGNORE or FORBIDDEN variables in Makefiles
        check_marks(ports, parameters["Limits"])

        # Check static ports
        check_static_ports(ports, parameters["Limits"]["Unchanged since"])

        # Print results per maintainer
        print_notifications()

        # Print summary of findings
        print_summary(parameters["Limits"])

    sys.exit(0)


if __name__ == "__main__":
    main()
