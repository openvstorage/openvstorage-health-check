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
import time

from ovs.dal.lists.storagedriverlist import StorageDriverList
from ovs.log.log_handler import LogHandler


class StoragedriverHelper(object):

    """
    StoragedriverHelper class
    """
    LOGGER = LogHandler.get(source="helpers", name="ci_storagedriver_helper")

    def __init__(self):
        pass

    @staticmethod
    def get_storagedrivers_by_storagerouterguid(storagerouter_guid):
        """
        Get the storagedriver connected to a storagerouter by its guid

        :param storagerouter_guid: guid of a storagerouter
        :type storagerouter_guid: str
        :return: collection of available storagedrivers on the storagerouter
        :rtype: list
        """

        return StorageDriverList.get_storagedrivers_by_storagerouter(storagerouter_guid)

    @staticmethod
    def get_by_storagedriver_id(storagedriver_id):
        """
        Returns the storage ip of the Storagedriver
        :param storagedriver_id: id of the storagedriver
        :type str
        :return:
        """
        return StorageDriverList.get_by_storagedriver_id(storagedriver_id)
