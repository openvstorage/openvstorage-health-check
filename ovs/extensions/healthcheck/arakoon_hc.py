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
import copy
import json
import time
import Queue
import socket
import ConfigParser
from datetime import timedelta
from collections import OrderedDict
from operator import itemgetter
from StringIO import StringIO
from threading import Thread
from ovs.dal.hybrids.servicetype import ServiceType
from ovs.extensions.db.arakooninstaller import ArakoonClusterConfig, ArakoonInstaller
from ovs_extensions.db.arakoon.pyrakoon.pyrakoon.compat import ArakoonNoMaster, ArakoonNoMasterResult
from ovs.extensions.generic.configuration import Configuration
from ovs.extensions.generic.sshclient import SSHClient, TimeOutException, NotAuthenticatedException, UnableToConnectException
from ovs.extensions.generic.system import System
from ovs_extensions.generic.toolbox import ExtensionsToolbox
from ovs.extensions.healthcheck.expose_to_cli import expose_to_cli, HealthCheckCLIRunner
from ovs.extensions.healthcheck.decorators import cluster_check
from ovs.extensions.healthcheck.helpers.network import NetworkHelper
from ovs.extensions.healthcheck.helpers.service import ServiceHelper
from ovs.extensions.healthcheck.helpers.storagerouter import StoragerouterHelper
from ovs.log.log_handler import LogHandler


class ArakoonHealthCheck(object):
    """
    A healthcheck for the arakoon persistent store
    """
    logger = LogHandler.get('ovs', 'healthcheck_arakoon')

    MODULE = 'arakoon'
    # oldest tlx files may not older than x days. If they are - failed collapse
    MAX_COLLAPSE_AGE = 2
    LOCAL_SR = System.get_my_storagerouter()

    @classmethod
    def _get_arakoon_clusters(cls, result_handler):
        """
        Retrieves all Arakoon clusters registered in this OVSCluster
        :param result_handler: Logging object
        :type result_handler: ovs.extensions.healthcheck.result.HCResults
        :return: Dict with the arakoon cluster types as key and list with dicts which contain cluster names and pyrakoon clients
        :rtype: dict(str, list[dict])
        """
        result_handler.info('Fetching available arakoon clusters.', add_to_result=False)
        arakoon_clusters = {}
        for cluster_name in list(Configuration.list('/ovs/arakoon')) + ['cacc']:
            # Determine Arakoon type
            is_cacc = cluster_name == 'cacc'
            arakoon_config = ArakoonClusterConfig(cluster_id=cluster_name, load_config=not is_cacc)
            arakoon_client = ArakoonInstaller.build_client(arakoon_config)
            if is_cacc is True:
                with open(Configuration.CACC_LOCATION) as config_file:
                    contents = config_file.read()
                arakoon_config.read_config(contents=contents)
                cluster_type = ServiceType.ARAKOON_CLUSTER_TYPES.CFG
            else:
                metadata = json.loads(arakoon_client.get(ArakoonInstaller.METADATA_KEY))
                cluster_type = metadata['cluster_type']
            if cluster_type not in arakoon_clusters:
                arakoon_clusters[cluster_type] = []
            arakoon_clusters[cluster_type].append({'cluster_name': cluster_name, 'client': arakoon_client, 'config': arakoon_config})
        return arakoon_clusters

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
            arakoon_config = ArakoonClusterConfig(str(cluster))
            master_node_ids = [node.name for node in arakoon_config.nodes]

            if ArakoonHealthCheck.LOCAL_SR.machine_id not in master_node_ids:
                continue
            # add node that is available for arakoon cluster
            nodes_per_cluster_result = {}
            missing_nodes_per_cluster = {}
            missing_tlog_per_cluster = {}

            tlog_dir = arakoon_config.export_dict()[ArakoonHealthCheck.LOCAL_SR.machine_id]['tlog_dir']
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

    @classmethod
    @cluster_check
    @expose_to_cli('arakoon', 'collapse-test', HealthCheckCLIRunner.ADDON_TYPE)
    def check_collapse(cls, result_handler, max_collapse_age=3, min_tlx_amount=10):
        """
        Check collapsing of arakoon
        :param result_handler: logging object
        :type result_handler: ovs.extensions.healthcheck.result.HCResults
        :param max_collapse_age: tlx files may not be longer than x days
        :type max_collapse_age: int
        :param min_tlx_amount: Minimum amount of tlxes before making collapsing mandatory (defaults to 10)
        :type min_tlx_amount: int
        :return: None
        :rtype: NoneType
        """
        arakoon_clusters = cls._get_arakoon_clusters(result_handler)
        result_handler.info('Starting Arakoon collapse test', add_to_result=False)
        max_age_seconds = timedelta(days=max_collapse_age).total_seconds()
        result_handler.info('Retrieving all collapsing statistics. This might take a while', add_to_result=False)
        start = time.time()
        arakoon_stats = cls._retrieve_stats(result_handler, arakoon_clusters)
        print arakoon_stats['CFG']
        result_handler.info('Retrieving all collapsing statistics succeeded (duration: {0})'.format(start - time.time()), add_to_result=False)
        for cluster_type, clusters in arakoon_stats.iteritems():
            result_handler.info('Testing the collapse of {0} Arakoons'.format(cluster_type), add_to_result=False)
            for cluster in clusters:
                cluster_name = cluster['cluster_name']
                arakoon_config = cluster['config']
                node_stats = cls._retrieve_stats(arakoon_config)
                node_stats = OrderedDict(sorted(node_stats.items(), key=lambda item: ExtensionsToolbox.advanced_sort(item[0].ip, separator='.')))
                print node_stats
                for node, stats in node_stats.iteritems():
                    identifier_log = 'Arakoon cluster {0} on node {1}'.format(cluster_name, node.ip)
                    if len(stats['errors']) > 0:
                        # Determine where issues were found
                        for step, exception in stats['errors']:
                            if step == 'build_client':
                                try:
                                    # Raise the thrown exception
                                    raise exception
                                except TimeOutException:
                                    result_handler.warning('Connection to {0} has timed out'.format(identifier_log))
                                except (socket.error, UnableToConnectException):
                                    result_handler.failure(
                                        'Connection to {0} could not be established'.format(identifier_log))
                                except NotAuthenticatedException:
                                    result_handler.skip(
                                        'Connection to {0} could not be authenticated. This node has no access to the Arakoon node.'.format(identifier_log))
                                except Exception:
                                    message = 'Connection to {0} could not be established due to an unhandled exception.'.format(identifier_log)
                                    cls.logger.exception(message)
                                    result_handler.exception(message)
                            elif step == 'stat_dir':
                                try:
                                    raise exception
                                except Exception:
                                    message = 'Unable to list the contents of the tlog directory ({0}) for {1}'.format(node.tlog_dir, identifier_log)
                                    cls.logger.exception(message)
                                    result_handler.exception(message)
                        continue
                    tlx_files = stats['results']['tlx']
                    tlog_files = stats['results']['tlog']
                    if any(item is None for item in [tlx_files, tlog_files]):
                        # Exception occurred but no errors were logged
                        result_handler.exception('Neither the tlx or tlog files could be found in the tlog directory ({0}) for {1}'.format(node.tlog_dir, identifier_log))
                        continue
                    if len(tlog_files) == 0:
                        # A tlog should always be present
                        result_handler.failure('{0} has no open tlog'.format(identifier_log))
                        continue
                    if len(tlx_files) < min_tlx_amount:
                        result_handler.skip('{0} only has {1} tlx, not worth collapsing (required: {2})'.format(identifier_log, len(tlx_files), min_tlx_amount))
                        continue
                    # Compare youngest tlog and oldest tlx timestamp
                    seconds_difference = tlx_files[-1][0] - tlog_files[0][0]
                    if seconds_difference > max_age_seconds:
                        result_handler.success('{0} should not be collapsed. The oldest tlx is at least {1} days younger than the youngest tlog'.format(identifier_log, max_collapse_age))
                    else:
                        result_handler.failure('{0} should be collapsed. The oldest tlx is currently {1} old'.format(identifier_log, str(timedelta(seconds=seconds_difference))))

    @classmethod
    def _retrieve_stats(cls, result_handler, arakoon_clusters, batch_size=25):
        """
        Retrieve tlog/tlx stat information for a Arakoon cluster concurrently

        :return: Dict with tlog/tlx contents for every node config
        Example return:
        {CFG: {ovs.extensions.db.arakooninstaller.ArakoonClusterConfig object: {ovs_extensions.db.arakoon.arakooninstaller.ArakoonNodeConfig object: {'output': {'tlx': [['1513174398', '/opt/OpenvStorage/db/arakoon/config/tlogs/3393.tlx']],
                                                                                                                                                                'tlog': [['1513178427', '/opt/OpenvStorage/db/arakoon/config/tlogs/3394.tlog']]},
                                                                                                                                                     'errors': []},
                                                                                ovs_extensions.db.arakoon.arakooninstaller.ArakoonNodeConfig object: {'output': {'tlx': [['1513166090', '/opt/OpenvStorage/db/arakoon/config/tlogs/3392.tlx'], ['1513174418', '/opt/OpenvStorage/db/arakoon/config/tlogs/3393.tlx']],
                                                                                                                                                                'tlog': [['1513178427', '/opt/OpenvStorage/db/arakoon/config/tlogs/3394.tlog']]}, 'errors': []}, <ovs_extensions.db.arakoon.arakooninstaller.ArakoonNodeConfig object at 0x7fb3a84db090>: {'output': {'tlx': [['1513174358', '/opt/OpenvStorage/db/arakoon/config/tlogs/3393.tlx']], 'tlog': [['1513178427', '/opt/OpenvStorage/db/arakoon/config/tlogs/3394.tlog']]},
                                                                                                                                                      'errors': []}}}
        :rtype: dict
        """
        def _get_stats(_queue, _clients, _result_handler):
            while not _queue.empty():
                _cluster_type, _cluster_name, _node_config, _results = _queue.get()
                _errors = _results['errors']
                _output = _results['output']
                identifier = 'Arakoon cluster {0} on node {1}'.format(_cluster_name, _node_config.ip)
                _result_handler.info('Retrieving collapse information for {0}'.format(identifier), add_to_result=False)
                try:
                    _client = _clients[_node_config.ip]
                    tlog_dir = _node_config.tlog_dir
                    path = os.path.join(tlog_dir, '*')
                    try:
                        # List the contents of the tlog directory and sort by oldest modification date
                        # Example output:
                        # 01111 file.tlog
                        # 01112 file2.tlog
                        timestamp_files = _client.run('stat -c "%Y %n" {0}'.format(path), allow_insecure=True)
                    except Exception as ex:
                        _errors.append(('stat_dir', ex))
                        return _queue.task_done()
                    # Sort and separate the timestamp item files
                    _output['tlx'] = sorted((timestamp_file.split() for timestamp_file in timestamp_files.splitlines() if timestamp_file.split()[1].endswith('tlx')), key=itemgetter(0))
                    _output['tlog'] = sorted((timestamp_file.split() for timestamp_file in timestamp_files.splitlines() if timestamp_file.split()[1].endswith('tlog')), key=itemgetter(0))
                    _queue.task_done()
                except Exception as ex:
                    _result_handler.warning('Could not retrieve the collapse information for {0} ({1})'.format(identifier, str(ex)), add_to_result=False)
                    _queue.task_done()

        queue = Queue.Queue()
        results = copy.deepcopy(arakoon_clusters)
        clients = {}
        # Prep work
        for cluster_type, clusters in results.iteritems():
            for cluster in clusters:
                cluster_name = cluster['cluster_name']
                arakoon_config = cluster['config']
                cluster['collapse_result'] = {}
                for node_config in arakoon_config.nodes:
                    result = {'errors': [],
                              'output': {'tlx': [],
                                         'tlog': []}}
                    # Build SSHClients outside the threads to avoid GIL
                    try:
                        client = clients.get(node_config.ip)
                        if client is None:
                            client = SSHClient(node_config.ip, timeout=5)
                            clients[node_config.ip] = client
                    except Exception as ex:
                        result['errors'].append(('build_client', ex))
                        continue
                    cluster['collapse_result'][node_config] = result
                    queue.put((cluster_type, cluster_name, node_config, result))

        for _ in xrange(batch_size):
            thread = Thread(target=_get_stats, args=(queue, clients, result_handler))
            thread.setDaemon(True)  # Setting threads as "daemon" allows main program to exit eventually even if these don't finish correctly.
            thread.start()
        # Wait for all results
        queue.join()
        return results

    @classmethod
    @cluster_check
    @expose_to_cli('arakoon', 'integrity-test', HealthCheckCLIRunner.ADDON_TYPE)
    def verify_integrity(cls, result_handler):
        """
        Verifies the integrity of a list of arakoons
        :param result_handler: logging object
        :type result_handler: ovs.extensions.healthcheck.result.HCResults
        :return: None
        :rtype: NoneType
        """
        arakoon_cluster = cls._get_arakoon_clusters(result_handler)
        result_handler.info('Starting Arakoon integrity test', add_to_result=False)
        for cluster_type, clusters in arakoon_cluster.iteritems():
            result_handler.info('Testing the integry of {0} Arakoons'.format(cluster_type), add_to_result=False)
            for cluster in clusters:
                arakoon_client = cluster['client']
                cluster_name = cluster['cluster_name']
                try:
                    arakoon_client.nop()
                    result_handler.success('Arakoon {0} responded'.format(cluster_name))
                except (ArakoonNoMaster, ArakoonNoMasterResult) as ex:
                    result_handler.failure('Arakoon {0} cannot find a master. (Message: {1})'.format(cluster_name, str(ex)))
                except Exception as ex:
                    cls.logger.exception('Unhandled exception during the integrity check')
                    result_handler.exception('Arakoon {0} threw an unhandled exception. (Message: {1}'.format(cluster_name, str(ex)))
