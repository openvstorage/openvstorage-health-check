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

from ovs.log.log_handler import LogHandler
from ovs.extensions.generic.sshclient import SSHClient
from ovs.extensions.healthcheck.helpers.init_manager import InitManager, InitManagerSupported


class SystemHelper(object):
    """
    BackendHelper class
    """
    LOGGER = LogHandler.get(source='helpers', name="ci_system")

    def __init__(self):
        pass

    @staticmethod
    def get_non_running_ovs_services(storagerouter_ip):
        """
        Get all non-running ovs services

        :param storagerouter_ip: ip address of a existing storagerouter
        :type storagerouter_ip: str
        :return: list of non running ovs services
        :rtype: list
        """
        client = SSHClient(storagerouter_ip, username='root')

        if InitManager.INIT_MANAGER == InitManagerSupported.INIT:
            ovs_services = [service for service in client.dir_list(InitManager.UPSTART_BASEDIR) if 'ovs-' in service]
            return [ovs_service.split('.')[0] for ovs_service in ovs_services
                    if not InitManager.service_running(ovs_service.split('.')[0], storagerouter_ip)]
        elif InitManager.INIT_MANAGER == InitManagerSupported.SYSTEMD:
            ovs_services = [service for service in client.dir_list(InitManager.SYSTEMD_BASEDIR) if 'ovs-' in service]
            return [ovs_service.split('.')[0] for ovs_service in ovs_services
                    if not InitManager.service_running(ovs_service.split('.')[0], storagerouter_ip)]

    @staticmethod
    def get_missing_packages(ip, required_packages):
        """
        Get all missing packages based on required packages

        :param ip: ip address of a server
        :type ip: str
        :param required_packages: a list of required packages (e.g. ['openvstorage', 'qemu', 'fio'])
        :type required_packages: list
        :return: list of missing packages
        :rtype: list
        """
        client = SSHClient(ip, username='root')
        return [package for package in required_packages
                if len(client.run("dpkg -l | grep {0} | tr -s ' '".format(package)).split()) == 0]
