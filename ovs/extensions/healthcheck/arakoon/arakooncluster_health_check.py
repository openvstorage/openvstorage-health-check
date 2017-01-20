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
import ConfigParser
from datetime import date, timedelta, datetime
from StringIO import StringIO
from ovs.extensions.db.arakoon.ArakoonInstaller import ArakoonClusterConfig
from ovs.extensions.db.arakoon.pyrakoon.pyrakoon.compat import ArakoonNotFound, ArakoonNoMaster, ArakoonNoMasterResult
from ovs.extensions.generic.configuration import Configuration
from ovs.extensions.generic.filemutex import file_mutex
from ovs.extensions.generic.system import System
from ovs.extensions.healthcheck.decorators import expose_to_cli
from ovs.extensions.healthcheck.helpers.network import NetworkHelper
from ovs.extensions.healthcheck.helpers.service import ServiceHelper
from ovs.extensions.healthcheck.helpers.storagerouter import StoragerouterHelper
from ovs.extensions.storage.persistent.pyrakoonstore import PyrakoonStore
from ovs.log.log_handler import LogHandler


class ArakoonHealthCheck(object):
    """
    A healthcheck for the arakoon persistent store
    """
    logger = LogHandler.get('health_check', 'arakoon')
    MODULE = 'arakoon'
    LAST_MINUTES = 5
    MAX_AMOUNT_NODE_RESTARTED = 5
    # oldest tlx files may not older than x days. If they are - failed collapse
    MAX_COLLAPSE_AGE = 2
    LOCAL_SR = System.get_my_storagerouter()

    @staticmethod
    def fetch_clusters(result_handler):
        """
        Fetches the available local arakoon clusters of a cluster
        :param result_handler: logging object
        :type result_handler: ovs.extensions.healthcheck.results.HCResults
        :return: if succeeded a tuple; if failed both dicts are empty
        :rtype: dict
        """
        test_name = 'arakoon-fetch-cluster-test'

        result_handler.info('Fetching available arakoon clusters.')
        arakoon_clusters = list(Configuration.list('/ovs/arakoon'))

        present_nodes = {}
        missing_nodes = {}
        cluster_results = {'present': present_nodes, 'missing': missing_nodes}
        if len(arakoon_clusters) == 0:
            # no arakoon clusters on node
            result_handler.warning('No installed arakoon clusters detected on this system.', test_name)
            return cluster_results

        # add arakoon clusters
        for cluster in arakoon_clusters:
            # add node that is available for arakoon cluster
            nodes_per_cluster_result = {}
            missing_nodes_per_cluster = []
            arakoon_config = ArakoonClusterConfig(str(cluster), filesystem=False)
            arakoon_config.load_config()
            master_node_ids = [node.name for node in arakoon_config.nodes]

            if ArakoonHealthCheck.LOCAL_SR.machine_id not in master_node_ids:
                continue

            try:
                tlog_dir = arakoon_config.export()[ArakoonHealthCheck.LOCAL_SR.machine_id]['tlog_dir']
            except KeyError, ex:
                result_handler.failure('Could not fetch the tlog dir, Arakoon structure changed? Got {0}.'.format(ex.message), test_name)
                continue

            for node_id in master_node_ids:
                node_info = StoragerouterHelper.get_by_machine_id(node_id)
                if node_info is None:
                    # No information found about the storagerouter - old value in arakoon
                    missing_nodes_per_cluster.append(node_id)
                else:
                    # add node information
                    nodes_per_cluster_result.update({node_id: {
                        'hostname': node_info.name,
                        'ip-address': node_info.ip,
                        'guid': node_info.guid,
                        'node_type': node_info.node_type,
                        'tlog_dir': tlog_dir
                        }
                    })
            present_nodes[cluster] = nodes_per_cluster_result
            missing_nodes[cluster] = missing_nodes_per_cluster

        return cluster_results

    @staticmethod
    @expose_to_cli('arakoon', 'consistency-test')
    def check_model_consistency(result_handler):
        """
        Verifies the information in the model
        :param result_handler:
        :return:
        """
        test_name = 'arakoon_model_consistensy'

        def dict_compare(dict1, dict2):
            d1_keys = set(dict1.keys())
            d2_keys = set(dict2.keys())
            intersect_keys = d1_keys.intersection(d2_keys)
            added = d1_keys - d2_keys
            removed = d2_keys - d1_keys
            modified = {key: (dict1[key], dict2[key]) for key in intersect_keys if dict1[key] != dict2[key]}
            same = set(key for key in intersect_keys if dict1[key] == dict2[key])
            return {'added': added, 'removed': removed, 'modified': modified, 'same': same}

        result_handler.info("Verifying arakoon information.")
        # @todo remove testing
        dal_ports = {}
        # dal_ports = {u'arakoon-mybackend01-abm': [26404, 26405], u'arakoon-voldrv': [26408, 26409], u'arakoon-ovsdb': [26402, 26403], u'arakoon-mybackend01-nsm_0': [26406, 26407]}
        arakoon_ports = {}
        # arakoon_ports = {'arakoon-mybackend01-ab': [26404, 26405], 'arakoon-voldrv': [26408, 26409], 'arakoon-ovsdb': [26402, 26403], 'arakoon-mybackend01-nsm_0': [26406, 26407]}
        for service in ServiceHelper.get_local_arakoon_services():
            dal_ports[service.name] = service.ports
        for arakoon_cluster in Configuration.list('/ovs/arakoon'):
            e = Configuration.get('/ovs/arakoon/{0}/config'.format(arakoon_cluster), raw=True)
            config = ConfigParser.RawConfigParser()
            config.readfp(StringIO(e))
            for section in config.sections():
                if section != "global" and section == ArakoonHealthCheck.LOCAL_SR.machine_id:
                    process_name = "arakoon-{0}".format(arakoon_cluster)
                    arakoon_ports[process_name] = [int(config.get(section, 'client_port')), int(config.get(section, 'messaging_port'))]  # cast port strings to int
        diff = dict_compare(dal_ports, arakoon_ports)
        if len(diff['added']) > 0 or len(diff['removed']) > 0:
            if len(diff['added']) > 0:
                result_handler.warning('Found {0} in DAL but not in Arakoon.'.format(diff['added']), test_name)
            if len(diff['removed']) > 0:
                result_handler.warning('Found {0} in Arakoon but not in DAL.'.format(diff['removed']), test_name)
        else:
            result_handler.success('Arakoon info for DAL and Arakoon are the same.', test_name)
        if len(diff['modified']) > 0:
            result_handler.warning('The following items have changed: {0}.'.format(diff['modified']), test_name)
        else:
            result_handler.success('No items have changed.', test_name)

    # @todo: separate cluster-wide-check
    @staticmethod
    @expose_to_cli('arakoon', 'ports-test')
    def check_arakoon_ports(result_handler):
        """
        Checks all ports of Arakoon nodes (client & server)

        :param result_handler: logging object
        :type result_handler: ovs.extensions.healthcheck.results.HCResults
        """
        test_name = 'arakoon-ports-test'
        result_handler.info('Checking PORT CONNECTIONS of arakoon nodes.')
        ip = ArakoonHealthCheck.LOCAL_SR.ip
        for service in ServiceHelper.get_local_arakoon_services():
            for port in service.ports:
                result = NetworkHelper.check_port_connection(port, ip)
                if result:
                    result_handler.success(
                        'Connection successfully established to service {0} on {1}:{2}'.format(service.name, ip, port), test_name)
                else:
                    result_handler.failure('Connection FAILED to service {0} on {1}:{2}'.format(service.name, ip, port), test_name)

    # @todo: separate cluster-wide-check
    @staticmethod
    @expose_to_cli('arakoon', 'collapse-test')
    def check_collapse(result_handler, arakoon_clusters=None, max_collapse_age=MAX_COLLAPSE_AGE):
        """
        Check collapsing of arakoon

        :param result_handler: logging object
        :type result_handler: ovs.extensions.healthcheck.results.HCResults
        :param arakoon_clusters: List of available Arakoons
        :type arakoon_clusters: dict
        :param max_collapse_age: tlx files may not be longer than x days
        :type max_collapse_age: int
        :return: list with OK, NOK status
        :rtype: list
        """
        test_name = 'arakoon-collapse-test'

        if arakoon_clusters is None:
            res = ArakoonHealthCheck.fetch_clusters(result_handler)
            arakoon_clusters = dict(res['missing'])
            arakoon_clusters.update(res['present'])

        ok_arakoons = []
        nok_arakoons = []
        result = {'ok': ok_arakoons, 'nok': nok_arakoons}
        # tlx file must have young timestamp than this one.
        max_age_timestamp = time.mktime((date.today() - timedelta(days=max_collapse_age)).timetuple())

        for arakoon, arakoon_nodes in arakoon_clusters.iteritems():
            for node, config in arakoon_nodes.iteritems():
                if node != ArakoonHealthCheck.LOCAL_SR.machine_id:
                    continue
                try:
                    tlog_dir = config['tlog_dir']
                    files = os.listdir(tlog_dir)
                except KeyError:
                    result_handler.failure('Could not fetch the tlog dir, Arakoon structure changed?', test_name)
                except OSError as ex:
                    result_handler.failure('File or directory not found: {0}'.format(ex), test_name)
                    nok_arakoons.append(arakoon)
                    continue

                if len(files) == 0:
                    nok_arakoons.append(arakoon)
                    if not result_handler.print_progress:
                        result_handler.failure('No files found in {0}'.format(tlog_dir), test_name)
                    continue

                if 'head.db' in files:
                    head_db_stats = os.stat('{0}/head.db'.format(tlog_dir))
                    if head_db_stats.st_mtime > max_age_timestamp:
                        ok_arakoons.append(arakoon)
                        continue
                else:
                    # Determine whether the arakoon is fresh or a collapse already happened
                    pass

                tlx_files = [(int(tlx_file.replace('.tlx', '')), tlx_file) for tlx_file in files
                             if tlx_file.endswith('.tlx')]
                amount_tlx = len(tlx_files)

                # Discussed with Arakoon team. Min tlx files must be 3 before checking time
                if amount_tlx < 3 and len([tlog_file for tlog_file in files if tlog_file.endswith('.tlog')]) > 0:
                    result_handler.info('Found less than 3 tlogs for {0}, collapsing is not worth doing.'.format(arakoon))
                    ok_arakoons.append(arakoon)
                    continue
                elif amount_tlx == 0 and len([tlog_file for tlog_file in files if tlog_file.endswith('.tlog')]) < 0:
                    nok_arakoons.append(arakoon)
                    if not result_handler.print_progress:
                        result_handler.failure('No tlx files found and head.db is out of sync or is not present in {0}.'.format(tlog_dir), test_name)
                    continue

                tlx_files.sort(key=lambda tup: tup[0])
                oldest_file = tlx_files[0][1]

                try:
                    oldest_tlx_stats = os.stat('{0}/{1}'.format(tlog_dir, oldest_file))
                except OSError, ex:
                    if not result_handler.print_progress:
                        result_handler.failure('File or directory not found: {0}'.format(ex), test_name)
                    nok_arakoons.append(arakoon)
                    continue

                if oldest_tlx_stats.st_mtime > max_age_timestamp:
                    result_handler.success('Oldest tlx file for Arakoon {0} is not older than {1}.'.format(arakoon, max_collapse_age), test_name)
                    ok_arakoons.append(arakoon)
                    continue

                if result_handler.print_progress:
                    datetime_oldest_file = datetime.fromtimestamp(oldest_tlx_stats.st_mtime).isoformat()
                    datetime_old_date = datetime.fromtimestamp(max_age_timestamp).isoformat()
                    result_handler.failure('oldest file: {0} with timestamp: {1} is older than {2} for arakoon {3}'
                                           .format(oldest_file, datetime_oldest_file, datetime_old_date, arakoon),
                                           test_name)

                nok_arakoons.append(arakoon)

        # Testing conditions
        if len(result['nok']) > 0:
            result_handler.failure('{0} Arakoon(s) having issues with collapsing: {1}'.format(len(result['nok']), ','.join(result['nok'])),
                                   test_name)
        elif len(result['ok']) > 0:
            result_handler.success('ALL Arakoon(s) are collapsed.', test_name)
        return result

    # @todo: separate cluster-wide-check
    @staticmethod
    @expose_to_cli('arakoon', 'integrity-test')
    def verify_integrity(result_handler, arakoon_clusters=None):
        """
        Verifies the integrity of a list of arakoons

        :param result_handler: logging object
        :type result_handler: ovs.extensions.healthcheck.results.HCResults
        :param arakoon_clusters: list of arakoon names
        :type arakoon_clusters: list that consists of strings
        :return: (working_arakoon_list, no_master_arakoon_list, down_arakoon_list, unkown_arakoon_list)
        :rtype: tuple > lists
        """
        test_name = 'arakoon-integrity-test'

        unknown_arakoon_list = []
        working_arakoon_list = []
        no_master_arakoon_list = []
        down_arakoon_list = []

        result = {
            "unkown": unknown_arakoon_list,
            "working": working_arakoon_list,
            "no_master": no_master_arakoon_list,
            "down": down_arakoon_list
        }

        if arakoon_clusters is None:
            arakoon_clusters = ArakoonHealthCheck.fetch_clusters(result_handler)['present']

        result_handler.info('Starting Arakoon integrity test')
        # verify integrity of arakoon clusters
        for cluster_name, cluster_info in arakoon_clusters.iteritems():
            if ArakoonHealthCheck.LOCAL_SR.machine_id not in cluster_info:
                continue

            with file_mutex('ovs-healthcheck_arakoon-test_{0}'.format(cluster_name)):
                try:
                    # determine if there is a healthy cluster
                    client = PyrakoonStore(str(cluster_name))
                    client.nop()
                except ArakoonNotFound:
                    down_arakoon_list.append(cluster_name)
                    break

                except (ArakoonNoMaster, ArakoonNoMasterResult):
                    no_master_arakoon_list.append(cluster_name)
                    break

                except Exception:
                    unknown_arakoon_list.append(cluster_name)
                    break

        # Processing results
        if len(working_arakoon_list) == len(arakoon_clusters):
            result_handler.success('ALL available Arakoon(s) their integrity are/is OK! ', test_name)
        else:
            # less output for unattended_mode
            # check amount OK arakoons
            if len(working_arakoon_list) > 0:
                result_handler.warning(
                    '{0}/{1} Arakoon(s) is/are OK!: {2}'.format(len(working_arakoon_list), len(arakoon_clusters), ', '.join(working_arakoon_list)), test_name)
            # check amount NO-MASTER arakoons
            if len(no_master_arakoon_list) > 0:
                result_handler.failure('{0} Arakoon(s) cannot find a MASTER: {1}'.format(len(no_master_arakoon_list), ', '.join(no_master_arakoon_list)), test_name)

            # check amount DOWN arakoons
            if len(down_arakoon_list) > 0:
                result_handler.failure('{0} Arakoon(s) seem(s) to be DOWN!: {1}'.format(len(down_arakoon_list), ', '.join(down_arakoon_list)), test_name)

                # check amount UNKNOWN_ERRORS arakoons
                if len(unknown_arakoon_list) > 0:
                    result_handler.exception('{0} Arakoon(s) seem(s) to have UNKNOWN ERRORS, please check the logs'
                                             .format(len(unknown_arakoon_list), ', '.join(unknown_arakoon_list)),test_name)
                else:
                    result_handler.failure('Some Arakoon(s) have problems, please check this!', test_name)
            # check amount UNKNOWN_ERRORS arakoons
            if len(unknown_arakoon_list) > 0:
                result_handler.failure('{0} Arakoon(s) seem(s) to have UNKNOWN ERRORS, please check the logs @ '
                                       '/var/log/ovs/arakoon.log or /var/log/upstart/ovs-arakoon-*.log: {1}'.format(len(unknown_arakoon_list), ', '.join(unknown_arakoon_list)),
                                       test_name)
            else:
                result_handler.failure('Some Arakoon(s) have problems, please check this!', test_name)

            return result

    # @todo: separate cluster-wide-check
    @staticmethod
    @expose_to_cli('arakoon', 'missing-node-test')
    def check_arakoons(result_handler):
        """
        Verifies/validates the integrity of all available arakoons

        :param result_handler: logging object
        :type result_handler: ovs.extensions.healthcheck.results.HCResults
        """
        test_name = 'arakoon-missing-node-test'

        fetched_clusters = ArakoonHealthCheck.fetch_clusters(result_handler)
        arakoon_clusters = fetched_clusters['present']
        missing_nodes = fetched_clusters['missing']
        if len([nodes for nodes in missing_nodes.itervalues() if len(nodes) != 0]) != 0:
            # Only return the (arakoon, system id) tuple for arakoons that have missing system ids
            missing = [cluster for cluster in missing_nodes.items() if len(cluster[1]) != 0]
            result_handler.failure('The following nodes are stored in arakoon but missing in reality (output format is (arakoon, [system ids]): {0}'.format(missing),
                                   test_name)
        else:
            result_handler.success('Found no nodes that are missing according to arakoons.', test_name)
