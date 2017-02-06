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

from ovs.dal.hybrids.vdisk import VDisk
from ovs.dal.lists.vdisklist import VDiskList
from ovs.dal.lists.vpoollist import VPoolList
from ovs.extensions.healthcheck.helpers.exceptions import VPoolNotFoundError, VDiskNotFoundError


class VDiskHelper(object):
    """
    vDiskHelper class
    """

    def __init__(self):
        pass

    @staticmethod
    def get_vdisk_by_name(vdisk_name, vpool_name):
        """
        Fetch disk partitions by disk guid
        :param vdisk_name: location of a vdisk on a vpool
                           (e.g. /mnt/vpool/test.raw = test.raw, /mnt/vpool/volumes/test.raw = volumes/test.raw )
        :type vdisk_name: str
        :param vpool_name: name of a existing vpool
        :type vpool_name: str
        :return: a vdisk object
        :rtype: ovs.dal.hybrids.vdisk.VDisk
        """
        vpool = VPoolList.get_vpool_by_name(vpool_name)
        if vpool:
            vdisk = VDiskList.get_by_devicename_and_vpool('/{0}'.format(vdisk_name), vpool)
            if vdisk:
                return vdisk
            else:
                raise VDiskNotFoundError("VDisk with name `{0}` not found!".format(vdisk_name))
        else:
            raise VPoolNotFoundError("vPool with name `{0}` cannot be found!".format(vpool_name))

    @staticmethod
    def get_vdisk_by_guid(vdisk_guid):
        """
        Fetch vdisk object by vdisk guid
        :param vdisk_guid: guid of a existing vdisk
        :type vdisk_guid: str
        :return: a vdisk object
        :rtype: ovs.dal.hybrids.vdisk.VDisk
        """
        return VDisk(vdisk_guid)

