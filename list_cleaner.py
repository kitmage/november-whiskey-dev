import os
import sys
import json
import requests

HUBSPOT_TOKEN = os.environ.get("HUBSPOT_TOKEN")
LIST_ID = 677  # HubSpot segment/list ID
PROPERTY_NAME = "do_not_send_pci"

BASE_URL = "https://api.hubapi.com"

headers = {
    "Authorization": f"Bearer {HUBSPOT_TOKEN}",
    "Content-Type": "application/json",
}


def get_list_contacts(list_id, properties=None):
    """
    Returns a list of contact records (dicts) from a list/segment.
    Uses v3 CRM Lists API + Batch read for properties.
    """
    # 1) Get all contact IDs in the list
    endpoint = f"{BASE_URL}/crm/v3/lists/{list_id}/memberships"
    after = None
    contact_ids = []

    while True:
        params = {"limit": 100}
        if after:
            params["after"] = after

        resp = requests.get(endpoint, headers=headers, params=params)
        resp.raise_for_status()
        data = resp.json()

        results = data.get("results", [])
        if not results:
            break

        for item in results:
            # Try several likely locations for the contact ID
            contact_id = None

            # Most likely: nested under "contact"
            if isinstance(item, dict):
                if "contact" in item and isinstance(item["contact"], dict):
                    contact_id = item["contact"].get("id")
                # Fallbacks if structure differs
                if contact_id is None:
                    contact_id = item.get("id")  # in case it's flat

            if contact_id is None:
                # Dump one problematic item and exit so we can see structure
                print("Unexpected membership item structure, cannot find contact id:")
                print(json.dumps(item, indent=2))
                raise RuntimeError("Could not locate contact id in membership item")

            contact_ids.append(str(contact_id))

        paging = data.get("paging", {})
        next_link = paging.get("next", {})
        after = next_link.get("after")
        if not after:
            break

    if not contact_ids:
        return []

    # 2) Batch read contacts to get properties
    contacts = []
    batch_endpoint = f"{BASE_URL}/crm/v3/objects/contacts/batch/read"
    batch_size = 100

    for i in range(0, len(contact_ids), batch_size):
        batch_ids = contact_ids[i : i + batch_size]
        payload = {
            "properties": properties or [],
            "inputs": [{"id": cid} for cid in batch_ids],
        }
        resp = requests.post(batch_endpoint, headers=headers, json=payload)
        resp.raise_for_status()
        data = resp.json()
        contacts.extend(data.get("results", []))

    return contacts


def main():
    # Get all contacts in the list with the do_not_send_pci property
    contacts = get_list_contacts(LIST_ID, properties=[PROPERTY_NAME, "email"])

    PCI_ELIGIBLE = []
    PCI_INELIGIBLE = []

    for contact in contacts:
        props = contact.get("properties", {}) or {}
        do_not_send_pci_val = props.get(PROPERTY_NAME)

        # HubSpot booleans often come as 'true'/'false' strings
        is_ineligible = str(do_not_send_pci_val).lower() == "true"

        if is_ineligible:
            PCI_INELIGIBLE.append(contact)
        else:
            PCI_ELIGIBLE.append(contact)

    # Print the two lists (id + email)
    print("=== PCI_ELIGIBLE ===")
    for c in PCI_ELIGIBLE:
        cid = c.get("id")
        email = c.get("properties", {}).get("email")
        print(f"id={cid}, email={email}")

    print("\n=== PCI_INELIGIBLE ===")
    for c in PCI_INELIGIBLE:
        cid = c.get("id")
        email = c.get("properties", {}).get("email")
        print(f"id={cid}, email={email}")


if __name__ == "__main__":
    if not HUBSPOT_TOKEN:
        print("HUBSPOT_TOKEN environment variable is not set.", file=sys.stderr)
        sys.exit(1)
    main()
