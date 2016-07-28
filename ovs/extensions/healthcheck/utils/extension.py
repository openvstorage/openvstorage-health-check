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

import subprocess
import xmltodict
import commands
import json
from ovs.extensions.services.service import ServiceManager
from ovs.extensions.generic.sshclient import SSHClient
from ovs.extensions.generic.system import System


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

    SETTINGS_LOC = "/opt/OpenvStorage/config/healthcheck/settings.json"

    def __init__(self):
        """ Init method """

        # module specific
        self.module = "utils"

        # load config file
        with open(self.SETTINGS_LOC) as settings_file:
            self.settings = json.load(settings_file)

        # fetch from config file
        self.debug = self.settings["healthcheck"]["debug_mode"]
        self.max_log_size = self.settings["healthcheck"]["max_check_log_size"]  # in MB

        # open ovs ssh client
        self.client = SSHClient('127.0.0.1', username='root')

        # init at runtime
        self.etcd = self.check_etcd()
        self.serviceManager = self.get_service_manager()
        self.node_type = self.get_ovs_type()
        self.ovs_version = self.get_ovs_version()
        self.cluster_id = self.get_cluster_id()

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

        if not self.etcd:
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
                if not guid and self.etcd:
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

        if self.etcd:
            return self.get_etcd_information_by_location("/ovs/framework/cluster_id")[0].translate(None, '\"')
        else:
            with open("/opt/OpenvStorage/config/ovs.json") as ovs_json:
                ovs = json.load(ovs_json)

            return ovs["support"]["cid"]

    def check_etcd(self):
        """
        Detects if ETCD is available on the local machine

        :return: result if ETCD is available on the local machine

        :rtype: bool
        """

        result = self.execute_bash_command("dpkg -l | grep etcd")

        if result[0] == '':
            return False
        else:
            return True

    def get_etcd_information_by_location(self, location):
        """
        Gets information from etcd by ABSOLUTE location (e.g. /ovs/framework)

        :param location: a etcd location

        :type location: str

        :return: result of file in etcd

        :rtype: list
        """

        return self.execute_bash_command("etcdctl get {0}".format(location))

    @staticmethod
    def convert_xml_to_json(xml):
        """
        Converts XML to JSON

        :param xml: a xml file

        :type: str

        :return: json file

        :rtype: json
        """

        # dumps converts to general json, loads converts to python value
        return json.loads(json.dumps(xmltodict.parse(str(xml))))

    def check_status_of_service(self, service_name):
        """
        Gets the status of a linux service

        :param service_name: name of a linux service

        :type service_name: str

        :return: status of the service

        :rtype: bool
        """

        return ServiceManager.get_service_status(str(service_name), self.client)

    @staticmethod
    def execute_bash_command(cmd, subpro=False):
        """
        Execute a bash command through a standard way, already processed and served on a silver platter

        :param cmd: a bash command
        :param subpro: determines if you are using subprocess or commands module
            * Bash piping or other special cases: False (use commands)
            * General bash command: True (use subprocess)

        :type cmd: str
        :type subpro: bool

        :return: bash command output

        :rtype: list
        """

        if not subpro:
            return commands.getstatusoutput(str(cmd))[1].split('\n')
        else:
            return subprocess.check_output(str(cmd), stderr=subprocess.STDOUT, shell=True)

    @staticmethod
    def get_service_manager():
        """
        Detects the Service Manager on the local system

        :return: systemd or init/upstart
            * systemd = 0
            * init/upstart = 1

        :rtype: int

        :raises RuntimeError
        """

        # detects what service manager your system has
        det_sys = "pidof systemd && echo 'systemd' || pidof /sbin/init && echo 'sysvinit' || echo 'other'"
        result = commands.getoutput(det_sys)

        # process output
        if 'systemd' in result:
            return 0
        elif 'sysvinit':
            return 1
        else:
            raise RuntimeError("Unsupported Service Manager detected, please contact support or file a bug @github")


