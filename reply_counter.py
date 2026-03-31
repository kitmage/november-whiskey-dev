import os
import sys
import requests

HUBSPOT_TOKEN = os.environ.get("HUBSPOT_TOKEN")
LIST_ID = 677  # HubSpot segment/list ID
CAMPAIGN_ID = "6afccccd-1f8b-4036-ba17-3eea85f23a05"
PROPERTY_NAME = "do_not_send_pci"

BASE_URL = "https://api.hubapi.com"
