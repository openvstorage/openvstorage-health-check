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
from ovs.dal.lists.albabackendlist import AlbaBackendList


class BackendHelper(object):
    """
    BackendHelper class
    """

    @staticmethod
    def get_albabackends():
        """
        Fetches all the alba backends on the cluster

        :return: alba backends
        :rtype: list
        """

        return AlbaBackendList.get_albabackends()
