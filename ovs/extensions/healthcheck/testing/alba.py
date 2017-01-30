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
