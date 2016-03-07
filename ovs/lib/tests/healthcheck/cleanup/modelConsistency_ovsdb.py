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