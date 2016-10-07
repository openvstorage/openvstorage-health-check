import json
from ovs.dal.lists.albabackendlist import AlbaBackendList

b = map(lambda ab: {
    ab.name: {"is_available_for_vpool": sum(map(lambda preset: preset.get('is_available'),  ab.presets)) >= 1,
              "type": ab.scaling,
              "backend_guid": ab.backend_guid,
              "guid": ab.guid,
              "alba_id": ab.alba_id,
              "disks": map(lambda asd: asd.export(),  ab.osds)}}, AlbaBackendList.get_albabackends())
