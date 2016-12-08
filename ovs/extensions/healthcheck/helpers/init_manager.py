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

import subprocess
from ovs.log.log_handler import LogHandler
from ovs.extensions.generic.sshclient import SSHClient
from ovs.extensions.healthcheck.helpers.exceptions import UnsupportedInitManager


class InitManagerSupported(object):
    """
    Container method for certain variables
    """

    INIT = "init"
    SYSTEMD = "systemd"


class InitManager(object):
    """
    BackendHelper class
    """
    LOGGER = LogHandler.get(source='helpers', name="ci_initmanager")
    SYSTEMD_BASEDIR = "/lib/systemd/system"
    UPSTART_BASEDIR = "/etc/init"

    RAW_INIT_MANAGER = str(subprocess.check_output('cat /proc/1/comm', shell=True)).strip()

    if hasattr(InitManagerSupported, RAW_INIT_MANAGER.upper()):
        INIT_MANAGER = getattr(InitManagerSupported, RAW_INIT_MANAGER.upper())
    else:
        raise UnsupportedInitManager("Init manager `{0}` is not supported".format(RAW_INIT_MANAGER))

    def __init__(self):
        pass

    @staticmethod
    def service_exists(service_name, ip):
        """
        Check if a service exists

        :param service_name: name of a existing service
        :type service_name: str
        :param ip: ip address of a node
        :type ip: str
        :return: if the service exists
        :rtype: bool
        """
        client = SSHClient(ip, username='root')

        if InitManager.INIT_MANAGER == InitManagerSupported.INIT:
            return client.file_exists("{0}/{1}.conf".format(InitManager.UPSTART_BASEDIR, service_name))
        elif InitManager.INIT_MANAGER == InitManagerSupported.SYSTEMD:
            return client.file_exists("{0}/{1}.service".format(InitManager.SYSTEMD_BASEDIR, service_name))

    @staticmethod
    def service_running(service_name, ip):
        """
        Check if a service is running

        :param service_name: name of a existing service
        :type service_name: str
        :param ip: ip address of a node
        :type ip: str
        :return: if the service is running
        :rtype: bool
        """
        client = SSHClient(ip, username='root')

        if InitManager.INIT_MANAGER == InitManagerSupported.INIT:
            output = client.run(['service', service_name, 'status'])
            return output.split()[1] == "start/running,"
        elif InitManager.INIT_MANAGER == InitManagerSupported.SYSTEMD:
            try:
                output = client.run(['systemctl', 'is-active', '{0}.service'.format(service_name)])
            except subprocess.CalledProcessError:
                InitManager.LOGGER.warning("Exception caught when checking service `{0}` on node with ip `{1}`"
                                           .format(service_name, ip))
                return False

            # if not failed, check output
            return output == 'active'

    @staticmethod
    def get_local_services(prefix, ip):
        """
        Fetch the local services with a grep on the chosen prefix

        :param prefix: substring to search for in the local service list
        :type prefix: str
        :param ip: ip address of a node
        :type ip: str
        :return: list of services
        :rtype: list
        """

        if InitManager.INIT_MANAGER == InitManagerSupported.INIT:
            return InitManager._list_local_services(prefix=prefix, ip=ip, basedir=InitManager.UPSTART_BASEDIR)
        elif InitManager.INIT_MANAGER == InitManagerSupported.SYSTEMD:
            return InitManager._list_local_services(prefix=prefix, ip=ip, basedir=InitManager.SYSTEMD_BASEDIR)

    @staticmethod
    def _list_local_services(prefix, ip, basedir):
        """
        List the local services

        :param prefix: substring to search for in the local service list
        :type prefix: str
        :param ip: ip address of a node
        :type ip: str
        :return: list of services
        :param basedir: absolute path where to search for the services
        :type basedir: ovs.extensions.healthcheck.helpers.init_manager.InitManager.BASEDIR
        :rtype: list
        """

        client = SSHClient(ip, username='root')
        return [service.split('.')[0] for service in client.run("ls {0} | grep {1}-".format(basedir, prefix),
                                                                allow_insecure=True).split()]
