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
import json
import time
import Queue
import socket
import operator
from datetime import timedelta
from collections import OrderedDict
from threading import Thread
from ovs.dal.hybrids.servicetype import ServiceType
from ovs.extensions.db.arakooninstaller import ArakoonClusterConfig, ArakoonInstaller
from ovs_extensions.db.arakoon.pyrakoon.pyrakoon.compat import ArakoonNoMaster, ArakoonNoMasterResult
from ovs.extensions.generic.configuration import Configuration
from ovs.extensions.generic.sshclient import SSHClient, TimeOutException, NotAuthenticatedException, UnableToConnectException
from ovs_extensions.generic.toolbox import ExtensionsToolbox
from ovs.extensions.healthcheck.decorators import cluster_check
from ovs.extensions.healthcheck.config.error_codes import ErrorCodes
from ovs.extensions.healthcheck.expose_to_cli import expose_to_cli, HealthCheckCLIRunner
from ovs.extensions.healthcheck.helpers.network import NetworkHelper
from ovs.extensions.healthcheck.logger import Logger
from ovs.extensions.services.servicefactory import ServiceFactory


class ArakoonHealthCheck(object):
    """
    A healthcheck for the arakoon persistent store
    """

    logger = Logger("healthcheck-healthcheck_arakoon")
    MODULE = 'arakoon'

    @classmethod
    def _get_arakoon_clusters(cls, result_handler):
        """
        Retrieves all Arakoon clusters registered in this OVSCluster
        :param result_handler: Logging object
        :type result_handler: ovs.extensions.healthcheck.result.HCResults
        :return: Dict with the Arakoon cluster types as key and list with dicts which contain cluster names and pyrakoon clients
        :rtype: dict(str, list[dict])
        """
        result_handler.info('Fetching available arakoon clusters.', add_to_result=False)
        arakoon_clusters = {}
        for cluster_name in list(Configuration.list('/ovs/arakoon')) + ['cacc']:
            # Determine Arakoon type
            is_cacc = cluster_name == 'cacc'
            arakoon_config = ArakoonClusterConfig(cluster_id=cluster_name, load_config=not is_cacc)
            if is_cacc is True:
                with open(Configuration.CACC_LOCATION) as config_file:
                    contents = config_file.read()
                arakoon_config.read_config(contents=contents)
                cluster_type = ServiceType.ARAKOON_CLUSTER_TYPES.CFG
                arakoon_client = ArakoonInstaller.build_client(arakoon_config)
            else:
                arakoon_client = ArakoonInstaller.build_client(arakoon_config)
                metadata = json.loads(arakoon_client.get(ArakoonInstaller.METADATA_KEY))
                cluster_type = metadata['cluster_type']
            if cluster_type not in arakoon_clusters:
                arakoon_clusters[cluster_type] = []
            arakoon_clusters[cluster_type].append({'cluster_name': cluster_name, 'client': arakoon_client, 'config': arakoon_config})
        return arakoon_clusters

    @classmethod
    @cluster_check
    @expose_to_cli(MODULE, 'nodes-test', HealthCheckCLIRunner.ADDON_TYPE)
    def check_node_status(cls, result_handler, max_transactions_behind=10):
        """
        Checks the status of every node within the Arakoon cluster
        This check will report what nodes are currently missing and what nodes are catching up to the master
        :param result_handler: Logging object
        :type result_handler: ovs.extensions.healthcheck.result.HCResults
        :param max_transactions_behind: The number of transactions that a slave can be behind a master before logging a failure
        :type max_transactions_behind: int
        :return: None
        :rtype: NoneType
        """
        result_handler.info('Starting Arakoon nodes test.', add_to_result=False)
        arakoon_clusters = cls._get_arakoon_clusters(result_handler)
        for cluster_type, clusters in arakoon_clusters.iteritems():
            result_handler.info('Fetching the status of {0} Arakoons'.format(cluster_type), add_to_result=False)
            for cluster in clusters:
                arakoon_client = cluster['client']
                cluster_name = cluster['cluster_name']
                arakoon_config = cluster['config']
                # Map the node ids to the object for easier lookups
                node_info = dict((node.name, node) for node in arakoon_config.nodes)
                identifier = 'Arakoon cluster {0}'.format(cluster_name)
                try:
                    statistics = arakoon_client._client.statistics()
                    node_is = statistics['node_is']
                    # Look for any missing nodes within the cluster
                    missing_ids = list(set(node_info.keys()) - set(node_is.keys()))
                    if len(missing_ids) > 0:
                        for missing_id in missing_ids:
                            node_config = node_info[missing_id]
                            result_handler.failure('{0} is missing node: {1}'.format(identifier, '{0} ({1}:{2})'.format(node_config.name, node_config.ip, node_config.client_port)),
                                                   code=ErrorCodes.node_missing)
                    highest_id = max(node_is.iteritems(), key=operator.itemgetter(1))[0]
                    for node_id, transactions in node_is.iteritems():
                        if node_id == highest_id:
                            continue
                        transactions_behind = node_is[highest_id] - transactions
                        node_config = node_info[node_id]
                        log = 'Node {0} ({1}:{2}) for {3} {{0}} ({4}/{5})'.format(node_config.name, node_config.ip, node_config.client_port,
                                                                                  identifier, transactions_behind, max_transactions_behind)
                        if transactions == 0:
                            result_handler.warning(log.format('is catching up'), code=ErrorCodes.slave_catch_up)
                        elif transactions_behind > max_transactions_behind:
                            result_handler.failure(log.format('is behind the master'), code=ErrorCodes.master_behind)
                        else:
                            result_handler.success(log.format('is up to date'), code=ErrorCodes.node_up_to_date)
                except (ArakoonNoMaster, ArakoonNoMasterResult) as ex:
                    result_handler.failure('{0} cannot find a master. (Message: {1})'.format(identifier, cluster_name, str(ex)), code=ErrorCodes.master_none)
                except Exception as ex:
                    cls.logger.exception('Unhandled exception during the nodes check')
                    result_handler.exception('Testing {0} threw an unhandled exception. (Message: {1})'.format(identifier, cluster_name, str(ex)),
                                             code=ErrorCodes.unhandled_exception)

    @classmethod
    @cluster_check
    @expose_to_cli(MODULE, 'ports-test', HealthCheckCLIRunner.ADDON_TYPE)
    def check_arakoon_ports(cls, result_handler):
        """
        Verifies that the Arakoon clusters still respond to connections
        :param result_handler: logging object
        :type result_handler: ovs.extensions.healthcheck.result.HCResults
        :return: None
        :rtype: NoneType
        """
        arakoon_clusters = cls._get_arakoon_clusters(result_handler)
        result_handler.info('Starting Arakoon ports test.', add_to_result=False)
        result_handler.info('Retrieving all collapsing statistics. This might take a while', add_to_result=False)
        start = time.time()
        arakoon_stats = cls._get_port_connections(result_handler, arakoon_clusters)
        result_handler.info('Retrieving all collapsing statistics succeeded (duration: {0})'.format(time.time() - start), add_to_result=False)
        for cluster_type, clusters in arakoon_stats.iteritems():
            result_handler.info('Testing the collapse of {0} Arakoons'.format(cluster_type), add_to_result=False)
            for cluster in clusters:
                cluster_name = cluster['cluster_name']
                connection_result = cluster['connection_result']
                connection_result = OrderedDict(sorted(connection_result.items(), key=lambda item: ExtensionsToolbox.advanced_sort(item[0].ip, separator='.')))
                for node, stats in connection_result.iteritems():
                    identifier_log = 'Arakoon cluster {0} on node {1}'.format(cluster_name, node.ip)
                    if len(stats['errors']) > 0:
                        # Determine where issues were found
                        for step, exception in stats['errors']:
                            if step == 'test_connection':
                                try:
                                    # Raise the thrown exception
                                    raise exception
                                except Exception:
                                    message = 'Connection to {0} could not be established due to an unhandled exception.'.format(identifier_log)
                                    cls.logger.exception(message)
                                    result_handler.exception(message, code=ErrorCodes.unhandled_exception)
                        continue
                    if stats['result'] is True:
                        result_handler.success('Connection established to {0}'.format(identifier_log),
                                               code=ErrorCodes.arakoon_connection_ok)
                    else:
                        result_handler.failure('Connection could not be established to {0}'.format(identifier_log),
                                               code=ErrorCodes.arakoon_connection_failure)

    @classmethod
    def _get_port_connections(cls, result_handler, arakoon_clusters, batch_size=10):
        """
        Retrieve tlog/tlx stat information for a Arakoon cluster concurrently
        Note: this will mutate the given arakoon_clusters dict
        :param result_handler: logging object
        :type result_handler: ovs.extensions.healthcheck.result.HCResults
        :param arakoon_clusters: Information about all arakoon clusters, sorted by type and given config
        :type arakoon_clusters: dict
        :param batch_size: Amount of workers to collect the Arakoon information.
        The amount of workers are dependant on the MaxSessions in the sshd_config
        :return: Dict with tlog/tlx contents for every node config
        Example return:
        {CFG: {ovs.extensions.db.arakooninstaller.ArakoonClusterConfig object: {ovs_extensions.db.arakoon.arakooninstaller.ArakoonNodeConfig object: {'result': True,
                                                                                                                                                     'errors': []},
                                                                                ovs_extensions.db.arakoon.arakooninstaller.ArakoonNodeConfig object: {'result': False,
                                                                                                                                                      'errors': []}}}
        :rtype: dict
        """
        queue = Queue.Queue()
        # Prep work
        for cluster_type, clusters in arakoon_clusters.iteritems():
            for cluster in clusters:
                cluster_name = cluster['cluster_name']
                arakoon_config = cluster['config']
                cluster['connection_result'] = {}
                for node_config in arakoon_config.nodes:
                    result = {'errors': [],
                              'result': False}
                    cluster['connection_result'][node_config] = result
                    queue.put((cluster_name, node_config, result))

        for _ in xrange(batch_size):
            thread = Thread(target=cls._connection_worker, args=(queue, result_handler))
            thread.setDaemon(True)  # Setting threads as "daemon" allows main program to exit eventually even if these don't finish correctly.
            thread.start()
        # Wait for all results
        queue.join()
        return arakoon_clusters

    @staticmethod
    def _connection_worker(queue, result_handler):
        """
        Worker method to retrieve file descriptors
        :param queue: Queue to use
        :param result_handler: Logging object
        :return: None
        :rtype: NoneType
        """
        while not queue.empty():
            cluster_name, _node_config, _results = queue.get()
            errors = _results['errors']
            identifier = 'Arakoon cluster {0} on node {1}'.format(cluster_name, _node_config.ip)
            result_handler.info('Testing the connection to {0}'.format(identifier), add_to_result=False)
            try:
                _results['result'] = NetworkHelper.check_port_connection(_node_config.client_port, _node_config.ip)
            except Exception as ex:
                errors.append(('test_connection', ex))
                result_handler.warning('Could not test the connection to {0} ({1})'.format(identifier, str(ex)), add_to_result=False)
            finally:
                queue.task_done()

    @classmethod
    @cluster_check
    @expose_to_cli(MODULE, 'collapse-test', HealthCheckCLIRunner.ADDON_TYPE)
    def check_collapse(cls, result_handler, max_collapse_age=3, min_tlx_amount=10):
        """
        Verifies collapsing has occurred for all Arakoons
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
        result_handler.info('Retrieving all collapsing statistics succeeded (duration: {0})'.format(time.time() - start), add_to_result=False)
        for cluster_type, clusters in arakoon_stats.iteritems():
            result_handler.info('Testing the collapse of {0} Arakoons'.format(cluster_type), add_to_result=False)
            for cluster in clusters:
                cluster_name = cluster['cluster_name']
                collapse_result = cluster['collapse_result']
                collapse_result = OrderedDict(sorted(collapse_result.items(), key=lambda item: ExtensionsToolbox.advanced_sort(item[0].ip, separator='.')))
                for node, stats in collapse_result.iteritems():
                    identifier_log = 'Arakoon cluster {0} on node {1}'.format(cluster_name, node.ip)
                    if len(stats['errors']) > 0:
                        # Determine where issues were found
                        for step, exception in stats['errors']:
                            if step == 'build_client':
                                try:
                                    # Raise the thrown exception
                                    raise exception
                                except TimeOutException:
                                    result_handler.warning('Connection to {0} has timed out'.format(identifier_log), code=ErrorCodes.ssh_connection_time)
                                except (socket.error, UnableToConnectException):
                                    result_handler.failure(
                                        'Connection to {0} could not be established'.format(identifier_log), code=ErrorCodes.ssh_connection_fail)
                                except NotAuthenticatedException:
                                    result_handler.skip('Connection to {0} could not be authenticated. This node has no access to the Arakoon node.'.format(identifier_log),
                                                        code=ErrorCodes.ssh_connection_authentication)
                                except Exception:
                                    message = 'Connection to {0} could not be established due to an unhandled exception.'.format(identifier_log)
                                    cls.logger.exception(message)
                                    result_handler.exception(message, code=ErrorCodes.unhandled_exception)
                            elif step == 'stat_dir':
                                try:
                                    raise exception
                                except Exception:
                                    message = 'Unable to list the contents of the tlog directory ({0}) for {1}'.format(node.tlog_dir, identifier_log)
                                    cls.logger.exception(message)
                                    result_handler.exception(message, code=ErrorCodes.unhandled_exception)
                        continue
                    tlx_files = stats['result']['tlx']
                    tlog_files = stats['result']['tlog']
                    if any(item is None for item in [tlx_files, tlog_files]):
                        # Exception occurred but no errors were logged
                        result_handler.exception('Neither the tlx or tlog files could be found in the tlog directory ({0}) for {1}'.format(node.tlog_dir, identifier_log),
                                                 code=ErrorCodes.tlx_tlog_not_found)
                        continue
                    if len(tlog_files) == 0:
                        # A tlog should always be present
                        result_handler.failure('{0} has no open tlog'.format(identifier_log), code=ErrorCodes.tlog_not_found)
                        continue
                    if len(tlx_files) < min_tlx_amount:
                        result_handler.skip('{0} only has {1} tlx, not worth collapsing (required: {2})'.format(identifier_log, len(tlx_files), min_tlx_amount))
                        continue
                    # Compare youngest tlog and oldest tlx timestamp
                    seconds_difference = int(tlog_files[-1][0]) - int(tlx_files[0][0])
                    if max_age_seconds > seconds_difference:
                        result_handler.success('{0} should not be collapsed. The oldest tlx is at least {1} days younger than the youngest tlog (actual age: {2})'.format(identifier_log, max_collapse_age, str(timedelta(seconds=seconds_difference))),
                                               code=ErrorCodes.collapse_ok)
                    else:
                        result_handler.failure('{0} should be collapsed. The oldest tlx is currently {1} old'.format(identifier_log, str(timedelta(seconds=seconds_difference))),
                                               code=ErrorCodes.collapse_not_ok)

    @classmethod
    def _retrieve_stats(cls, result_handler, arakoon_clusters, batch_size=10):
        """
        Retrieve tlog/tlx stat information for a Arakoon cluster concurrently
        Note: this will mutate the given arakoon_clusters dict
        :param result_handler: logging object
        :type result_handler: ovs.extensions.healthcheck.result.HCResults
        :param arakoon_clusters: Information about all arakoon clusters, sorted by type and given config
        :type arakoon_clusters: dict
        :param batch_size: Amount of workers to collect the Arakoon information.
        The amount of workers are dependant on the MaxSessions in the sshd_config
        :return: Dict with tlog/tlx contents for every node config
        Example return:
        {CFG: {ovs.extensions.db.arakooninstaller.ArakoonClusterConfig object: {ovs_extensions.db.arakoon.arakooninstaller.ArakoonNodeConfig object: {'result': {'tlx': [['1513174398', '/opt/OpenvStorage/db/arakoon/config/tlogs/3393.tlx']],
                                                                                                                                                                'tlog': [['1513178427', '/opt/OpenvStorage/db/arakoon/config/tlogs/3394.tlog']]},
                                                                                                                                                     'errors': []},
                                                                                ovs_extensions.db.arakoon.arakooninstaller.ArakoonNodeConfig object: {'result': {'tlx': [['1513166090', '/opt/OpenvStorage/db/arakoon/config/tlogs/3392.tlx'], ['1513174418', '/opt/OpenvStorage/db/arakoon/config/tlogs/3393.tlx']],
                                                                                                                                                                'tlog': [['1513178427', '/opt/OpenvStorage/db/arakoon/config/tlogs/3394.tlog']]}, 'errors': []}, <ovs_extensions.db.arakoon.arakooninstaller.ArakoonNodeConfig object at 0x7fb3a84db090>: {'output': {'tlx': [['1513174358', '/opt/OpenvStorage/db/arakoon/config/tlogs/3393.tlx']], 'tlog': [['1513178427', '/opt/OpenvStorage/db/arakoon/config/tlogs/3394.tlog']]},
                                                                                                                                                      'errors': []}}}
        :rtype: dict
        """
        queue = Queue.Queue()
        clients = {}
        # Prep work
        for cluster_type, clusters in arakoon_clusters.iteritems():
            for cluster in clusters:
                cluster_name = cluster['cluster_name']
                arakoon_config = cluster['config']
                cluster['collapse_result'] = {}
                for node_config in arakoon_config.nodes:
                    result = {'errors': [],
                              'result': {'tlx': [],
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
                    queue.put((cluster_name, node_config, result))

        for _ in xrange(batch_size):
            thread = Thread(target=cls._collapse_worker, args=(queue, clients, result_handler))
            thread.setDaemon(True)  # Setting threads as "daemon" allows main program to exit eventually even if these don't finish correctly.
            thread.start()
        # Wait for all results
        queue.join()
        return arakoon_clusters

    @staticmethod
    def _collapse_worker(queue, clients, result_handler):
        """
        Worker method to retrieve file descriptors
        :param queue: Queue to use
        :param clients: SSHClients to choose from
        :param result_handler: Logging object
        :return: None
        :rtype: NoneType
        """
        while not queue.empty():
            cluster_name, _node_config, _results = queue.get()
            errors = _results['errors']
            output = _results['result']
            identifier = 'Arakoon cluster {0} on node {1}'.format(cluster_name, _node_config.ip)
            result_handler.info('Retrieving collapse information for {0}'.format(identifier), add_to_result=False)
            try:
                _client = clients[_node_config.ip]
                tlog_dir = _node_config.tlog_dir
                path = os.path.join(tlog_dir, '*')
                try:
                    # List the contents of the tlog directory and sort by oldest modification date
                    # Example output:
                    # 01111 file.tlog
                    # 01112 file2.tlog
                    timestamp_files = _client.run('stat -c "%Y %n" {0}'.format(path), allow_insecure=True)
                except Exception as _ex:
                    errors.append(('stat_dir', _ex))
                    raise
                # Sort and separate the timestamp item files
                output['tlx'] = sorted((timestamp_file.split() for timestamp_file in timestamp_files.splitlines()
                                        if timestamp_file.split()[1].endswith('tlx')), key=lambda split: int(split[0]))
                output['tlog'] = sorted((timestamp_file.split() for timestamp_file in timestamp_files.splitlines()
                                         if timestamp_file.split()[1].endswith('tlog')), key=lambda split: int(split[0]))
            except Exception as _ex:
                result_handler.warning('Could not retrieve the collapse information for {0} ({1})'.format(identifier, str(_ex)), add_to_result=False)
            finally:
                queue.task_done()

    @classmethod
    @cluster_check
    @expose_to_cli(MODULE, 'integrity-test', HealthCheckCLIRunner.ADDON_TYPE)
    def verify_integrity(cls, result_handler):
        """
        Verifies that all Arakoon clusters are still responding to client calls
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
                    result_handler.success('Arakoon {0} responded'.format(cluster_name), code=ErrorCodes.arakoon_responded)
                except (ArakoonNoMaster, ArakoonNoMasterResult) as ex:
                    result_handler.failure('Arakoon {0} cannot find a master. (Message: {1})'.format(cluster_name, str(ex)),
                                           code=ErrorCodes.master_none)
                except Exception as ex:
                    cls.logger.exception('Unhandled exception during the integrity check')
                    result_handler.exception('Arakoon {0} threw an unhandled exception. (Message: {1})'.format(cluster_name, str(ex)),
                                             code=ErrorCodes.unhandled_exception)

    @classmethod
    @cluster_check
    @expose_to_cli(MODULE, 'file-descriptors-test', HealthCheckCLIRunner.ADDON_TYPE)
    def check_arakoon_fd(cls, result_handler, fd_limit=30, passed_connections=None):
        """
        Checks all current open tcp file descriptors for all Arakoon clusters in the OVS cluster
        Will raise warnings when these reach a certain threshold
        :param result_handler: Logging object
        :type result_handler: ovs.extensions.healthcheck.result.HCResults
        :param fd_limit: Threshold for the number number of tcp connections for which to start logging warnings
        :type fd_limit: int
        :param passed_connections: checked TCP connections
        :type passed_connections: list
        :return: None
        :rtype: NoneType
        """
        if passed_connections is None:
            passed_connections = ['ESTABLISHED', 'TIME_WAIT']
        warning_threshold = fd_limit * 80 / 100
        error_threshold = fd_limit * 95 / 100

        result_handler.info('Starting Arakoon integrity test', add_to_result=False)
        arakoon_clusters = cls._get_arakoon_clusters(result_handler)
        start = time.time()
        arakoon_fd_results = cls._get_filedescriptors(result_handler, arakoon_clusters)
        result_handler.info('Retrieving all file descriptor information succeeded (duration: {0})'.format(time.time() - start), add_to_result=False)
        for cluster_type, clusters in arakoon_fd_results.iteritems():
            result_handler.info('Checking the file descriptors of {0} Arakoons'.format(cluster_type), add_to_result=False)
            for cluster in clusters:
                cluster_name = cluster['cluster_name']
                fd_result = cluster['fd_result']
                fd_result = OrderedDict(sorted(fd_result.items(), key=lambda item: ExtensionsToolbox.advanced_sort(item[0].ip, separator='.')))
                for node, stats in fd_result.iteritems():
                    identifier_log = 'Arakoon cluster {0} on node {1}'.format(cluster_name, node.ip)
                    if len(stats['errors']) > 0:
                        # Determine where issues were found
                        for step, exception in stats['errors']:
                            if step == 'build_client':
                                try:
                                    # Raise the thrown exception
                                    raise exception
                                except TimeOutException:
                                    result_handler.warning('Connection to {0} has timed out'.format(identifier_log), code=ErrorCodes.ssh_connection_time)
                                except (socket.error, UnableToConnectException):
                                    result_handler.failure(
                                        'Connection to {0} could not be established'.format(identifier_log), code=ErrorCodes.ssh_connection_fail)
                                except NotAuthenticatedException:
                                    result_handler.skip('Connection to {0} could not be authenticated. This node has no access to the Arakoon node.'.format(identifier_log),
                                                        code=ErrorCodes.ssh_connection_authentication)
                                except Exception:
                                    message = 'Connection to {0} could not be established due to an unhandled exception.'.format(identifier_log)
                                    cls.logger.exception(message)
                                    result_handler.exception(message, code=ErrorCodes.unhandled_exception)
                            elif step == 'lsof':
                                try:
                                    raise exception
                                except Exception:
                                    message = 'Unable to list the file descriptors for {0}'.format(identifier_log)
                                    cls.logger.exception(message)
                                    result_handler.exception(message, ErrorCodes.unhandled_exception)
                        continue
                    fds = stats['result']['fds']
                    filtered_fds = [i for i in fds if i.split()[-1].strip('(').strip(')') in passed_connections]
                    if len(filtered_fds) >= warning_threshold:
                        if len(filtered_fds) >= error_threshold:
                            result_handler.warning('Number of TCP connections exceeded the 95% warning threshold for {0}, ({1}/{2})'.format(identifier_log, len(filtered_fds), fd_limit),
                                                   code=ErrorCodes.arakoon_fd_95)
                        else:
                            result_handler.warning('Number of TCP connections exceeded the 80% warning threshold for {0}, ({1}/{2})'.format(identifier_log, len(filtered_fds), fd_limit),
                                                   code=ErrorCodes.arakoon_fd_80)
                    else:
                        result_handler.success('Number of TCP connections for {0} is healthy ({1}/{2})'.format(identifier_log, len(filtered_fds), fd_limit),
                                               code=ErrorCodes.arakoon_fd_ok)

    @classmethod
    def _get_filedescriptors(cls, result_handler, arakoon_clusters, batch_size=10):
        """
        Retrieve tlog/tlx stat information for a Arakoon cluster concurrently
        Note: this will mutate the given arakoon_clusters dict
        :param result_handler: logging object
        :type result_handler: ovs.extensions.healthcheck.result.HCResults
        :param arakoon_clusters: Information about all Arakoon clusters, sorted by type and given config
        :type arakoon_clusters: dict
        :param batch_size: Amount of workers to collect the Arakoon information.
        The amount of workers are dependant on the MaxSessions in the sshd_config
        :return: Dict with file descriptors contents for every node config
        :rtype: dict
        """
        queue = Queue.Queue()
        clients = {}
        # Prep work
        for cluster_type, clusters in arakoon_clusters.iteritems():
            for cluster in clusters:
                cluster_name = cluster['cluster_name']
                arakoon_config = cluster['config']
                cluster['fd_result'] = {}
                for node_config in arakoon_config.nodes:
                    result = {'errors': [],
                              'result': {'fds': []}}
                    # Build SSHClients outside the threads to avoid GIL
                    try:
                        client = clients.get(node_config.ip)
                        if client is None:
                            client = SSHClient(node_config.ip, timeout=5)
                            clients[node_config.ip] = client
                    except Exception as ex:
                        result['errors'].append(('build_client', ex))
                        continue
                    cluster['fd_result'][node_config] = result
                    queue.put((cluster_name, node_config, result))
        service_manager = ServiceFactory.get_manager()
        for _ in xrange(batch_size):
            thread = Thread(target=cls._fd_worker, args=(queue, clients, result_handler, service_manager))
            thread.setDaemon(True)  # Setting threads as "daemon" allows main program to exit eventually even if these don't finish correctly.
            thread.start()
        # Wait for all results
        queue.join()
        return arakoon_clusters

    @staticmethod
    def _fd_worker(queue, clients, result_handler, service_manager):
        """
        Worker method to retrieve file descriptors
        :param queue: Queue to use
        :param clients: SSHClients to choose from
        :param result_handler: Logging object
        :param service_manager: Service manager instance
        :return: None
        :rtype: NoneType
        """
        while not queue.empty():
            cluster_name, _node_config, _results = queue.get(False)
            errors = _results['errors']
            output = _results['result']
            identifier = 'Arakoon cluster {0} on node {1}'.format(cluster_name, _node_config.ip)
            result_handler.info('Retrieving file descriptor information for {0}'.format(identifier), add_to_result=False)
            try:
                client = clients[_node_config.ip]
                try:
                    # Handle config Arakoon
                    cluster_name = cluster_name if cluster_name != 'cacc' else 'config'
                    service_name = ArakoonInstaller.get_service_name_for_cluster(cluster_name)
                    pid = service_manager.get_service_pid(service_name, client)
                    file_descriptors = client.run(['lsof', '-i', '-a', '-p', pid]).splitlines()[1:]
                except Exception as _ex:
                    errors.append(('lsof', _ex))
                    raise
                output['fds'] = file_descriptors
            except Exception as _ex:
                result_handler.warning(
                    'Could not retrieve the file descriptor information for {0} ({1})'.format(identifier, str(_ex)), add_to_result=False)
            finally:
                queue.task_done()
