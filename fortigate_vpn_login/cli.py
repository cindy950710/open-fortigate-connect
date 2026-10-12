# -*- coding: utf-8 -*-
"""
    fortigate_vpn_login.cli
    ~~~~~~~~~~~~~~~~~~~~~~

    This is the CLI interface for running the package.
"""
import logging
import multiprocessing
import os
import platform
import sys
import webbrowser
import subprocess
from pathlib import Path
from argparse import ArgumentParser, RawDescriptionHelpFormatter
from fortigate_vpn_login import __version__, __description__, logger
from fortigate_vpn_login import utils, config
from fortigate_vpn_login.fortigate import Fortigate
import fortigate_vpn_login.webserver as webserver


def main() -> int:
    """
    Main method which is called by CLI.

    Returns:
        int: The status from the program.

    Exit codes:
        0: Everything went well.
        1: General error while connecting to the VPN
        2: Usage/syntax error
    """
    multiprocessing.freeze_support()

    # main program argument parser
    parser = ArgumentParser(
        formatter_class=RawDescriptionHelpFormatter,
        description=(
            f"fortigate-vpn-login {__version__}{os.linesep}"
            f"{__description__}"
        )
    )

    parser.add_argument(
        '-d',
        '--debug',
        help='Set LOG_LEVEL to DEBUG.',
        dest="DEBUG_MODE",
        action='store_true'
    )

    parser.add_argument(
        '-q',
        '--quiet',
        help='Do not log at all.',
        dest="QUIET_MODE",
        action='store_true'
    )

    parser.add_argument(
        '--configure',
        help='Interactive configuration.',
        dest='INTERACTIVE_CONFIGURE',
        action='store_true'
    )

    parser.add_argument(
        '-s',
        '--forti-url',
        help='URL of the Fortigate VPN server.',
        dest='FORTI_URL'
    )

    parser.add_argument(
        '-k',
        '--disconnect',
        '--kill',
        help='Disconnect active VPN session.',
        dest='DISCONNECT',
        action='store_true'
    )

    # windows don't have these options supported
    if not utils.is_windows():
        parser.add_argument(
            '-F',
            '--foreground',
            help='Run VPN in foreground.',
            dest="FOREGROUND",
            action='store_true'
        )

        parser.add_argument(
            '-B',
            '--background',
            help='Run VPN in background (default).',
            dest="BACKGROUND",
            action='store_true',
            default=True
        )
    else:
        parser.set_defaults(FOREGROUND=False, BACKGROUND=False)

    # parse the arguments, show in the screen if needed, etc
    parser = parser.parse_args()

    if parser.DEBUG_MODE:
        logger.setLevel("DEBUG")
        logging.getLogger().setLevel(os.getenv("LOG_LEVEL", "DEBUG"))
        # TODO: on debug mode, change log format to
        # '[%(asctime)s] [%(levelname)s] [%(name)s:%(filename)s:%(lineno)s: %(funcName)s()] %(message)s'))
    else:
        # defaults to info
        logger.setLevel("INFO")
        logging.getLogger().setLevel(os.getenv("LOG_LEVEL", "INFO"))

    if parser.QUIET_MODE:
        logging.disable(logging.CRITICAL)

    if getattr(parser, 'FOREGROUND', False):
        parser.BACKGROUND = False

    # load configuration
    options = config.Config()

    if getattr(parser, 'DISCONNECT', False):
        if utils.is_windows():
            res = subprocess.run(["taskkill", "/F", "/IM", "openconnect.exe"], capture_output=True, text=True)
            if res.returncode == 0:
                print("VPN disconnected successfully (OpenConnect terminated).")
            else:
                print("No active OpenConnect VPN process found.")
            return 0
        else:
            pid_file = options.get('openconnect_pid_filename')
            pid = utils.get_openconnect_pid(pid_file) if pid_file else None
            if pid:
                os.kill(pid, 15)
                print(f"VPN process (PID {pid}) terminated.")
            else:
                res = subprocess.run(["pkill", "openconnect"], capture_output=True)
                if res.returncode == 0:
                    print("VPN disconnected successfully.")
                else:
                    print("No active OpenConnect VPN process found.")
            return 0

    # do we need to configure interactively?
    if parser.INTERACTIVE_CONFIGURE:
        options.configure()
        options.write()
        return 0

    openconnect_path = utils.find_openconnect()

    if not openconnect_path:
        print("ERROR: Could not find openconnect executable. "
              "Please make sure OpenConnect or OpenConnect-GUI is installed.")
        return 1

    # openconnect compatability check
    if not utils.check_openconnect_version(openconnect_path):
        print("ERROR: Your openconnect version isn't compatible with this program. "
              "Make sure you have the latest version, which supports the \"fortinet\" protocol.")
        return 1

    # server url
    if not parser.FORTI_URL:
        fortigate_vpn_url = options.get('forti_url')
        if not fortigate_vpn_url:
            print('ERROR: "forti_url" option is not set. Use "-s" or "--configure" to set it.')
            return 2
    else:
        fortigate_vpn_url = parser.FORTI_URL

    # establish connection to the Fortigate VPN Server, grab info, etc
    fortigate = Fortigate(fortigate_vpn_url)
    fortigate_vpn_url = fortigate.url

    # In FortiOS SAML workflow, the browser must initiate the flow via /remote/saml/start?redirect=1
    # directly so the browser maintains session cookies and context across IdP redirects.
    saml_start_url = f"{fortigate.url}/remote/saml/start?redirect=1"

    # webserver to get the response from the IDP through browser request
    ws = webserver.run()
    webbrowser.open(saml_start_url)
    auth_id = webserver.return_token()
    webserver.quit(ws)

    if auth_id == '-1':
        print("ERROR: Invalid ID from provider. Try again or contact your provider support.")
        return 1

    cookie_svpn = fortigate.get_cookie(auth_id)
    if not cookie_svpn:
        print("ERROR: Failed to retrieve SVPNCOOKIE from server.")
        return 1

    openconnect_arguments = [
        "--protocol=fortinet",
        f"--server={fortigate_vpn_url}",
        f"--useragent=fortigate-vpn-login-{__version__}:{platform.uname().version}",
        "--no-dtls",
        "--non-inter",
        "--disable-ipv6",
        f"--cookie=SVPNCOOKIE={cookie_svpn}",
    ]

    if utils.is_windows():
        openconnect_arguments.append("--interface=vpn0")

    if parser.QUIET_MODE:
        openconnect_arguments.append("--quiet")

    if parser.DEBUG_MODE:
        openconnect_arguments.append("--verbose")

    if getattr(parser, 'BACKGROUND', False):
        openconnect_arguments.append("--quiet")
        openconnect_arguments.append("--background")

    command_line = []
    if utils.is_windows():
        import tempfile
        workdir = openconnect_path.parent
        bat_file = Path(tempfile.gettempdir()) / "fortigate_vpn_run.bat"
        escaped_args = " ".join([f'"{arg}"' for arg in openconnect_arguments])
        bat_content = (
            "@echo off\r\n"
            "title FortiGate OpenConnect VPN\r\n"
            f'"{str(openconnect_path)}" {escaped_args}\r\n'
            "echo.\r\n"
            "echo OpenConnect process has exited.\r\n"
            "pause\r\n"
        )
        bat_file.write_text(bat_content, encoding="utf-8")
        command_line = [
            "powershell",
            "-Command",
            f"Start-Process cmd.exe -ArgumentList '/c',\"{str(bat_file)}\" -Verb runAs -WorkingDirectory '{workdir}'",
        ]
    else:
        if not os.getuid() == 0:
            command_line.append("sudo")
            command_line = command_line + [str(openconnect_path)] + openconnect_arguments

    env = os.environ.copy()
    env['LC_ALL'] = 'C'

    try:
        if not getattr(parser, 'BACKGROUND', False):
            subprocess.run(command_line, env=env)
        else:
            subprocess.run(command_line, env=env,
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except KeyboardInterrupt:
        logger.debug("User interrupted process.")
        print("CTRL+C/SIGTERM detected. Exiting.")

    return 0


if __name__ == "__main__":
    sys.exit(main())
