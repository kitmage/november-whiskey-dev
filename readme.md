[API Ref](https://github.com/HubSpot/hubspot-api-python)

```shell
pip install --upgrade hubspot-api-client
```

Configure Client
```python
from hubspot import HubSpot

api_client = HubSpot(access_token=$HUBSPOT_TOKEN)
```

Get Audit Logs
```python
from hubspot.cms.audit_logs import ApiException

try:
    audit_logs_page = api_client.cms.audit_logs.default_api.get_page()
except ApiException as e:
    print("Exception when calling cards_api->create: %s\n" % e)
```

These variables are set in the environment.
```shell
export HUBSPOT_TOKEN='pat-na2...'
export HUBSPOT_USER_ID='123...'
export HUBSPOT_APP_ID='123...'
export TENANT_ID='123-abc...'
export CLIENT_ID='123-abc'
export CLIENT_SECRET='123_abc...'
export CLIENT_SECRET_ID='123-abc'
export TOM_ID='tom@example.com'
export MIKE_ID='SalesMarketing@example.com'
export ROB_ID='rob@example.com'
```
