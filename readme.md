[API Ref](https://github.com/HubSpot/hubspot-api-python)

```shell
pip install --upgrade hubspot-api-client
```

Configure Client
```python
from hubspot import HubSpot

api_client = HubSpot(access_token=$HUBSPOT_ACCESS_TOKEN)
```

Get Audit Logs
```pythong
from hubspot.cms.audit_logs import ApiException

try:
    audit_logs_page = api_client.cms.audit_logs.default_api.get_page()
except ApiException as e:
    print("Exception when calling cards_api->create: %s\n" % e)
```
