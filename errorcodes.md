# Error codes
The json output from the healthcheck returns status codes for every provided message.
These error codes can be used for internal alerting purposes.

## Error code ranges
There are a couple ranges reserved for the OpenvStorage healthcheck. When adding your own tests to the healthcheck,
these ranges should be respected.

| Ranges        | Component     |
| ------------- | ------------- |
| HC0-999       | Healthcheck   |
| FWK0-999      | Framework     |
| ALBA0-999     | Alba          |
| ARA0-999      | Arakoon       |
| VOL0-999      | Volumedriver  |

****
## Current code overview
### Framework

### Alba

### Arakoon

### Volumedriver

