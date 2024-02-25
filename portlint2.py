#!/usr/bin/env python3
""" portlint2 - yet another lint for FreeBSD ports Index and Makefiles
License: 3-clause BSD (see https://opensource.org/licenses/BSD-3-Clause)
Author: Hubert Tournier
"""

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
ID = "@(#) $Id: portlint2 - yet another lint for FreeBSD ports Index and Makefiles v1.0.0 (February 25, 2024) by Hubert Tournier $"

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
    "Check hostnames": False,
    "Check URL": False,
    "Show categories": False,
    "Show maintainers": False,
    "Categories": [],
    "Maintainers": [],
    "Ports": [],
}

# Global dictionary of counters:
counters = {
    "FreeBSD ports": 0,
    "Selected ports": 0,
    "Unexistent Makefile": 0,
    "Unexistent port-path": 0,
    "Unusual installation-prefix": 0,
    "Too long comments": 0,
    "Uncapitalized comments": 0,
    "Dot-ended comments": 0,
    "Diverging comments": 0,
    "Unexistent description-file": 0,
    "Diverging maintainers": 0,
    "Undocumented categories": 0,
    "Diverging categories": 0,
    "Empty www-site": 0,
    "Unresolvable www-site": 0,
    "Unaccessible www-site": 0,
    "Diverging www-site": 0,
}

# Global dictionary of notifications to port maintainers:
notifications = {}


####################################################################################################
def _display_help():
    """ Display usage and help """
    #pylint: disable=C0301
    print("usage: portlint2 [--check-host|-h] [--check-url|-u]", file=sys.stderr)
    print("        [--show-cat|-C] [--show-mnt|-M]", file=sys.stderr)
    print("        [--cat|-c LIST] [--mnt|-m LIST] [--port|-p LIST]", file=sys.stderr)
    print("        [--debug] [--help|-?] [--info] [--version] [--]", file=sys.stderr)
    print("  ------------------  ---------------------------------------------------", file=sys.stderr)
    print("  --check-host|-h     Enable checking hostname resolution (long!)", file=sys.stderr)
    print("  --check-url|-u      Enable checking URL (very long!)", file=sys.stderr)
    print("  --show-cat|-C       Show categories with ports count", file=sys.stderr)
    print("  --show-mnt|-M       Show maintainers with ports count", file=sys.stderr)
    print("  --cat|-c LIST       Select only the comma-separated categories in LIST", file=sys.stderr)
    print("  --mnt|-m LIST       Select only the comma-separated maintainers in LIST", file=sys.stderr)
    print("  --port|-p LIST      Select only the comma-separated ports in LIST", file=sys.stderr)
    print("  --debug             Enable logging at debug level", file=sys.stderr)
    print("  --help|-?           Print usage and this help message and exit", file=sys.stderr)
    print("  --info              Enable logging at info level", file=sys.stderr)
    print("  --version           Print version and exit", file=sys.stderr)
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
        "check-host",
        "check-url",
        "show-cat",
        "show-mnt",
        "cat=",
        "mnt=",
        "port=",
        "debug",
        "help",
        "info",
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

        elif option in ("--check-host", "-h"):
            parameters["Check hostnames"] = True

        elif option in ("--check-url", "-u"):
            parameters["Check hostnames"] = True
            parameters["Check URL"] = True

        elif option in ("--show-cat", "-C"):
            parameters["Show categories"] = True
            parameters["Show maintainers"] = False

        elif option in ("--show-mnt", "-M"):
            parameters["Show maintainers"] = True
            parameters["Show categories"] = False

        elif option in ("--cat", "-c"):
            parameters["Categories"] = argument.split(",")

        elif option in ("--mnt", "-m"):
            parameters["Maintainers"] = argument.split(",")

        elif option in ("--port", "-p"):
            parameters["Ports"] = argument.split(",")

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
                    "maintainer": fields[5],
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
            logging.error("Unexistent Makefile for port %s", name)
            counters["Unexistent Makefile"] += 1
            notify_maintainer(port["maintainer"], "Unexistent Makefile", name)
        else:
            with open(port_makefile, encoding='utf-8', errors='ignore') as file:
                lines = file.read().splitlines()

            previous_lines = ""
            for line in lines:
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

    logging.info("Found %d ports with unexistent Makefile", counters["Unexistent Makefile"])
    return ports


####################################################################################################
def check_port_path(ports):
    """ Checks the port-path field existence """
    for name, port in ports.items():
        if not os.path.isdir(port["port-path"]):
            logging.error("Unexistent port-path '%s' for port %s", port["port-path"], name)
            counters["Unexistent port-path"] += 1
            notify_maintainer(port["maintainer"], "Unexistent port-path", name)

    logging.info("Found %d ports with unexistent port-path", counters["Unexistent port-path"])


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

            if port["comment"] != port["COMMENT"]:
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
        unexistent = False
        if not port["description-file"].startswith(port["port-path"]):
            # it appears to be quite common and probably OK in most cases...
            logging.debug("description-file '%s' not sitting under port-path '%s' for port %s", port["description-file"], port["port-path"], name)
            if not os.path.isfile(port["description-file"]):
                unexistent = True
        elif not os.path.isdir(port["port-path"]):
            pass # already reported
        elif not os.path.isfile(port["description-file"]):
            unexistent = True

        if unexistent:
            logging.error("Unexistent description-file '%s' for port %s", port["description-file"], name)
            counters["Unexistent description-file"] += 1
            notify_maintainer(port["maintainer"], "Unexistent description-file", name)

    logging.info("Found %d ports with unexistent description-file", counters["Unexistent description-file"])


####################################################################################################
def check_maintainer(ports):
    """ Cross-checks the maintainer field with the Makefile and compliance with rules
    Rules at https://docs.freebsd.org/en/books/porters-handbook/makefiles/#makefile-maintainer
    """
    for name, port in ports.items():
        if "MAINTAINER" in port:
            if '$' in port["MAINTAINER"]:
                continue # don't try to resolve embedded variables. Ignore check

            if port["maintainer"].lower() != port["MAINTAINER"].lower():
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
                logging.warning("Undocumented category '%s' in Index for port %s", category, name)
                counters["Undocumented categories"] += 1
                notify_maintainer(port["maintainer"], "Undocumented category", name)

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
                    logging.warning("Undocumented category '%s' in Makefile for port %s", category, name)
                    counters["Undocumented categories"] += 1
                    notify_maintainer(port["maintainer"], "Undocumented category", name)

    logging.info("Found %d ports with undocumented categories", counters["Undocumented categories"])
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
def print_summary():
    """ Pretty prints a summary of findings """
    print(f'\nSelected {counters["Selected ports"]} ports out of {counters["FreeBSD ports"]} in the FreeBSD port tree, and found:')

    if counters["Unexistent port-path"]:
        value = counters["Unexistent port-path"]
        print(f'  {value} port{"" if value == 1 else "s"} with non existent port-path')
    if counters["Unexistent Makefile"]:
        value = counters["Unexistent Makefile"]
        print(f'  {value} port{"" if value == 1 else "s"} without Makefile')
    if counters["Unusual installation-prefix"]:
        value = counters["Unusual installation-prefix"]
        print(f'  {value} port{"" if value == 1 else "s"} with unusual installation-prefix (warning)')
    if counters["Too long comments"]:
        value = counters["Too long comments"]
        print(f'  {value} port{"" if value == 1 else "s"} with a comment string exceeding 70 characters (warning)')
    if counters["Uncapitalized comments"]:
        value = counters["Uncapitalized comments"]
        print(f'  {value} port{"" if value == 1 else "s"} with an uncapitalized comment')
    if counters["Dot-ended comments"]:
        value = counters["Dot-ended comments"]
        print(f'  {value} port{"" if value == 1 else "s"} comment ending with a dot')
    if counters["Diverging comments"]:
        value = counters["Diverging comments"]
        print(f'  {value} port{"" if value == 1 else "s"} with a comment different between the Index and Makefile')
    if counters["Unexistent description-file"]:
        value = counters["Unexistent description-file"]
        print(f'  {value} port{"" if value == 1 else "s"} with non existent description-file')
    if counters["Diverging maintainers"]:
        value = counters["Diverging maintainers"]
        print(f'  {value} port{"" if value == 1 else "s"} with a maintainer different between the Index and Makefile')
    if counters["Undocumented categories"]:
        value = counters["Undocumented categories"]
        print(f'  {value} port{"" if value == 1 else "s"} referring to unofficial categories (warning)')
    if counters["Diverging categories"]:
        value = counters["Diverging categories"]
        print(f'  {value} port{"" if value == 1 else "s"} with a maintainer different between the Index and Makefile')
    if counters["Empty www-site"]:
        value = counters["Empty www-site"]
        print(f'  {value} port{"" if value == 1 else "s"} with no www-site')
    if counters["Unresolvable www-site"]:
        value = counters["Unresolvable www-site"]
        print(f'  {value} port{"" if value == 1 else "s"} with an unresolvable www-site hostname')
    if counters["Unaccessible www-site"]:
        value = counters["Unaccessible www-site"]
        print(f'  {value} port{"" if value == 1 else "s"} with an unaccessible www-site')
    if counters["Diverging www-site"]:
        value = counters["Diverging www-site"]
        print(f'  {value} port{"" if value == 1 else "s"} with a www-site different betwwen the Index and makefile')


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

        # Cross-check maintainer identity between Index and Makefile
        check_maintainer(ports)

        # Cross-check categories identity between Index and Makefile
        # and belonging to the official list of categories
        check_categories(ports)

        # Check that www-site is not empty, that the hostnames exist,
        # that the URL is accessible, and identity between Index and Makefile
        check_www_site(ports, parameters["Check hostnames"], parameters["Check URL"])

        # Print results per maintainer
        print_notifications()

        # Print summary of findings
        print_summary()

    sys.exit(0)


if __name__ == "__main__":
    main()
