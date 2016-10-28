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
Configuration module
"""

import json


class ConfigurationProduct(object):
    """
    Configuration Products
    """

    ARAKOON = "arakoon"
    VPOOL = "vpool"
    BACKEND = "backend"
    ASD = "asd"
    FRAMEWORK = "framework"


class ConfigurationManager(object):
    """
    Configuration Manager
    """

    CONFIG_MANAGER_LOCATION = "/opt/OpenvStorage/config/framework.json"
    ETCD_PORT = "2379"
    ETCD_IP = "127.0.0.1"
    ARAKOON_CONFIG_LOCATION = "?ini=%2Fopt%2FOpenvStorage%2Fconfig%2Farakoon_cacc.ini"

    @staticmethod
    def get_config_manager():
        with open(ConfigurationManager.CONFIG_MANAGER_LOCATION) as data_file:
            data = json.load(data_file)

        return data['configuration_store']

    @staticmethod
    def get_config_file_path(*args, **kwargs):
        """
        Gets the location of a certain service via local or etcd path

        :param args: arguments
        :type args: tuple
        :param kwargs: arguments
        :type kwargs: dict
        :return: location of a config file
        :rtype: str
        """

        config_manager = ConfigurationManager.get_config_manager()

        if config_manager == "etcd":
            if kwargs['product'] == ConfigurationProduct.ARAKOON:
                return "etcd://127.0.0.1:2379/ovs/arakoon/{0}/config".format(kwargs['arakoon_name'])
            elif kwargs['product'] == ConfigurationProduct.VPOOL:
                return "etcd://127.0.0.1:2379/ovs/vpools/{0}/hosts/{1}/config".format(kwargs['vpool_guid'],
                                                                                      kwargs['vpool_name'] +
                                                                                      kwargs['node_id'])
            elif kwargs['product'] == ConfigurationProduct.FRAMEWORK:
                return "etcd://127.0.0.1:2379/ovs/framework"
            else:
                raise \
                    NotImplementedError("Configuration product `{0}` is not yet implemented".format(kwargs['product']))
        elif config_manager == "arakoon":
            if kwargs['product'] == ConfigurationProduct.ARAKOON:
                return "arakoon://config/ovs/arakoon/{0}/config{1}".format(kwargs['arakoon_name'],
                                                                           ConfigurationManager.ARAKOON_CONFIG_LOCATION)
            elif kwargs['product'] == ConfigurationProduct.VPOOL:
                return "arakoon://config/ovs/vpools/{0}/hosts/{1}/config{2}" \
                       .format(kwargs['vpool_guid'], kwargs['vpool_name']+kwargs['node_id'],
                               ConfigurationManager.ARAKOON_CONFIG_LOCATION)
            elif kwargs['product'] == ConfigurationProduct.FRAMEWORK:
                return "arakoon://config/ovs/framework{0}".format(ConfigurationManager.ARAKOON_CONFIG_LOCATION)
            else:
                raise \
                    NotImplementedError("Configuration product `{0}` is not yet implemented".format(kwargs['product']))
        else:
            raise NotImplementedError("Config manager `{0}` is not yet implemented".format(config_manager))
