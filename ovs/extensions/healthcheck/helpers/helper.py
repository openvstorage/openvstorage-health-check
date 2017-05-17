#!/usr/bin/python

# Copyright (C) 2016 iNuron NV
#
# This file is part of Open vStorage Open Source Edition (OSE),
# as available from
#
#      http://www.openvstorage.org and
#      http://www.openvstorage.com.
#
# This file is free software; you can redistribute it and/or modify it
# under the terms of the GNU Affero General Public License v3 (GNU AGPLv3)
# as published by the Free Software Foundation, in version 3 as it comes
# in the LICENSE.txt file of the Open vStorage OSE distribution.
#
# Open vStorage is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY of any kind.

"""
Helper module
"""
import json
import platform
import socket
import subprocess
from ovs.extensions.generic.system import System
from ovs.extensions.generic.sshclient import SSHClient
from ovs.extensions.generic.configuration import Configuration
from ovs.extensions.packages.package import PackageManager


class Helper(object):
    """
    Helper module
    """
    MODULE = "utils"
    SETTINGS_LOC = "/opt/OpenvStorage/config/healthcheck/settings.json"
    RAW_INIT_MANAGER = str(subprocess.check_output('cat /proc/1/comm', shell=True)).strip()
    LOCAL_SR = System.get_my_storagerouter()
    LOCAL_ID = System.get_my_machine_id()

    with open(SETTINGS_LOC) as settings_file:
        settings = json.load(settings_file)

    debug_mode = settings["healthcheck"]["debug_mode"]
    enable_logging = settings["healthcheck"]["logging"]["enable"]
    max_log_size = settings["healthcheck"]["max_check_log_size"]
    packages = settings["healthcheck"]["package_list"]
    extra_ports = settings["healthcheck"]["extra_ports"]
    rights_dirs = settings["healthcheck"]["rights_dirs"]
    owners_files = settings["healthcheck"]["owners_files"]
    max_hours_zero_disk_safety = settings["healthcheck"]["max_hours_zero_disk_safety"]

    @staticmethod
    def get_healthcheck_version():
        """
        Gets the installed healthcheck version
        :return: version number of the installed healthcheck
        :rtype: str
        """
        client = SSHClient(System.get_my_storagerouter())
        package_name = 'openvstorage-health-check'
        packages = PackageManager.get_installed_versions(client=client, package_names=[package_name])
        return packages.get(package_name, 'unknown')

    @staticmethod
    def get_local_settings():
        """
        Fetch settings of the local Open vStorage node
        :return: local settings of the node
        :rtype: dict
        """
        # Fetch all details
        local_settings = {'cluster_id': Configuration.get("/ovs/framework/cluster_id"),
                          'hostname': socket.gethostname(),
                          'storagerouter_id': Helper.LOCAL_ID,
                          'storagerouter_type': Helper.LOCAL_SR.node_type,
                          'environment os': ' '.join(platform.linux_distribution())}
        return local_settings
