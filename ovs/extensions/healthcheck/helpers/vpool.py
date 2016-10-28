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
from ovs.dal.lists.vpoollist import VPoolList
from ovs.extensions.healthcheck.helpers.exceptions import VPoolNotFoundError


class VPoolHelper(object):
    """
    BackendHelper class
    """
    LOGGER = LogHandler.get(source='helpers', name="ci_vpool")

    def __init__(self):
        pass

    @staticmethod
    def get_vpools():
        """
        Get all vpools on a cluster

        :return: vpools
        :rtype: list
        """

        return VPoolList.get_vpools()

    @staticmethod
    def get_vpool_by_name(vpool_name):
        """
        Get a vpool by name

        :param vpool_name: name of a existing vpool
        :type vpool_name: str
        :return: a vpool object
        :rtype: ovs.dal.hybrids.vpool
        """

        vpool = VPoolList.get_vpool_by_name(vpool_name)
        if vpool:
            return vpool
        else:
            raise VPoolNotFoundError("vPool with name `{0}` was not found!".format(vpool_name))
