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

import os
import time
import uuid
import socket
import subprocess
import ConfigParser
from StringIO import StringIO
from datetime import date, timedelta, datetime
from ovs.extensions.generic.system import System
from ovs.extensions.healthcheck.utils.helper import Helper
from ovs.dal.lists.storagerouterlist import StorageRouterList
from ovs.extensions.generic.configuration import Configuration
from ovs.extensions.storage.persistent.pyrakoonstore import PyrakoonStore
from ovs.extensions.db.arakoon.ArakoonInstaller import ArakoonClusterConfig
from ovs.extensions.db.arakoon.pyrakoon.pyrakoon.compat import ArakoonNotFound, ArakoonNoMaster, ArakoonNoMasterResult
# Test exposetocli
from ovs.extensions.healthcheck.decorators import ExposeToCli


class ArakoonHealthCheck(object):
    """
    A healthcheck for the arakoon persistent store
    """
    MODULE = "arakoon"
    LAST_MINUTES = 5
    MAX_AMOUNT_NODE_RESTARTED = 5
    # oldest tlx files may not older than x days. If they are - failed collapse
    MAX_COLLAPSE_AGE = 2
    MACHINE_DETAILS = System.get_my_storagerouter()

    @staticmethod
    def _is_port_listening(logger, process_name, port, ip=MACHINE_DETAILS.ip):
        """
        Checks the port connection of a process

        :param logger: logging object
        :type logger: ovs.log.healthcheck_logHandler.HCLogHandler
        :param process_name: name of a certain process running on this local machine
        :type process_name: str
        :param port: port where the service is running on
        :type port: int
        :param ip: ip address to try
        :type ip: str
        """
        logger.info("Checking port {0} of service {1} ...".format(port, process_name), '_is_port_listening')
        if Helper.check_port_connection(port, ip):
            logger.success("Connection successfully established!",
                           'port_{0}_{1}'.format(process_name, port))
        else:
            logger.failure("Connection FAILED to service '{1}' on port {0}".format(port, process_name),
                           'port_{0}_{1}'.format(process_name, port))

    @staticmethod
    def fetch_available_clusters(logger):
        """
        Fetches the available local arakoon clusters of a cluster

        :param logger: logging object
        :type logger: ovs.log.healthcheck_logHandler.HCLogHandler
        :return: if succeeded a dict; if failed `None`
        :rtype: dict
        """

        logger.info("Fetching available arakoon clusters: ", 'checkArakoons')
        arakoon_clusters = list(Configuration.list('/ovs/arakoon'))

        result = {}
        if len(arakoon_clusters) == 0:
            # no arakoon clusters on node
            logger.warning("No installed arakoon clusters detected on this system ...", 'arakoon_no_clusters_found')
            return {}

        # add arakoon clusters
        for cluster in arakoon_clusters:
            # add node that is available for arakoon cluster
            nodes_per_cluster_result = {}

            ak = ArakoonClusterConfig(str(cluster), filesystem=False)
            ak.load_config()
            master_node_ids = [node.name for node in ak.nodes]

            if ArakoonHealthCheck.MACHINE_DETAILS.machine_id not in master_node_ids:
                continue

            try:
                tlog_dir = ak.export()[ArakoonHealthCheck.MACHINE_DETAILS.machine_id]['tlog_dir']
            except KeyError, ex:
                logger.failure("Key {0} not found.".format(ex.message))
                continue

            for node_id in master_node_ids:
                node_info = StorageRouterList.get_by_machine_id(node_id)

                # add node information
                nodes_per_cluster_result.update({node_id: {
                    'hostname': node_info.name,
                    'ip-address': node_info.ip,
                    'guid': node_info.guid,
                    'node_type': node_info.node_type,
                    'tlog_dir': tlog_dir
                    }
                })
            result.update({cluster: nodes_per_cluster_result})

        return result

    @staticmethod
    @ExposeToCli('arakoon', 'required-ports-test')
    def check_required_ports(logger):
        """
        Checks all ports of Arakoon nodes (client & server)

        :param logger: logging object
        :type logger: ovs.log.healthcheck_logHandler.HCLogHandler
        """
        logger.info("Checking PORT CONNECTIONS of arakoon nodes ...", 'check_required_ports_arakoon')

        for arakoon_cluster in Configuration.list('/ovs/arakoon'):
            e = Configuration.get('/ovs/arakoon/{0}/config'.format(arakoon_cluster), raw=True)
            config = ConfigParser.RawConfigParser()
            config.readfp(StringIO(e))

            for section in config.sections():
                if section != "global" and section == ArakoonHealthCheck.MACHINE_DETAILS.machine_id:
                    process_name = "{0}-{1}".format(arakoon_cluster, section)
                    ports = [config.get(section, 'client_port'), config.get(section, 'messaging_port')]
                    for port in ports:
                        logger.info("Checking port {0} of service {1} ...".format(port, process_name), '_is_port_listening')
                        ArakoonHealthCheck._is_port_listening(logger, process_name, port, ArakoonHealthCheck.MACHINE_DETAILS.ip)

    @staticmethod
    @ExposeToCli('arakoon', 'restart-test')
    def check_restarts(logger, arakoon_clusters=None, last_minutes=LAST_MINUTES, max_amount_node_restarted=MAX_AMOUNT_NODE_RESTARTED):
        """
        Check the amount of restarts of an Arakoon node
        :param logger: Logger instance
        :type logger: ovs.log.healthcheck_logHandler.HCLogHandler
        :param arakoon_clusters: List of available Arakoons
        :type arakoon_clusters: dict
        :param last_minutes: Last x minutes to check
        :type last_minutes: int
        :param max_amount_node_restarted: The amount of restarts
        :type max_amount_node_restarted: int
        :return: list with OK and NOK status
        """

        if arakoon_clusters is None:
            arakoon_clusters = ArakoonHealthCheck.fetch_available_clusters(logger)

        result = {"OK": [], "NOK": []}
        for cluster_name, cluster_info in arakoon_clusters.iteritems():
            if ArakoonHealthCheck.MACHINE_DETAILS.machine_id not in cluster_info:
                continue
            # @todo use log reader to fetch info
            command = 'grep "NODE STARTED" {0} | awk -v d1="$(date --date="-{1} min" +"%F %R")" ' \
                      '-v d2="$(date +"%F %R")" \'$0 > d1 && $0 < d2 || $0 ~ d2\''\
                .format("/var/log/upstart/ovs-arakoon-{0}.log".format(cluster_name), last_minutes)

            out, err = subprocess.Popen(command, shell=True, stdout=subprocess.PIPE).communicate()

            count_node_started = len(out.splitlines())

            if count_node_started >= max_amount_node_restarted:
                result['NOK'].append(cluster_name)

            result['OK'].append(cluster_name)

        return result

    @staticmethod
    @ExposeToCli('arakoon', 'collapse-test')
    def check_collapse(logger, arakoon_clusters=None, max_collapse_age=MAX_COLLAPSE_AGE):
        """
        Check collapsing of arakoon

        :param logger: logging object
        :type logger: ovs.log.healthcheck_logHandler.HCLogHandler
        :param arakoon_clusters: List of available Arakoons
        :type arakoon_clusters: dict
        :param max_collapse_age: tlx files may not be longer than x days
        :type max_collapse_age: int
        :return: list with OK, NOK status
        :rtype: list
        """

        result = {"OK": [], "NOK": []}
        # tlx file must have young timestamp than this one.
        max_age_timestamp = time.mktime((date.today() - timedelta(days=max_collapse_age)).timetuple())

        for arakoon, arakoon_nodes in arakoon_clusters.iteritems():
            for node, config in arakoon_nodes.iteritems():
                if node != ArakoonHealthCheck.MACHINE_DETAILS.machine_id:
                    continue

                try:
                    tlog_dir = config['tlog_dir']
                    files = os.listdir(tlog_dir)
                except OSError, ex:
                    if not logger.print_progress:
                        logger.failure("File or directory not found: {0}".format(ex), 'arakoon_path')
                    result["NOK"].append(arakoon)
                    continue

                if len(files) == 0:
                    result["NOK"].append(arakoon)
                    if not logger.print_progress:
                        logger.failure("No files found in {0}".format(tlog_dir), 'arakoon_files')
                    continue

                if 'head.db' in files:
                    head_db_stats = os.stat('{0}/head.db'.format(tlog_dir))
                    if head_db_stats.st_mtime > max_age_timestamp:
                        result["OK"].append(arakoon)
                        continue

                tlx_files = [(int(tlx_file.replace('.tlx', '')), tlx_file) for tlx_file in files
                             if tlx_file.endswith('.tlx')]
                amount_tlx = len(tlx_files)

                # Discussed with Arakoon team. Min tlx files must be 3 before checking time
                if amount_tlx < 3 and len([tlog_file for tlog_file in files if tlog_file.endswith('.tlog')]) > 0:
                    logger.info("Found less than 3 tlogs for '{0}', collapsing is not worth doing.".format(arakoon))
                    result['OK'].append(arakoon)
                    continue
                elif amount_tlx == 0 and len([tlog_file for tlog_file in files if tlog_file.endswith('.tlog')]) < 0:
                    result['NOK'].append(arakoon)
                    if not logger.print_progress:
                        logger.failure("No tlx files found and head.db is out of sync or is not present in {0}.".format(tlog_dir), 'arakoon_tlx_path')
                    continue

                tlx_files.sort(key=lambda tup: tup[0])
                oldest_file = tlx_files[0][1]

                try:
                    oldest_tlx_stats = os.stat('{0}/{1}'.format(tlog_dir, oldest_file))
                except OSError, ex:
                    if not logger.print_progress:
                        logger.failure("File or directory not found: {0}".format(ex), 'arakoon_tlx_path')
                    result["NOK"].append(arakoon)
                    continue

                if oldest_tlx_stats.st_mtime > max_age_timestamp:
                    logger.info("Found less than 3 tlogs for '{0}', collapsing is not worth doing.".format(arakoon))
                    result["OK"].append(arakoon)
                    continue

                if logger.print_progress:
                    datetime_oldest_file = datetime.fromtimestamp(oldest_tlx_stats.st_mtime).isoformat()
                    datetime_old_date = datetime.fromtimestamp(max_age_timestamp).isoformat()
                    logger.failure("oldest file: {0} with timestamp: {1} is older than {2} for arakoon {3}"
                                   .format(oldest_file, datetime_oldest_file,
                                           datetime_old_date, arakoon), 'arakoon_oldest_file')

                result['NOK'].append(arakoon)

        # Testing conditions
        if len(result['NOK']) > 0:
            logger.failure("{0} Arakoon(s) having issues with collapsing: {1}".format(len(result['NOK']), ','.join(result['NOK'])),
                           'arakoon_collapse')
        elif len(result['OK']) > 0:
            logger.success("ALL Arakoon(s) are collapsed.", 'arakoon_collapse')
        return result

    @staticmethod
    @ExposeToCli('arakoon', 'integrity-test')
    def verify_integrity(logger, arakoon_clusters=None):
        """
        Verifies the integrity of a list of arakoons

        :param logger: logging object
        :type logger: ovs.log.healthcheck_logHandler.HCLogHandler
        :param arakoon_clusters: list of arakoon names
        :type arakoon_clusters: list that consists of strings
        :return: (working_arakoon_list, no_master_arakoon_list, down_arakoon_list, unkown_arakoon_list)
        :rtype: tuple > lists
        """
        unkown_arakoon_list = []
        working_arakoon_list = []
        no_master_arakoon_list = []
        down_arakoon_list = []

        if arakoon_clusters is None:
            arakoon_clusters = ArakoonHealthCheck.fetch_available_clusters(logger)

        logger.info('Starting Arakoon integrity test')
        # verify integrity of arakoon clusters
        for cluster_name, cluster_info in arakoon_clusters.iteritems():
            if ArakoonHealthCheck.MACHINE_DETAILS.machine_id not in cluster_info:
                continue

            tries = 1
            max_tries = 2  # should be 5 but .nop is taking WAY to long

            while tries <= max_tries:
                logger.info("Executing testing cluster '{0}'. Will try a maximum amount of {1} tries."
                            " Currently on try {2}".format(cluster_name, max_tries, tries), 'arakoonTryCheck')

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
                        working_arakoon_list.append(cluster_name)
                        break

                except ArakoonNotFound:
                    if tries == max_tries:
                        down_arakoon_list.append(cluster_name)
                        break

                except (ArakoonNoMaster, ArakoonNoMasterResult):
                    if tries == max_tries:
                        no_master_arakoon_list.append(cluster_name)
                        break

                except Exception:
                    if tries == max_tries:
                        unkown_arakoon_list.append(cluster_name)
                        break

                # finish try if failed
                tries += 1

        # Processing results
        ver_result = working_arakoon_list, no_master_arakoon_list, down_arakoon_list, unkown_arakoon_list
        if len(ver_result[0]) == len(arakoon_clusters):
            logger.success("ALL available Arakoon(s) their integrity are/is OK! ", 'arakoon_integrity')
        else:
            # less output for unattended_mode
            # check amount OK arakoons
            if len(ver_result[0]) > 0:
                logger.warning(
                    "{0}/{1} Arakoon(s) is/are OK!: {2}".format(len(ver_result[0]), len(arakoon_clusters),
                                                                ', '.join(ver_result[0])), 'arakoon_some_up')
            # check amount NO-MASTER arakoons
            if len(ver_result[1]) > 0:
                logger.failure("{0} Arakoon(s) cannot find a MASTER: {1}".format(len(ver_result[1]),
                                                                                 ', '.join(ver_result[1])),
                               'arakoon_no_master_exception'.format(len(ver_result[1])))

            # check amount DOWN arakoons
            if len(ver_result[2]) > 0:
                logger.failure("{0} Arakoon(s) seem(s) to be DOWN!: {1}".format(len(ver_result[2]),
                                                                                ', '.join(ver_result[2])),
                               'arakoon_down_exception'.format(len(ver_result[2])))

            # check amount UNKNOWN_ERRORS arakoons
            if len(ver_result[3]) > 0:
                logger.failure("{0} Arakoon(s) seem(s) to have UNKNOWN ERRORS, please check the logs @"
                               " '/var/log/ovs/arakoon.log' or"
                               " '/var/log/upstart/ovs-arakoon-*.log': {1}".format(len(ver_result[3]),
                                                                                   ', '.join(
                                                                                       ver_result[3])),
                               'arakoon_unknown_exception')
            else:
                logger.failure("Some Arakoon(s) have problems, please check this!", 'arakoon_integrity')

        return working_arakoon_list, no_master_arakoon_list, down_arakoon_list, unkown_arakoon_list

    @staticmethod
    @ExposeToCli('arakoon', 'check-arakoons')
    def check_arakoons(logger):
        """
        Verifies/validates the integrity of all available arakoons

        :param logger: logging object
        :type logger: ovs.log.healthcheck_logHandler.HCLogHandler
        """

        arakoon_clusters = ArakoonHealthCheck.fetch_available_clusters(logger)

        if len(arakoon_clusters.keys()) != 0:
            logger.success("{0} available Arakoons successfully fetched, starting verification of clusters ..."
                           .format(len(arakoon_clusters)), 'arakoon_found')

            ArakoonHealthCheck.check_collapse(logger=logger, arakoon_clusters=arakoon_clusters)
            ArakoonHealthCheck.verify_integrity(logger=logger, arakoon_clusters=arakoon_clusters)
            ArakoonHealthCheck.check_restarts(logger=logger, arakoon_clusters=arakoon_clusters)

        else:
            logger.skip("No clusters found", 'arakoon_found')

    @staticmethod
    @ExposeToCli('arakoon', 'test')
    def run(logger):
        """
        Method to run the full Arakoon Healthcheck sequence
        :param logger: logging object
        :type logger: ovs.log.healthcheck_logHandler.HCLogHandler
        """
        ArakoonHealthCheck.check_required_ports(logger)
        ArakoonHealthCheck.check_arakoons(logger)
