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

"""
Title: Arakoon Health Check
Description: Checks the Arakoon cluster and its integrity
"""

"""
Section: Import package(s)
"""

# general packages
import uuid
import time
import sys

# ovs packages
sys.path.append('/opt/OpenvStorage')
from ovs.dal.lists.storagerouterlist import StorageRouterList
from ovs.extensions.storage.persistent.pyrakoonstore import PyrakoonStore
from ovs.extensions.db.arakoon.ArakoonInstaller import ArakoonClusterConfig
from ovs.extensions.db.arakoon.arakoon.ArakoonManagement import ArakoonManagementEx
from ovs.extensions.db.arakoon.pyrakoon.pyrakoon.compat import ArakoonNotFound, ArakoonSockNotReadable, ArakoonSockReadNoBytes, ArakoonSockSendError, ArakoonNoMaster, ArakoonNoMasterResult, ArakoonException

try:
    from ovs.extensions.db.etcd.configuration import EtcdConfiguration
except Exception:
    pass

# import health_check packages
from utils.extension import Utils

"""
Section: Classes
"""


class ArakoonHealthCheck:
    def __init__(self, utility=Utils(False)):
        self.module = "arakoon"
        self.utility = utility

    def _fetchAvailableArakoonClusters(self):
        if self.utility.etcd == False:
            aramex = ArakoonManagementEx()
            arakoon_clusters = aramex.listClusters()
        else:
            arakoon_clusters = list(EtcdConfiguration.list('/ovs/{0}'.format(self.module)))

        result = {}
        if len(arakoon_clusters) != 0:
            # add arakoon clusters
            for cluster in arakoon_clusters:
                # add node that is available for arakoon cluster
                nodes_per_cluster_result = {}

                if self.utility.etcd == False:
                    master_node_ids = aramex.getCluster(str(cluster)).listNodes()
                else:
                    ak = ArakoonClusterConfig(str(cluster))
                    ak.load_config()
                    master_node_ids = list((node.name for node in ak.nodes))

                for node_id in master_node_ids:
                    node_info = StorageRouterList.get_by_machine_id(node_id)

                    # add node information
                    nodes_per_cluster_result.update({node_id: {
                        'hostname': node_info.name,
                        'ip-address': node_info.ip,
                        'guid': node_info.guid,
                        'pmachine_guid': node_info.pmachine_guid,
                        'node_type': node_info.node_type
                        }
                    })
                result.update({cluster: nodes_per_cluster_result})

            return result
        else:
            # no arakoon clusters on node
            self.utility.logger("No installed arakoon clusters detected on this system ...", self.module, 2, 'arakoon_no_clusters_found', False)
            return False

    def _verifyArakoonIntegrity(self, arakoon_overview):
        ArakoonUnknown_list = []
        ArakoonPerfWorking_list = []
        ArakoonNoMaster_list = []
        ArakoonDown_list = []

        # verify integrity of arakoon clusters
        for cluster_name, cluster_info in arakoon_overview.iteritems():

            tries = 1
            max_tries = 2  # should be 5 but .nop is taking WAY to long

            while tries <= max_tries:
                self.utility.logger("Try {0} on cluster '{1}'".format(tries, cluster_name), self.module, 3, 'arakoonTryCheck', False)

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
                        ArakoonPerfWorking_list.append(cluster_name)
                        break

                except ArakoonNotFound:
                    if tries == max_tries:
                        ArakoonDown_list.append(cluster_name)
                        break

                except (ArakoonNoMaster, ArakoonNoMasterResult):
                    if tries == max_tries:
                        ArakoonNoMaster_list.append(cluster_name)
                        break

                except Exception:
                    if tries == max_tries:
                        ArakoonUnknown_list.append(cluster_name)
                        break

                # finish try if failed
                tries += 1

        return ArakoonPerfWorking_list, ArakoonNoMaster_list, ArakoonDown_list, ArakoonUnknown_list

    def checkArakoons(self):
        self.utility.logger("Fetching available arakoon clusters: ", self.module, 3, 'checkArakoons', False)
        try:
            arakoon_overview = self._fetchAvailableArakoonClusters()

            # fetch overview of arakoon clusters on local node
            if arakoon_overview:
                self.utility.logger(
                    "{0} available Arakoons successfully fetched, starting verification of clusters ...".format(
                        len(arakoon_overview)), self.module, 1, 'arakoon_amount_on_cluster {0}'.format(len(arakoon_overview)), False)
                ver_result = self._verifyArakoonIntegrity(arakoon_overview)
                if len(ver_result[0]) == len(arakoon_overview):
                    self.utility.logger("ALL available Arakoon(s) their integrity are/is OK! ", self.module, 1, 'arakoon_integrity')
                else:
                    # less output for unattended_mode
                    if not self.utility.unattended_mode:
                        # check amount OK arakoons
                        if len(ver_result[0]) > 0:
                            self.utility.logger(
                                "{0} Arakoon(s) is/are OK!: {1}".format(len(ver_result[0]), ', '.join(ver_result[0])),
                                self.module, 1, 'arakoon_some_up', False)
                        # check amount NO-MASTER arakoons
                        if len(ver_result[1]) > 0:
                            self.utility.logger("{0} Arakoon(s) cannot find a MASTER: {1}".format(len(ver_result[1]),
                                                                                                   ', '.join(
                                                                                                           ver_result[1])),
                                                 self.module, 0, 'arakoon_no_master_exception'.format(len(ver_result[1])))

                        # check amount DOWN arakoons
                        if len(ver_result[2]) > 0:
                            self.utility.logger("{0} Arakoon(s) seem(s) to be DOWN!: {1}".format(len(ver_result[2]),
                                                                                                  ', '.join(ver_result[2])),
                                                 self.module, 0, 'arakoon_down_exception'.format(len(ver_result[2])))

                        # check amount UNKNOWN_ERRORS arakoons
                        if len(ver_result[3]) > 0:
                            self.utility.logger(
                                "{0} Arakoon(s) seem(s) to have UNKNOWN ERRORS, please check the logs @ "
                                "'/var/log/ovs/arakoon.log' or '/var/log/upstart/ovs-arakoon-*.log': {1}".format(
                                    len(ver_result[3]), ', '.join(ver_result[3])), self.module, 0,
                                    'arakoon_unknown_exception')
                    else:
                        self.utility.logger("Some Arakoon(s) have problems, please check this!", self.module, 0,
                                            'arakoon_integrity')
            else:
                self.utility.logger("No clusters found on this node, so stopping arakoon checks ...", self.module, 5,
                                    'arakoon_integrity')
        except Exception as e:
            self.utility.logger("One ore more Arakoon clusters cannot be reached :(, due to: {0}".format(e),
                                 self.module, 4, 'arakoon_integrity')
