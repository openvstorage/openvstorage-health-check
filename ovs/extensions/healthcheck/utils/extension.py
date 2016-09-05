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
Utilities module for OVS health check
"""

import json
import commands
from ovs.extensions.generic.system import System
from ovs.extensions.generic.sshclient import SSHClient
from ovs.extensions.services.service import ServiceManager

MODULE = "utils"
SETTINGS_LOC = "/opt/OpenvStorage/config/healthcheck/settings.json"


class _Colors:
    """
    Colors for Open vStorage healthcheck logging
    """

    OKBLUE = '\033[94m'
    OKGREEN = '\033[92m'
    WARNING = '\033[93m'
    FAIL = '\033[91m'
    SKIP = '\033[95m'
    ENDC = '\033[0m'

    def __init__(self):
        """ Init method """

        pass


class Utils:
    """
    General utilities for Open vStorage healthcheck
    """

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
    client = SSHClient('127.0.0.1', username='root')

    def __init__(self):
        """ Init method """
        pass

    def get_config_file_path(self, name, node_id, product, guid=None):
        """
        Gets the location of a certain service via local or etcd path

        :param name: name of the PRODUCT (e.g. vpool01 or backend01-abm)
        :param node_id: the ID of the local node
        :param product: the id of the desired product
            * arakoon = 0
            * vpool = 1
            * alba_backend = 2
            * alba_asd = 3
            * ovs framework = 4
        :param guid: guid of a certain vpool (only required if one desires the config of a vpool)

        :type name: str
        :type node_id: str
        :type product: int
        :type guid: str

        :return: location of a config file

        :rtype: str
        """

        # INFO
        # guid is only for volumedriver (vpool) config and proxy configs

        # fetch config file through etcd or local

        # product_name:
        #
        # arakoon = 0
        # vpool = 1
        # alba_backends = 2
        # alba_asds = 3
        # ovs = 4
        etcd_status = self.check_etcd()

        if not etcd_status:
            if product == 0:
                return "/opt/OpenvStorage/config/arakoon/{0}/{0}.cfg".format(name)
            elif product == 1:
                return "/opt/OpenvStorage/config/storagedriver/storagedriver/{0}.json".format(name)
            elif product == 4:
                return "/opt/OpenvStorage/config/ovs.json"
        else:
            if product == 0:
                return "etcd://127.0.0.1:2379/ovs/arakoon/{0}/config".format(name)
            elif product == 1:
                if not guid and etcd_status:
                    raise Exception("You must provide a 'vPOOL_guid' for ETCD, currently this is 'None'")
                else:
                    return "etcd://127.0.0.1:2379/ovs/vpools/{0}/hosts/{1}/config".format(guid, name+node_id)
            elif product == 4:
                return "etcd://127.0.0.1:2379/ovs/framework"

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
        Gets the VERSION of the Open vStorage cluster

        :return: version of openvstorage cluster

        :rtype: str
        """

        with open("/opt/OpenvStorage/webapps/frontend/locales/en-US/ovs.json") as ovs_json:
            ovs = json.load(ovs_json)

        return ovs["releasename"]

    def get_cluster_id(self):
        """
        Gets the cluster ID of the Open vStorage cluster

        :return: cluster id of openvstorage cluster

        :rtype: str
        """

        if self.check_etcd():
            return self.get_etcd_information_by_location("/ovs/framework/cluster_id")[0].translate(None, '\"')
        else:
            with open("/opt/OpenvStorage/config/ovs.json") as ovs_json:
                ovs = json.load(ovs_json)

            return ovs["support"]["cid"]

    @staticmethod
    def check_etcd():
        """
        Detects if ETCD is available on the local machine

        :return: result if ETCD is available on the local machine

        :rtype: bool
        """

        if commands.getoutput("dpkg -l | grep etcd")[0] == '':
            return False
        else:
            return True

    @staticmethod
    def get_etcd_information_by_location(location):
        """
        Gets information from etcd by ABSOLUTE location (e.g. /ovs/framework)

        :param location: a etcd location

        :type location: str

        :return: result of file in etcd

        :rtype: list
        """

        return commands.getoutput("etcdctl get {0}".format(location))

    def check_status_of_service(self, service_name):
        """
        Gets the status of a linux service

        :param service_name: name of a linux service

        :type service_name: str

        :return: status of the service

        :rtype: bool
        """

        return ServiceManager.get_service_status(str(service_name), self.client)
