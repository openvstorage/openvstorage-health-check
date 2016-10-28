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
            output = client.run('service {0} status'.format(service_name))
            return output.split()[1] == "start/running,"
        elif InitManager.INIT_MANAGER == InitManagerSupported.SYSTEMD:
            try:
                output = client.run('systemctl is-active {0}.service'.format(service_name))
            except subprocess.CalledProcessError:
                InitManager.LOGGER.warning("Exception caught when checking service `{0}` on node with ip `{1}`"
                                           .format(service_name, ip))
                return False

            # if not failed, check output
            return output == 'active'
