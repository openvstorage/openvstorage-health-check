#!/usr/bin/python

# Copyright (C) 2018 iNuron NV
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

from ovs.dal.lists.albanodelist import AlbaNodeList
from ovs.extensions.generic.configuration import Configuration
from ovs_extensions.generic.ipmi import IPMIController, IPMITimeOutException, IPMICallException
from ovs.extensions.generic.sshclient import SSHClient
from ovs.extensions.generic.system import System
from ovs.extensions.healthcheck.expose_to_cli import expose_to_cli, HealthcheckCLI
from ovs.extensions.healthcheck.logger import Logger


class IPMIHealthCheck(object):
    """
    Healthcheck file to execute multiple IPMI tests
    """
    MODULE = 'ipmi'
    logger = Logger("healthcheck-healthcheck_ipmi")

    @classmethod
    @expose_to_cli(MODULE, 'ipmi-test', HealthcheckCLI.ADDON_TYPE,
                   help='Verify that AlbaNodes can be controlled through IPMI',
                   short_help='Test if AlbaNodes their IPMI info is correct')
    def ipmi_check(cls, result_handler):
        """
        :param result_handler: logging object
        :type result_handler: ovs.extensions.healthcheck.result.HCResults
        :return:
        """
        for albanode in AlbaNodeList.get_albanodes():
            node_id = albanode.node_id
            ipmi_config_loc = '/ovs/alba/asdnodes/{0}/config/ipmi'.format(node_id)
            if not Configuration.exists(ipmi_config_loc):
                result_handler.skip('No IPMI info found on AlbaNode with ID {0}'.format(node_id))
                continue
            ipmi_config = Configuration.get(ipmi_config_loc)
            ip = ipmi_config.get('ip')
            try:
                controller = IPMIController(ip=ip,
                                            username=ipmi_config.get('username'),
                                            password=ipmi_config.get('password'),
                                            client=SSHClient(System.get_my_storagerouter()))
            except:
                result_handler.failure('IPMI settings are not valid for AlbaNode with ID {0}'.format(node_id))
                continue
            try:
                status = controller.status_node().get(ip)
                if status == IPMIController.IPMI_POWER_ON:
                    result_handler.success('IPMI AlbaNode with ID {0} status is POWER ON'.format(node_id))
                elif status == IPMIController.IPMI_POWER_OFF:
                    result_handler.warning('IPMI AlbaNode with ID {0} status is POWER OFF'.format(node_id))
            except IPMITimeOutException as ex:
                result_handler.failure("IPMI AlbaNode with ID {0} timed out: '{1}'".format(node_id, ex))
            except IPMICallException as ex:
                result_handler.failure("IPMI AlbaNode with ID {0} call failed: '{1}'".format(node_id, ex))
            except Exception:
                msg = 'Could not retrieve info through IPMI for AlbaNode with ID {0}'.format(node_id)
                cls.logger.exception(msg)
                result_handler.exception(msg)
