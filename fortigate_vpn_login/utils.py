# -*- coding: utf-8 -*-
"""
    fortigate_vpn_login.utils
    ~~~~~~~~~~~~~~~~~~~~~~~~~

    Helper methods for fortigate_vpn_login
"""
import os
import psutil
import subprocess
import re
from typing import Optional
from shutil import which
from pathlib import Path
from enum import Enum, auto
from fortigate_vpn_login import logger


class VPNStatus(Enum):
    UNKNOWN = auto()
    DISCONNECTED = auto()
    CONNECTED_FOREGROUND = auto()
    CONNECTED_BACKGROUND = auto()


def get_default_config_filepath() -> Path:
    """
    Gets the default path for storing configuration files for this program. On UNIX, this will follow the
    XDG standard: `~/.config/fortigate_vpn_login`. On Windows, there's no standard, so we'll use
    `%APPDIR%/fortigate_vpn_login`.

    Returns:
        obj(Path): the path to store configuration files

    """
    if is_windows():
        return Path(os.getenv('APPDATA')) / 'fortigate_vpn_login'
    else:
        return Path(os.path.expanduser('~/.config/fortigate_vpn_login'))


def is_windows() -> bool:
    """
    Detects if the application is running on windows or not.

    Returns:
        bool: True if it's on Windows. False if not.
    """
    return os.name == 'nt'


def find_openconnect() -> Optional[Path]:
    """
    Checks openconnect presence on the system/path

    Returns:
        obj(Path)|Optional: path of the openconnect executable
    """
    if not is_windows():
        openconnect_path = which('openconnect')

    else:
        openconnect_path = which('openconnect.exe') or which('openconnect')

        if not openconnect_path:
            system_drive = os.environ.get('SystemDrive', 'C:')
            program_files = os.environ.get('ProgramFiles', f'{system_drive}\\Program Files')
            program_files_x86 = os.environ.get('ProgramFiles(x86)', f'{system_drive}\\Program Files (x86)')

            try_paths = [
                Path(f'{system_drive}\\ProgramFiles\\OpenConnect-GUI\\openconnect.exe'),
                Path(f'{system_drive}\\ProgramFiles\\OpenConnect\\openconnect.exe'),
                Path(program_files) / 'OpenConnect-GUI' / 'openconnect.exe',
                Path(program_files) / 'OpenConnect' / 'openconnect.exe',
                Path(program_files_x86) / 'OpenConnect-GUI' / 'openconnect.exe',
                Path(program_files_x86) / 'OpenConnect' / 'openconnect.exe',
                Path(r'c:\Progra~1\OpenConnect-GUI\openconnect.exe'),
                Path(r'c:\Progra~1\OpenConnect\openconnect.exe'),
                Path(r'c:\Progra~2\OpenConnect-GUI\openconnect.exe'),
                Path(r'c:\Progra~2\OpenConnect\openconnect.exe'),
                Path(r'c:\Progra~3\OpenConnect-GUI\openconnect.exe'),
                Path(r'c:\Progra~3\OpenConnect\openconnect.exe'),
            ]

            for try_path in try_paths:
                if try_path.is_file() and os.access(str(try_path), os.X_OK):
                    openconnect_path = str(try_path)
                    break

        if not openconnect_path:
            # Query Windows Registry for OpenConnect installation
            try:
                import winreg
                for hive in [winreg.HKEY_LOCAL_MACHINE, winreg.HKEY_CURRENT_USER]:
                    for sub in [
                        r'Software\Microsoft\Windows\CurrentVersion\Uninstall',
                        r'Software\WOW6432Node\Microsoft\Windows\CurrentVersion\Uninstall',
                    ]:
                        try:
                            with winreg.OpenKey(hive, sub) as key:
                                num_subkeys = winreg.QueryInfoKey(key)[0]
                                for i in range(num_subkeys):
                                    try:
                                        subkey_name = winreg.EnumKey(key, i)
                                        with winreg.OpenKey(key, subkey_name) as subkey:
                                            for val_name in ['InstallLocation', 'DisplayIcon', 'UninstallString']:
                                                try:
                                                    val, _ = winreg.QueryValueEx(subkey, val_name)
                                                    if isinstance(val, str) and 'openconnect' in val.lower():
                                                        clean_val = val.strip('"\'')
                                                        candidate = Path(clean_val)
                                                        if candidate.is_file():
                                                            if candidate.name.lower() == 'openconnect.exe':
                                                                openconnect_path = str(candidate)
                                                                break
                                                            exe_in_parent = candidate.parent / 'openconnect.exe'
                                                            if exe_in_parent.is_file():
                                                                openconnect_path = str(exe_in_parent)
                                                                break
                                                        elif candidate.is_dir():
                                                            exe_in_dir = candidate / 'openconnect.exe'
                                                            if exe_in_dir.is_file():
                                                                openconnect_path = str(exe_in_dir)
                                                                break
                                                except OSError:
                                                    pass
                                            if openconnect_path:
                                                break
                                    except OSError:
                                        pass
                                if openconnect_path:
                                    break
                        except OSError:
                            pass
                    if openconnect_path:
                        break
            except Exception as e:
                logger.debug(f"Error querying registry for openconnect: {e}")

    if not openconnect_path:
        return None
    else:
        logger.debug(f"Found openconnect path: {openconnect_path}")
        return Path(openconnect_path)


def is_openconnect_running_windows():
    """
    Detects if openconnect is running on windows or not.

    Returns:
        bool: True if running on Windows. False if not.
    """
    running = 'openconnect.exe' in (p.name() for p in psutil.process_iter(["name"]))
    logger.debug(f"is openconnect running on windows? {running}")
    if running:
        return True
    else:
        return False


def get_openconnect_pid(pid_file: str) -> int:
    """
    If it's running and has a pid file, gets the PID number

    Args:
        pid_file (str): Location of the file containing the PID number

    Returns:
        int: the PID number
    """
    pid = None
    with open(pid_file, 'r') as fp:
        pid = int(fp.read())

    logger.debug(f"get openconnect pid: {pid}")
    if pid and not psutil.pid_exists(pid):
        pid = None

    return pid


def check_openconnect_version(openconnect_path: Optional[Path]) -> bool:
    """
    Checks if the openconnect version is compatible with this program, mainly checking for the
    'fortinet' protocol support.

    Args:
        openconnect_path (Path): path of the openconnect executable

    Returns:
        bool: True if compatible. False if not.
    """
    if not openconnect_path:
        return False

    env = os.environ.copy()
    env['LC_ALL'] = 'C'
    process = subprocess.run([openconnect_path, '--version'], env=env, capture_output=True)
    output = process.stdout.decode("utf-8")
    logger.debug(f"Checking openconnect version: {output}")

    if not process.returncode == 0:
        return False

    # openconnect version
    # match = re.search(r'^OpenConnect version v(.*?)[\r\n]*$', output, re.MULTILINE)
    # openconnect_version = match.group(1)

    # openconnect fortinet support
    match = re.search(r'^Supported protocols: (.*?)$', output, re.MULTILINE)
    openconnect_supported_protocols = match.group(1)
    openconnect_supported_protocols = openconnect_supported_protocols.replace("(default)", "")
    openconnect_supported_protocols = [x.strip() for x in openconnect_supported_protocols.split(',')]
    logger.debug(f"Openconnect supported protocols: {openconnect_supported_protocols}")

    if 'fortinet' not in openconnect_supported_protocols:
        return False

    return True
