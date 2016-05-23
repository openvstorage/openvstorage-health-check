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

from ovs.dal.lists.vpoollist import VPoolList
import volumedriver.storagerouter.storagerouterclient as src

for vp in VPoolList.get_vpools():
    voldrv_client = src.LocalStorageRouterClient("/opt/OpenvStorage/config/storagedriver/storagedriver/vmstor.json")

    voldrv_volume_list = voldrv_client.list_volumes()
    model_vdisk_list = vp.vdisks

    for vdisk in model_vdisk_list:
        if not vdisk.volume_id in voldrv_volume_list:
            #print vdisk
            mds = vdisk.mds_services
            if len(mds) == 0:
                print "no mds"
                vdisk.delete()
            else:
                for md in mds:
                    print "mds"
                    md.delete()
                vdisk.delete()