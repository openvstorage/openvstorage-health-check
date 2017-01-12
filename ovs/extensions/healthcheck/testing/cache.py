import time
from ovs.extensions.healthcheck.helpers.cache import CacheHelper

assert CacheHelper.set(item='foo', key='bar')
assert CacheHelper.get(key='bar') == 'foo'
time.sleep(1)  # sleep 1 second to cause difference in time_added vs. time_updated
assert CacheHelper.update(key='bar', item='foo2')
result = CacheHelper.get(key='bar', raw=True)
assert type(result) == dict
assert result['time_added'] != result['time_updated']
assert CacheHelper.delete(key='bar')
