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


class AlbaTest(object):

    @staticmethod
    def get_disk_safety_buckets_mock():
            return {
                'mybackend02': {
                    '1,2': {
                        'max_disk_safety': 2, 'current_disk_safety': {2: [{'namespace': 'b4eef27e-ef54-4fe8-8658-cdfbda7ceae4_000000065', 'amount_in_bucket': 100}]}
                    }
                },
                'mybackend': {
                    '1,2': {
                        'max_disk_safety': 2, 'current_disk_safety': {1: [{'namespace': 'b4eef27e-ef54-4fe8-8658-cdfbda7ceae4_000000065', 'amount_in_bucket': 100}]}
                    }
                },
                'mybackend-global': {
                    '1,2': {'max_disk_safety': 2, 'current_disk_safety': {0: [{'namespace': 'e88c88c9-632c-4975-b39f-e9993e352560', 'amount_in_bucket': 100}]}},
                    '1,3': {'max_disk_safety': 3, 'current_disk_safety': {0: [{'namespace': 'e88c88c9-632c-4975-b39f-e9993e352560', 'amount_in_bucket': 100}]}}
                },
            }

    @staticmethod
    def get_cache_eviction_mock():
        return {"enable_auto_repair": True,
                "auto_repair_timeout_seconds": 900.0,
                "auto_repair_disabled_nodes": [],
                "enable_rebalance": True,
                "cache_eviction_prefix_preset_pairs": {"b4eef27e-ef54-4fe8-8658-cdfbda7ceae4": "ssdPreset"},
                "redis_lru_cache_eviction": {"host": "10.100.199.171",
                                             "port": 6379,
                                             "key": "alba_lru_38ba0ec2-212f-4439-b13e-b33600376e79"}}

