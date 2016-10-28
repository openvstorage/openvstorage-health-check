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
from ovs.dal.lists.albanodelist import AlbaNodeList


class AlbaNodeHelper(object):

    def __init__(self):
        pass

    @staticmethod
    def get_albanode_by_node_id(alba_node_id):
        """
        Fetches the alba node object with the specified id
        :param alba_node_id: id of the alba node
        :return:
        """
        return AlbaNodeList.get_albanode_by_node_id(alba_node_id)