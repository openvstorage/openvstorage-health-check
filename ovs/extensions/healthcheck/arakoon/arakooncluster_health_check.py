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
Arakoon Health Check module
"""

import time
import uuid
import socket
import subprocess
import ConfigParser
from StringIO import StringIO
from ovs.extensions.generic.system import System
from ovs.log.healthcheck_logHandler import HCLogHandler
from ovs.extensions.healthcheck.utils.extension import Utils
from ovs.dal.lists.storagerouterlist import StorageRouterList
from ovs.extensions.db.etcd.configuration import EtcdConfiguration
from ovs.extensions.storage.persistent.pyrakoonstore import PyrakoonStore
from ovs.extensions.db.arakoon.ArakoonInstaller import ArakoonClusterConfig
from ovs.extensions.db.arakoon.pyrakoon.pyrakoon.compat import ArakoonNotFound, ArakoonNoMaster, ArakoonNoMasterResult


class ArakoonHealthCheck:
    """
    A healthcheck for the arakoon persistent store
    """

    def __init__(self, logging=HCLogHandler(False)):
        """
        Init method for Arakoon health check module

        :param logging: ovs.log.healthcheck_logHandler

        :type logging: Class
        """

        self.module = "arakoon"
        self.utility = Utils()
        self.LOGGER = logging

        self.last_minutes = 5
        self.max_amount_node_restarted = 5

        self.machine_details = System.get_my_storagerouter()

    def fetch_available_clusters(self):
        """
        Fetches the available local arakoon clusters of a cluster

        :return: if succeeded a list; if failed `None`

        :rtype: list
        """

        arakoon_clusters = list(EtcdConfiguration.list('/ovs/{0}'.format(self.module)))

        result = {}
        if len(arakoon_clusters) == 0:
            # no arakoon clusters on node
            self.LOGGER.warning("No installed arakoon clusters detected on this system ...",
                                'arakoon_no_clusters_found', False)
            return None

        # add arakoon clusters
        for cluster in arakoon_clusters:
            # add node that is available for arakoon cluster
            nodes_per_cluster_result = {}

            ak = ArakoonClusterConfig(str(cluster))
            ak.load_config()
            master_node_ids = [node.name for node in ak.nodes]

            if self.machine_details.machine_id not in master_node_ids:
                continue

            for node_id in master_node_ids:
                node_info = StorageRouterList.get_by_machine_id(node_id)

                # add node information
                nodes_per_cluster_result.update({node_id: {
                    'hostname': node_info.name,
                    'ip-address': node_info.ip,
                    'guid': node_info.guid,
                    'node_type': node_info.node_type
                    }
                })
            result.update({cluster: nodes_per_cluster_result})

        return result

    def _check_port_connection(self, port_number):
        """
        Checks the port connection on a IP address

        :param port_number: Port number of a service that is running on the local machine. (Public or loopback)

        :type port_number: int

        :return: True if the port is available; False if the port is NOT available

        :rtype: bool
        """

        # check if port is open
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        result = sock.connect_ex((self.machine_details.ip, int(port_number)))
        if result == 0:
            return True
        else:
            # double check because some services run on localhost
            result = sock.connect_ex(('127.0.0.1', int(port_number)))
            if result == 0:
                return True
            else:
                return False

    def _is_port_listening(self, process_name, port):
        """
        Checks the port connection of a process

        :param process_name: name of a certain process running on this local machine
        :param port: port where the service is running on

        :type process_name: str
        :type port: int
        """

        self.LOGGER.info("Checking port {0} of service {1} ...".format(port, process_name), '_is_port_listening', False)
        if self._check_port_connection(port):
            self.LOGGER.success("Connection successfully established!",
                                'port_{0}_{1}'.format(process_name, port))
        else:
            self.LOGGER.failure("Connection FAILED to service '{1}' on port {0}".format(port, process_name),
                                'port_{0}_{1}'.format(process_name, port))

    def check_required_ports(self):
        """
        Checks all ports of Arakoon nodes (client & server)
        """

        self.LOGGER.info("Checking PORT CONNECTIONS of arakoon nodes ...", 'check_required_ports_arakoon', False)

        for arakoon_cluster in EtcdConfiguration.list('/ovs/arakoon'):
            e = EtcdConfiguration.get('/ovs/arakoon/{0}/config'.format(arakoon_cluster), raw=True)
            config = ConfigParser.RawConfigParser()
            config.readfp(StringIO(e))

            for section in config.sections():
                if section != "global" and section == self.machine_details.machine_id:
                    self._is_port_listening("{0}-{1}"
                                            .format(arakoon_cluster, section), config.get(section, 'client_port'))
                    self._is_port_listening("{0}-{1}"
                                            .format(arakoon_cluster, section), config.get(section, 'messaging_port'))

    def _check_restarts(self, arakoon_overview, last_minutes, max_amount_node_restarted):
        """
        Check the amount of restarts of an Arakoon node
        :param arakoon_overview: Path to Arakoon logfile
        :param last_minutes: Last x minutes to check
        :param max_amount_node_restarted: The amount of restarts

        :return: list with OK and NOK status
        """
        result = {"OK": [], "NOK": []}
        for cluster_name, cluster_info in arakoon_overview.iteritems():
            if self.machine_details.machine_id not in cluster_info:
                continue

            command = 'grep "NODE STARTED" {0} | awk -v d1="$(date --date="-{1} min" +"%F %R")" ' \
                      '-v d2="$(date +"%F %R")" \'$0 > d1 && $0 < d2 || $0 ~ d2\''\
                .format("/var/log/upstart/ovs-arakoon-{0}.log".format(cluster_name), last_minutes)

            out, err = subprocess.Popen(command, shell=True, stdout=subprocess.PIPE).communicate()

            count_node_started = len(out.splitlines())

            if count_node_started >= max_amount_node_restarted:
                result['NOK'].append(cluster_name)

            result['OK'].append(cluster_name)

        return result

    def _verify_integrity(self, arakoon_overview):
        """
        Verifies the integrity of a list of arakoons

        @param arakoon_overview: list of arakoon names

        @type arakoon_overview: list that consists of strings

        @return: (arakoonperfworking_list, arakoonnomaster_list, arakoondown_list, arakoonunknown_list)

        @rtype: tuple that consists of lists
        """

        arakoonunknown_list = []
        arakoonperfworking_list = []
        arakoonnomaster_list = []
        arakoondown_list = []

        # verify integrity of arakoon clusters
        for cluster_name, cluster_info in arakoon_overview.iteritems():
            if self.machine_details.machine_id not in cluster_info:
                continue

            tries = 1
            max_tries = 2  # should be 5 but .nop is taking WAY to long

            while tries <= max_tries:
                self.LOGGER.info("Try {0} on cluster '{1}'".format(tries, cluster_name),
                                 'arakoonTryCheck', False)

                key = 'ovs-healthcheck-{0}'.format(str(uuid.uuid4()))
                value = str(time.time())

                try:
                    # determine if there is a healthy cluster
                    client = PyrakoonStore(str(cluster_name))
                    client.nop()

                    # perform more complicated action to arakoon
                    client.set(key, value)
                    if client.get(key) == value:
                        client.delete(key)
                        arakoonperfworking_list.append(cluster_name)
                        break

                except ArakoonNotFound:
                    if tries == max_tries:
                        arakoondown_list.append(cluster_name)
                        break

                except (ArakoonNoMaster, ArakoonNoMasterResult):
                    if tries == max_tries:
                        arakoonnomaster_list.append(cluster_name)
                        break

                except Exception:
                    if tries == max_tries:
                        arakoonunknown_list.append(cluster_name)
                        break

                # finish try if failed
                tries += 1

        return arakoonperfworking_list, arakoonnomaster_list, arakoondown_list, arakoonunknown_list

    def check_arakoons(self):
        """
        Verifies/validates the integrity of all available arakoons
        """

        self.LOGGER.info("Fetching available arakoon clusters: ", 'checkArakoons', False)
        arakoon_overview = self.fetch_available_clusters()

        if arakoon_overview:
            self.LOGGER.success("{0} available Arakoons successfully fetched, starting verification of clusters ..."
                                .format(len(arakoon_overview)),
                                'arakoon_found')

            ver_result = self._verify_integrity(arakoon_overview)
            if len(ver_result[0]) == len(arakoon_overview):
                self.LOGGER.success("ALL available Arakoon(s) their integrity are/is OK! ",
                                    'arakoon_integrity')
            else:
                # less output for unattended_mode
                if not self.LOGGER.unattended_mode:
                    # check amount OK arakoons
                    if len(ver_result[0]) > 0:
                        self.LOGGER.warning(
                            "{0}/{1} Arakoon(s) is/are OK!: {2}".format(len(ver_result[0]), len(arakoon_overview),
                                                                        ', '.join(ver_result[0])),
                            'arakoon_some_up', False)
                    # check amount NO-MASTER arakoons
                    if len(ver_result[1]) > 0:
                        self.LOGGER.failure("{0} Arakoon(s) cannot find a MASTER: {1}".format(len(ver_result[1]),
                                            ', '.join(ver_result[1])),
                                            'arakoon_no_master_exception'.format(len(ver_result[1])))

                    # check amount DOWN arakoons
                    if len(ver_result[2]) > 0:
                        self.LOGGER.failure("{0} Arakoon(s) seem(s) to be DOWN!: {1}".format(len(ver_result[2]),
                                            ', '.join(ver_result[2])),
                                            'arakoon_down_exception'.format(len(ver_result[2])))

                    # check amount UNKNOWN_ERRORS arakoons
                    if len(ver_result[3]) > 0:
                        self.LOGGER.failure("{0} Arakoon(s) seem(s) to have UNKNOWN ERRORS, please check the logs @"
                                            " '/var/log/ovs/arakoon.log' or"
                                            " '/var/log/upstart/ovs-arakoon-*.log': {1}".format(len(ver_result[3]),
                                                                                                ', '.join(
                                                                                                    ver_result[3])),
                                            'arakoon_unknown_exception')
                else:
                    self.LOGGER.failure("Some Arakoon(s) have problems, please check this!",
                                        'arakoon_integrity')

            log_checks = self._check_restarts(arakoon_overview, self.last_minutes, self.max_amount_node_restarted)

            nok = log_checks['NOK']
            ok = log_checks['OK']

            if len(nok) > 0:
                self.LOGGER.failure("{0} Arakoon(s) restarted more than {1} times in {2} minutes: {3}"
                                    .format(len(nok), self.max_amount_node_restarted, self.last_minutes, ','.join(nok)),
                                    'arakoon_restarts')
            elif len(ok) > 0:
                self.LOGGER.success("ALL Arakoon(s) restart check(s) is/are OK!",
                                    'arakoon_restarts')

        else:
            self.LOGGER.skip("No clusters found", 'arakoon_found')
