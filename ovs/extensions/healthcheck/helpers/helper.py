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
import socket

from ovs.extensions.generic.system import System
from ovs.extensions.generic.sshclient import SSHClient
from ovs.extensions.services.service import ServiceManager
from ovs.extensions.generic.configuration import Configuration


class Helper(object):
    """
    Helper module
    """
    MODULE = "utils"
    SETTINGS_LOC = "/opt/OpenvStorage/config/healthcheck/settings.json"

    with open(SETTINGS_LOC) as settings_file:
        settings = json.load(settings_file)

    debug_mode = settings["healthcheck"]["debug_mode"]
    enable_logging = settings["healthcheck"]["logging"]["enable"]
    max_log_size = settings["healthcheck"]["max_check_log_size"]
    packages = settings["healthcheck"]["package_list"]
    extra_ports = settings["healthcheck"]["extra_ports"]
    rights_dirs = settings["healthcheck"]["rights_dirs"]
    owners_files = settings["healthcheck"]["owners_files"]
    check_logs = settings["healthcheck"]["check_logs"]

    @staticmethod
    def get_ovs_type():
        """
        Gets the TYPE of the Open vStorage local node

        :return: TYPE of openvstorage local node
            * MASTER
            * EXTRA
        :rtype: str
        """

        return System.get_my_storagerouter().node_type

    @staticmethod
    def get_ovs_version():
        """
        Gets the RELEASE & BRANCH of the Open vStorage cluster

        :return: RELEASE & BRANCH of openvstorage cluster
        :rtype: tuple
        """

        with open("/opt/OpenvStorage/webapps/frontend/locales/en-US/ovs.json") as ovs_json1:
            ovs_releasename = json.load(ovs_json1)["releasename"]

        with open("/etc/apt/sources.list.d/ovsaptrepo.list") as ovs_json2:
            ovs_current_version = ovs_json2.read().split()[2]

        return ovs_releasename, ovs_current_version

    @staticmethod
    def get_cluster_id():
        """
        Gets the cluster ID of the Open vStorage cluster

        :return: cluster id of openvstorage cluster
        :rtype: str
        """

        return Configuration.get("/ovs/framework/cluster_id")

    @staticmethod
    def check_status_of_service(service_name):
        """
        Gets the status of a linux service
        :param service_name: name of a linux service
        :type service_name: str
        :return: status of the service
        :rtype: bool
        """
        local_machine = System.get_my_storagerouter()
        client = SSHClient(local_machine.ip, username='root')
        return ServiceManager.get_service_status(str(service_name), client)

    @staticmethod
    def check_port_connection(port_number, ip):
        """
        Checks the port connection on a IP address

        :param port_number: Port number of a service that is running on the local machine. (Public or loopback)
        :type port_number: int
        :param ip: ip address to try
        :type ip: str
        :return: True if the port is available; False if the port is NOT available
        :rtype: bool
        """

        # check if port is open
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        result = sock.connect_ex((ip, int(port_number)))
        if result == 0:
            return True
        else:
            # double check because some services run on localhost
            result = sock.connect_ex(('127.0.0.1', int(port_number)))
            if result == 0:
                return True
            else:
                return False
