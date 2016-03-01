#!/usr/bin/python

# Copyright 2014 iNuron NV
#
# Licensed under the Open vStorage Modified Apache License (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.openvstorage.org/license
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""
Title: Utils
Description: Utilities for OVS health check
"""

"""
Section: Import package(s)
"""

# general packages
import subprocess
import xmltodict
import datetime
import commands
import json
import os

# ovs packages
from ovs.extensions.services.service import ServiceManager
from ovs.extensions.generic.sshclient import SSHClient
from ovs.extensions.generic.system import System

"""
Section: Classes
"""


class _Colors:
    OKBLUE = '\033[94m'
    OKGREEN = '\033[92m'
    WARNING = '\033[93m'
    FAIL = '\033[91m'
    SKIP = '\033[95m'
    ENDC = '\033[0m'


class Utils:
    def __init__(self, unattended_mode):
        # module specific
        self.module = "utils"

        # load config file
        PARENT = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), os.pardir))
        with open("{0}/conf/settings.json".format(PARENT)) as settings_file:
            self.settings = json.load(settings_file)

        # fetch from config file
        self.HEALTHCHECK_DIR = self.settings["healthcheck"]["logging"]["directory"]
        self.HEALTHCHECK_FILE = self.settings["healthcheck"]["logging"]["file"]
        self.debug = self.settings["healthcheck"]["debug_mode"]
        self.max_log_size = self.settings["healthcheck"]["max_check_log_size"]  # in MB

        # open ovs ssh client
        self.client = SSHClient('127.0.0.1', username='root')

        # init at runtime
        self.etcd = self.detectEtcd()
        self.serviceManager = self.detectServiceManager()
        self.node_type = self.detectOvsType()
        self.ovs_version = self.detectOvsVersion()
        self.cluster_id = self.getClusterId()

        # fetched from main.py
        self.unattended_mode = unattended_mode

        # HC counters
        self.failure = 0
        self.success = 0
        self.warning = 0
        self.info = 0
        self.exception = 0
        self.skip = 0
        self.debug = 0

        # create if dir does not exists
        if not os.path.isdir(self.HEALTHCHECK_DIR):
            os.makedirs(self.HEALTHCHECK_DIR)

    def fetchConfigFilePath(self, name, node_id, product, guid=None):

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


    def detectOvsType(self):
        return System.get_my_storagerouter().node_type

    def detectOvsVersion(self):
        with open("/opt/OpenvStorage/webapps/frontend/locales/en-US/ovs.json") as ovs_json:
            ovs = json.load(ovs_json)

        return ovs["releasename"]

    def getClusterId(self):

        if self.etcd:
            return self.getEtcdInformation("/ovs/framework/cluster_id")[0].translate(None, '\"')
        else:
            with open("/opt/OpenvStorage/config/ovs.json") as ovs_json:
                ovs = json.load(ovs_json)

            return ovs["support"]["cid"]

    def detectEtcd(self):
        result = self.executeBashCommand("dpkg -l | grep etcd")

        if result[0] == '':
            return False
        else:
            return True

    def getEtcdInformation(self, location):
        return self.executeBashCommand("etcdctl get {0}".format(location))

    def parseXMLtoJSON(self, xml):
        # dumps converts to general json, loads converts to python value
        return json.loads(json.dumps(xmltodict.parse(str(xml))))

    def getStatusOfService(self, service_name):
        return ServiceManager.get_service_status(str(service_name), self.client)

    def executeBashCommand(self, cmd, subpro=False):
        if not subpro:
            return commands.getstatusoutput(str(cmd))[1].split('\n')
        else:
            return subprocess.check_output(str(cmd), stderr=subprocess.STDOUT, shell=True)

    def detectServiceManager(self):

        # service_types:
        #
        # init = 1
        # systemd = 0
        # other(s) (not supported) = -1

        # detects what service manager your system has
        DETSYS = "pidof systemd && echo 'systemd' || pidof /sbin/init && echo 'sysvinit' || echo 'other'"
        OUTPUT = commands.getoutput(DETSYS)

        # process output
        if 'systemd' in OUTPUT:
            return 0
        elif 'sysvinit':
            return 1
        else:
            raise Exception("Unsupported Service Manager detected, please contact support or file a bug @github")

    def logger(self, message, module, log_type, unattended_mode_name, unattended_print_mode=True):

        # unattended_print_mode & unattended_mode_name are required together
        #
        # log_types:
        #
        # failure = 0
        # success = 1
        # warning = 2
        # info = 3
        # exception = 4
        # skip = 5
        # debug = 6

        try:
            target = open('{0}/{1}'.format(self.HEALTHCHECK_DIR, self.HEALTHCHECK_FILE), 'a')
            now = datetime.datetime.now()

            if log_type == 0:
                target.write("{0} - [FAILURE] - [{1}] - {2}\n".format(now, module, message))
                self.failure += 1
                if self.unattended_mode:
                    if unattended_print_mode:
                        print "{0} FAILURE".format(unattended_mode_name)
                else:
                    print _Colors.FAIL + "[FAILURE] " + _Colors.ENDC + "%s" % (str(message))
            elif log_type == 1:
                target.write("{0} - [SUCCESS] - [{1}] - {2}\n".format(now, module, message))
                self.success += 1
                if self.unattended_mode:
                    if unattended_print_mode:
                        print "{0} SUCCESS".format(unattended_mode_name)
                else:
                    print _Colors.OKGREEN + "[SUCCESS] " + _Colors.ENDC + "%s" % (str(message))
            elif log_type == 2:
                target.write("{0} - [WARNING] - [{1}] - {2}\n".format(now, module, message))
                self.warning += 1
                if self.unattended_mode:
                    if unattended_print_mode:
                        print "{0} WARNING".format(unattended_mode_name)
                else:
                    print _Colors.WARNING + "[WARNING] " + _Colors.ENDC + "%s" % (str(message))
            elif log_type == 3:
                target.write("{0} - [INFO] - [{1}] - {2}\n".format(now, module, message))
                self.info += 1
                if self.unattended_mode:
                    if unattended_print_mode:
                        print "{0} INFO".format(unattended_mode_name)
                else:
                    print _Colors.OKBLUE + "[INFO] " + _Colors.ENDC + "%s" % (str(message))
            elif log_type == 4:
                target.write("{0} - [EXCEPTION] - [{1}] - {2}\n".format(now, module, message))
                self.exception += 1
                if self.unattended_mode:
                    if unattended_print_mode:
                        print "{0} EXCEPTION".format(unattended_mode_name)
                else:
                    print _Colors.FAIL + "[EXCEPTION] " + _Colors.ENDC + "%s" % (str(message))
            elif log_type == 5:
                target.write("{0} - [SKIPPED] - [{1}] - {2}\n".format(now, module, message))
                self.skip += 1
                if self.unattended_mode:
                    if unattended_print_mode:
                        print "{0} SKIPPED".format(unattended_mode_name)
                else:
                    print _Colors.SKIP + "[SKIPPED] " + _Colors.ENDC + "%s" % (str(message))
            elif log_type == 6:
                if self.debug:
                    target.write("{0} - [DEBUG] - [{1}] - {2}\n".format(now, module, message))
                    self.debug += 1
                    print _Colors.OKBLUE + "[DEBUG] " + _Colors.ENDC + "%s" % (str(message))
            else:
                target.write("{0} - [UNEXPECTED_EXCEPTION] - [{1}] - {2}\n".format(now, module, message))
                self.exception += 1
                if self.unattended_mode:
                    if unattended_print_mode:
                        print "{0} UNEXPECTED_EXCEPTION".format(unattended_mode_name)
                else:
                    print _Colors.FAIL + "[UNEXPECTED_EXCEPTION] " + _Colors.ENDC + "%s" % (str(message))
            target.close()

        except Exception, e:
            print "An unexpected exception occured during logging in '{0}': \n{1}".format(self.HEALTHCHECK_DIR, e)


"""
Section: Main
"""
