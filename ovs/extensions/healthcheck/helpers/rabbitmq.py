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

import json
import requests
from requests import ConnectionError
from StringIO import StringIO
from ovs.dal.lists.storagerouterlist import StorageRouterList
from ovs.extensions.generic.configuration import Configuration
from ovs.extensions.generic.sshclient import SSHClient, UnableToConnectException
from ovs.extensions.services.service import ServiceManager


class RabbitMQ(object):

    NAME = 'rabbitmq-server'
    USER = Configuration.get('/ovs/framework/messagequeue|user')
    PASSWORD = Configuration.get('/ovs/framework/messagequeue|password')
    INTERNAL = Configuration.get('/ovs/framework/messagequeue|metadata.internal')

    def __init__(self, ip):
        """
        Create RabbitMQ object

        :param ip: ip from the server
        :type ip: str
        """
        # check if rabbitmq is available on the ip
        if not RabbitMQ._check_rabbitmq_ip(ip):
            raise ValueError('RabbitMQ on {0} could not be found.'.format(ip))

        self.ip = ip
        if RabbitMQ.INTERNAL:
            self._storagerouter = StorageRouterList.get_by_ip(ip)
            self._client = SSHClient(ip, username='root')

        if not self.check_management_plugin():
            self.enable_management_plugin()

    def list_queues(self):
        """
        List all the queues in RabbitMQ

        :return: tuple with api exit code and list from queues
        :rtype: tuple
        """
        status = self.status()
        if status[0] != 'RUNNING':
            return status[0], 'RabbitMQ is not running.'
        api_output = self.api_request('/api/queues')
        if api_output[0] == 404:
            return api_output
        else:
            queues = {}
            for queue in json.loads(api_output[1].text):
                queues[queue['name']] = queue['messages']
            return api_output[0], queues

    def cluster_status(self):
        """
        Get RabbitMQ cluster status

        :return: tuple with api exit code and list from nodes with their status
        :rtype: tuple
        """
        status = self.status()
        if status[0] != 'RUNNING':
            return status[0], 'RabbitMQ is not running.'
        api_output = self.api_request('/api/nodes')
        if api_output[0] == 404:
            return api_output
        else:
            output = json.loads(api_output[1].text)
            nodes = {}
            for node in output:
                nodes[node['name']] = {'running': node['running'], 'partitions': node['partitions']}
            return api_output[0], nodes

    def partition_status(self):
        """
        Get RabbitMQ nodes who have partitions

        :return: list with rabbitmq nodes who have partitions
        :rtype: list
        """
        status = self.status()
        if status[0] != 'RUNNING':
            return status[0], 'RabbitMQ is not running.'

        cluster_status = self.cluster_status()
        nodes_in_partition = []
        if cluster_status[0] != 200:
            return cluster_status
        else:
            for rabbitmq_info, rabbitmq_status in self.cluster_status()[1].iteritems():
                if len(rabbitmq_status['partitions']) != 0:
                    nodes_in_partition.append(rabbitmq_info.split('@')[1])

        return nodes_in_partition

    def status(self):
        """
        Get status of this RabbitMQ node

        :return: tuple with status and information
        :rtype: tuple
        """
        api_output = self.api_request('/api/overview')
        if api_output[0] == 404 and RabbitMQ.INTERNAL:
            status = ServiceManager.get_service_status('rabbitmq-server', self._client)[0]
            if not self.check_management_plugin():
                if status:
                    return 'RUNNING', 'RabbitMQ is running. Restart RabbitMQ to enable the management plugin.'
                return "UNKNOWN", "Install the management plugin from RabbitMQ."
            else:
                if status:
                    return 'RUNNING', 'RabbitMQ is running. Restart RabbitMQ to enable the management plugin.'
                return 'STOP', api_output[1]
        elif api_output[0] == 404 and not RabbitMQ.INTERNAL:
            return 'STOP', 'RabbitMQ is not running or the management plugin is not installed.'

        return "RUNNING", json.loads(api_output[1].text)

    def check_management_plugin(self):
        """
        Check if the management plugin already is installed on this RabbitMQ

        :return: True/False
        :rtype: bool
        """
        if not RabbitMQ.INTERNAL:
            return 'UNKNOWN', "Unable to check the management plugin, this is not an internal RabbitMQ from ovs."
        output = self._client.run(['rabbitmq-plugins', 'list', '-E'])
        plugins = output.split('\n')

        for plugin in plugins:
            if 'rabbitmq_management' in plugin:
                return True

        return False

    def api_request(self, path):
        """
        Run an api request

        :param path: api path for example: "/api/nodes"
        :type path: str
        :return: tuple with exit code and Response object
        :rtype: tuple
        """
        try:
            r = requests.get('http://{0}:15672{1}'.format(self.ip, path),
                             auth=(RabbitMQ.USER, RabbitMQ.PASSWORD))
            return r.status_code, r
        except ConnectionError as ex:
            return 404, ex.message

    @staticmethod
    def _check_rabbitmq_ip(ip):
        """
        Check if RabbitMQ is running on the requested ip

        :param ip: ip address with a active RabbitMQ node
        :type ip: str
        :return: True/False
        :rtype: bool
        """
        endpoints = Configuration.get('/ovs/framework/messagequeue|endpoints')

        if any(endpoint for endpoint in endpoints if ip in endpoint):
            return True
        return False

    def enable_management_plugin(self):
        """
        Enable the management plugin for this RabbitMQ

        :return: tuple with exit code and information
        :rtype: tuple
        """
        if not RabbitMQ.INTERNAL:
            return 'UNKNOWN', "Unable to enable the management plugin, this is not an internal RabbitMQ from ovs."
        management_enabled = self.check_management_plugin()

        if not management_enabled:
            self._client.run(['rabbitmq-plugins', 'enable', 'rabbitmq_management'])
            self._client.run(['rabbitmqctl', 'set_user_tags', 'ovs', 'administrator'])
            users = StringIO(self._client.run("rabbitmqctl list_users | awk '{ print $1}'", allow_insecure=True))\
                .readlines()
            if 'guest' in users:
                self._client.run(['rabbitmqctl', 'delete_user', 'guest'])
            return self.restart()
        else:
            return self.status()

    def start(self):
        """
        Start the RabbitMQ

        :return: tuple with status and information
        :rtype: tuple
        """
        status = self.status()
        if status[0] != 'STOP':
            return status[0], "RabbitMQ already running."
        if not RabbitMQ.INTERNAL:
            return 'UNKNOWN', "Unable to start, this is not an internal RabbitMQ from ovs."
        ServiceManager.start_service('rabbitmq-server', self._client)
        return self.status()

    def stop(self):
        """
        Stop the RabbitMQ

        :return: tuple with status and information
        :rtype: tuple
        """
        status = self.status()
        if status[0] != 'RUNNING':
            return status[0], "RabbitMQ is not running."
        if not RabbitMQ.INTERNAL:
            return 'UNKNOWN', "Unable to stop, this is not an internal RabbitMQ from ovs."
        ServiceManager.stop_service('rabbitmq-server', self._client)
        return self.status()

    def restart(self):
        """
        Restart the Rabbitmq

        :return: tuple with status and information
        :rtype: tuple
        """
        status = self.status()
        if status[0] != 'RUNNING':
            print "RabbitMQ is not running. Trying to restart the service."
        if not RabbitMQ.INTERNAL:
            return 'UNKNOWN', "Unable to restart, this is not an internal RabbitMQ from ovs."
        ServiceManager.restart_service('rabbitmq-server', self._client)
        return self.status()
