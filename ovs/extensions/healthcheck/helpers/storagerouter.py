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

from ovs.dal.lists.storagerouterlist import StorageRouterList
from ovs.dal.hybrids.storagerouter import StorageRouter
from ovs.extensions.generic.system import System
from ovs.log.log_handler import LogHandler


class StoragerouterHelper(object):

    """
    StoragerouterHelper class
    """

    @staticmethod
    def get_by_machine_id(machine_id):
        """
        Fetch a dal machine by id

        :param machine_id: id of the machine
        :return:
        """

        return StorageRouterList.get_by_machine_id(machine_id)
