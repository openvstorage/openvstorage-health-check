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
import timeout_decorator
import ConfigParser
from datetime import date, timedelta
from StringIO import StringIO
from ovs.extensions.db.arakoon.ArakoonInstaller import ArakoonClusterConfig
from ovs.extensions.db.arakoon.pyrakoon.pyrakoon.compat import ArakoonNotFound, ArakoonNoMaster, ArakoonNoMasterResult
from ovs.extensions.generic.configuration import Configuration
from ovs.extensions.generic.system import System
from ovs.extensions.healthcheck.expose_to_cli import expose_to_cli, HealthCheckCLIRunner
from ovs.extensions.healthcheck.cluster_check import cluster_check
from ovs.extensions.healthcheck.helpers.network import NetworkHelper
from ovs.extensions.healthcheck.helpers.service import ServiceHelper
from ovs.extensions.healthcheck.helpers.storagerouter import StoragerouterHelper
from ovs.extensions.storage.persistent.pyrakoonstore import PyrakoonStore
from timeout_decorator.timeout_decorator import TimeoutError


class ArakoonHealthCheck(object):
    """
    A healthcheck for the arakoon persistent store
    """
    MODULE = 'arakoon'
    # oldest tlx files may not older than x days. If they are - failed collapse
    MAX_COLLAPSE_AGE = 2
    LOCAL_SR = System.get_my_storagerouter()
    INTEGRITY_TIMEOUT = 10

    @staticmethod
    def _get_clusters_residing_on_local_node(result_handler):
        """
        Fetches the available local arakoon clusters of a cluster
        :param result_handler: logging object
        :type result_handler: ovs.extensions.healthcheck.result.HCResults
        :return: dict with the arakoon info
        :rtype: dict
        """
        result_handler.info('Fetching available arakoon clusters.', add_to_result=False)
        arakoon_clusters = list(Configuration.list('/ovs/arakoon'))

        present_nodes = {}
        missing_nodes = {}
        missing_tlog = {}
        cluster_results = {'present': present_nodes, 'missing': missing_nodes, 'tlog_missing': missing_tlog}
        if len(arakoon_clusters) == 0:
            # no arakoon clusters on node
            result_handler.warning('No installed arakoon clusters detected on this system.')
            return cluster_results

        # add arakoon clusters
        for cluster in arakoon_clusters:
            arakoon_config = ArakoonClusterConfig(str(cluster), filesystem=False)
            arakoon_config.load_config()
            master_node_ids = [node.name for node in arakoon_config.nodes]

            if ArakoonHealthCheck.LOCAL_SR.machine_id not in master_node_ids:
                continue
            # add node that is available for arakoon cluster
            nodes_per_cluster_result = {}
            missing_nodes_per_cluster = {}
            missing_tlog_per_cluster = {}

            tlog_dir = arakoon_config.export()[ArakoonHealthCheck.LOCAL_SR.machine_id]['tlog_dir']
            for node_id in master_node_ids:
                machine = StoragerouterHelper.get_by_machine_id(node_id)
                if machine is None:
                    # No information found about the storagerouter - old value in arakoon
                    missing_nodes_per_cluster.update({node_id: tlog_dir})
                    result_handler.warning('Could not fetch storagerouter information about node {0} that was stored in Arakoon {1}'.format(node_id, cluster), add_to_result=False)
                elif not tlog_dir:
                    missing_tlog_per_cluster.update({node_id: tlog_dir})
                    result_handler.warning('Arakoon {1} seems to have no tlog_dir on this node.'.format(node_id, cluster), add_to_result=False)
                else:
                    nodes_per_cluster_result.update({node_id: tlog_dir})
            present_nodes[cluster] = nodes_per_cluster_result
            missing_nodes[cluster] = missing_nodes_per_cluster
            missing_tlog[cluster] = missing_tlog_per_cluster

        return cluster_results

    @staticmethod
    @expose_to_cli('arakoon', 'consistency-test', HealthCheckCLIRunner.ADDON_TYPE)
    def check_model_consistency(result_handler):
        """
        Verifies the information in the model
        :param result_handler: logging object
        :type result_handler: ovs.extensions.healthcheck.result.HCResults
        :return: None
        :rtype: NoneType
        """
        def dict_compare(dict1, dict2):
            d1_keys = set(dict1.keys())
            d2_keys = set(dict2.keys())
            intersect_keys = d1_keys.intersection(d2_keys)
            added = d1_keys - d2_keys
            removed = d2_keys - d1_keys
            modified = {key: (dict1[key], dict2[key]) for key in intersect_keys if dict1[key] != dict2[key]}
            same = set(key for key in intersect_keys if dict1[key] == dict2[key])
            return {'added': added, 'removed': removed, 'modified': modified, 'same': same}

        result_handler.info("Verifying arakoon information.", add_to_result=False)
        dal_ports = {}
        arakoon_ports = {}
        for service in ServiceHelper.get_local_arakoon_services():
            dal_ports[service.name] = service.ports
        for arakoon_cluster in Configuration.list('/ovs/arakoon'):
            e = Configuration.get('/ovs/arakoon/{0}/config'.format(arakoon_cluster), raw=True)
            config = ConfigParser.RawConfigParser()
            config.readfp(StringIO(e))
            for section in config.sections():
                if section == ArakoonHealthCheck.LOCAL_SR.machine_id:
                    process_name = "arakoon-{0}".format(arakoon_cluster)
                    arakoon_ports[process_name] = [int(config.get(section, 'client_port')), int(config.get(section, 'messaging_port'))]  # cast port strings to int
                    break
        diff = dict_compare(dal_ports, arakoon_ports)
        if len(diff['added']) > 0 or len(diff['removed']) > 0:
            if len(diff['added']) > 0:
                result_handler.warning('Found {0} in DAL but not in Arakoon.'.format(diff['added']))
            if len(diff['removed']) > 0:
                result_handler.warning('Found {0} in Arakoon but not in DAL.'.format(diff['removed']))
        else:
            result_handler.success('Arakoon info for DAL and Arakoon are the same.')
        if len(diff['modified']) > 0:
            result_handler.warning('The following items have changed: {0}.'.format(diff['modified']))
        else:
            result_handler.success('No items have changed.')

    @staticmethod
    @expose_to_cli('arakoon', 'ports-test', HealthCheckCLIRunner.ADDON_TYPE)
    def check_local_arakoon_ports(result_handler):
        """
        Checks all ports of Arakoon nodes (client & server) on the local node
        :param result_handler: logging object
        :type result_handler: ovs.extensions.healthcheck.result.HCResults
        :return: None
        :rtype: NoneType
        """
        result_handler.info('Checking PORT CONNECTIONS of arakoon nodes.', add_to_result=False)
        ip = ArakoonHealthCheck.LOCAL_SR.ip
        for service in ServiceHelper.get_local_arakoon_services():
            for port in service.ports:
                result = NetworkHelper.check_port_connection(port, ip)
                if result:
                    result_handler.success(
                        'Connection successfully established to service {0} on {1}:{2}'.format(service.name, ip, port))
                else:
                    result_handler.failure('Connection FAILED to service {0} on {1}:{2}'.format(service.name, ip, port))

    @staticmethod
    @expose_to_cli('arakoon', 'collapse-test', HealthCheckCLIRunner.ADDON_TYPE)
    def check_collapse(result_handler, arakoon_clusters=None, max_collapse_age=MAX_COLLAPSE_AGE):
        """
        Check collapsing of arakoon
        :param result_handler: logging object
        :type result_handler: ovs.extensions.healthcheck.result.HCResults
        :param arakoon_clusters: List of available Arakoons
        :type arakoon_clusters: dict
        :param max_collapse_age: tlx files may not be longer than x days
        :type max_collapse_age: int
        :return: None
        :rtype: NoneType
        """
        if arakoon_clusters is None:
            res = ArakoonHealthCheck._get_clusters_residing_on_local_node(result_handler)
            arakoon_clusters = dict(res['missing'])
            arakoon_clusters.update(res['present'])

        ok_arakoons = []
        nok_arakoons = []
        # tlx file must have young timestamp than this one.
        max_age_timestamp = time.mktime((date.today() - timedelta(days=max_collapse_age)).timetuple())

        for cluster_name, arakoon_nodes in arakoon_clusters.iteritems():
            for node_id, tlog_dir in arakoon_nodes.iteritems():
                if node_id != ArakoonHealthCheck.LOCAL_SR.machine_id:
                    continue
                try:
                    files = os.listdir(tlog_dir)
                except OSError as ex:
                    result_handler.failure('The tlog directory {0} is not present for cluster {1}. Got {2}'.format(tlog_dir, cluster_name, str(ex)))
                    nok_arakoons.append(cluster_name)
                    continue

                if len(files) == 0:
                    result_handler.failure('No files found in {0}'.format(tlog_dir))
                    nok_arakoons.append(cluster_name)
                    continue

                if 'head.db' in files:
                    head_db_stats = os.stat('{0}/head.db'.format(tlog_dir))
                    if head_db_stats.st_mtime > max_age_timestamp:
                        ok_arakoons.append(cluster_name)
                        continue
                else:
                    # @todo Determine whether the arakoon is fresh or a collapse already happened
                    pass

                tlx_files = []
                tlog_files = []
                for a_file in files:
                    if a_file.endswith('.tlx'):
                        tlx_files.append((int(a_file.replace('.tlx', '')), a_file))
                    elif a_file.endswith('.tlog'):
                        tlog_files.append(a_file)
                tlx_amount = len(tlx_files)
                tlog_amount = len(tlog_files)
                # Always 1 open tlog
                # tlx = compressed tlogs and used for collapsing (created once tlog is closed)
                if tlog_amount == 0:
                    result_handler.failure('No tlog file could be found and 1 should always be present in {0}.'.format(tlog_dir))
                    nok_arakoons.append(cluster_name)
                    continue
                elif tlx_amount < 3:
                    result_handler.skip('Collapsing {0} is not worth doing, only found {1} tlx files.'.format(cluster_name, tlx_amount), add_to_result=False)
                    ok_arakoons.append(cluster_name)
                    continue

                tlx_files.sort(key=lambda tup: tup[0])
                oldest_file = tlx_files[0][1]

                try:
                    oldest_tlx_stats = os.stat('{0}/{1}'.format(tlog_dir, oldest_file))
                except OSError as ex:
                    result_handler.warning('Could not inspect {0}/{1}. Got {2}'.format(tlog_dir, oldest_file, str(ex)))
                    nok_arakoons.append(cluster_name)
                    continue

                if oldest_tlx_stats.st_mtime > max_age_timestamp:
                    result_handler.success('Oldest tlx file for Arakoon {0} is not older than {1}.'.format(cluster_name, max_collapse_age))
                    ok_arakoons.append(cluster_name)
                    continue
                else:
                    result_handler.warning('Oldest tlx file for Arakoon {0} is not older than {1}.'.format(cluster_name, max_collapse_age))

                nok_arakoons.append(cluster_name)

        # Testing conditions
        if len(nok_arakoons) > 0:
            result_handler.warning('{0} Arakoon(s) having issues with collapsing: {1}'.format(len(nok_arakoons), ','.join(nok_arakoons)))
        elif len(ok_arakoons) > 0:
            result_handler.success('ALL Arakoon(s) are collapsed.')

    @staticmethod
    @cluster_check
    @expose_to_cli('arakoon', 'integrity-test', HealthCheckCLIRunner.ADDON_TYPE)
    def verify_integrity(result_handler, arakoon_clusters=None):
        """
        Verifies the integrity of a list of arakoons
        :param result_handler: logging object
        :type result_handler: ovs.extensions.healthcheck.result.HCResults
        :param arakoon_clusters: list of arakoon names
        :type arakoon_clusters: list that consists of strings
        :return: None
        :rtype: NoneType
        """
        @timeout_decorator.timeout(ArakoonHealthCheck.INTEGRITY_TIMEOUT)
        def verify_arakoon(arakoon_cluster_name):
            """
            Tries a nop on a arakoon cluster
            :param arakoon_cluster_name: name of the arakoon cluster
            :return: None
            """
            try:
                # determine if there is a healthy cluster
                client = PyrakoonStore(str(arakoon_cluster_name))
                client.nop()
                result_handler.success('Arakoon {0} responded successfully.'.format(arakoon_cluster_name))
            except ArakoonNotFound as ex:
                result_handler.failure('Arakoon {0} seems to be down. Got {1}'.format(arakoon_cluster_name, str(ex)))
            except (ArakoonNoMaster, ArakoonNoMasterResult) as ex:
                result_handler.failure('Arakoon {0} cannot find a master. Got {1}'.format(arakoon_cluster_name, str(ex)))
            except TimeoutError:
                result_handler.warning('Arakoon {0} did not respond within {1}s'.format(arakoon_cluster_name, ArakoonHealthCheck.INTEGRITY_TIMEOUT))
            except Exception as ex:
                result_handler.exception('Arakoon {0} could not process a nop. Got {1}'.format(arakoon_cluster_name, str(ex)))

        if arakoon_clusters is None:
            arakoon_clusters = ArakoonHealthCheck._get_clusters_residing_on_local_node(result_handler)['present']

        result_handler.info('Starting Arakoon integrity test', add_to_result=False)
        # verify integrity of arakoon clusters
        for cluster_name, cluster_info in arakoon_clusters.iteritems():
            if ArakoonHealthCheck.LOCAL_SR.machine_id not in cluster_info:
                continue
            verify_arakoon(str(cluster_name))

    @staticmethod
    @cluster_check
    @expose_to_cli('arakoon', 'missing-node-test', HealthCheckCLIRunner.ADDON_TYPE)
    def check_missing_nodes(result_handler):
        """
        Verifies/validates the integrity of all available arakoons
        :param result_handler: logging object
        :type result_handler: ovs.extensions.healthcheck.result.HCResults
        :return: None
        :rtype: NoneType
        """
        fetched_clusters = ArakoonHealthCheck._get_clusters_residing_on_local_node(result_handler)
        missing = [(cluster_name, missing_nodes.keys()) for cluster_name, missing_nodes in fetched_clusters['missing'].items() if len(missing_nodes) > 0]
        if len(missing) > 0:
            # Only return the (arakoon, system id) tuple for arakoons that have missing system ids
            result_handler.failure('The following nodes are stored in arakoon but missing in reality.'.format(missing))
        else:
            result_handler.success('Found no nodes that are missing according to arakoons.')
