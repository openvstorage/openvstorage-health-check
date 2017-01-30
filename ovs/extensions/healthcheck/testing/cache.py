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
import time
from ovs.extensions.healthcheck.helpers.cache import CacheHelper


class CacheTest(object):

    @staticmethod
    def test_cache_operations():
        assert CacheHelper.set(item='foo', key='bar')
        assert CacheHelper.get(key='bar') == 'foo'
        time.sleep(1)  # sleep 1 second to cause difference in time_added vs. time_updated
        assert CacheHelper.update(key='bar', item='foo2')
        result = CacheHelper.get(key='bar', raw=True)
        assert type(result) == dict
        assert result['time_added'] != result['time_updated']
        assert CacheHelper.delete(key='bar')

    @staticmethod
    def _test_type_handling():
        """
        Test if CacheHelper can cope with all primitive types
        :return:
        """
        testers = {
            'integer': 1,
            'double': 2.0,
            'string': "test",
            'literal': 'test',
            'dict': {"test": "test"},
            'list': [1, 2],
            'set': {1, 2}
        }

        for key, value in testers.iteritems():
            try:
                CacheHelper.set(value)
            except Exception as e:
                print "Could not set {0} type. Got {1}".format(key, e.message)
            try:
                CacheHelper.append(value)
                print "Appended {0}".format(key)
            except Exception as e:
                print "Could not append {0} type. Got {1}".format(key, e.message)
            try:
                data = CacheHelper.get()
                print data
            except Exception as e:
                print "Could not get {0} type. Got {1}".format(key, e.message)
        CacheHelper.delete()
