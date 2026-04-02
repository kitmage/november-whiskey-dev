#!/usr/bin/env python3
"""
create_booking.py

Creates a Microsoft Bookings appointment from the output of availability.py,
always assigning the booking to Mike.

Example:
  python3 create_booking.py \
    --input best_start.json \
    --customer-name "Jane Doe" \
    --customer-email "jane@example.com" \
    --customer-phone "555-555-5555" \
    --service-name "Discovery Call"
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

import requests


GRAPH_ROOT = "https://graph.microsoft.com/v1.0"
TOKEN_URL_TMPL = "https://login.microsoftonline.com/{tenant_id}/oauth2/v2.0/token"

DEFAULT_BOOKING_BUSINESS_EMAIL = "DiscoveryCall@nwmonitoring.com"
DEFAULT_SERVICE_NAME = "30-min meeting"
DEFAULT_TIMEZONE = "Pacific Standard Time"
DEFAULT_DURATION_MINUTES = 30


class GraphError(RuntimeError):
    pass


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Create a Microsoft Bookings appointment from best_start_time JSON.")
    parser.add_argument("--input", help="Path to JSON file from availability.py. If omitted, reads from stdin.")
    parser.add_argument("--booking-business-email", default=DEFAULT_BOOKING_BUSINESS_EMAIL)
    parser.add_argument("--service-name", default=DEFAULT_SERVICE_NAME,
                        help="Exact Bookings service display name.")
    parser.add_argument("--customer-name", required=True)
    parser.add_argument("--customer-email", required=True)
    parser.add_argument("--customer-phone", default="")
    parser.add_argument("--customer-notes", default="")
    parser.add_argument("--timezone", default=DEFAULT_TIMEZONE)
    parser.add_argument("--duration-minutes", type=int, default=DEFAULT_DURATION_MINUTES)
    parser.add_argument("--allow-customer-manage", action="store_true", default=True)
    parser.add_argument("--no-allow-customer-manage", dest="allow_customer_manage", action="store_false")
    parser.add_argument("--sms-notifications", action="store_true", default=False)
    parser.add_argument("--opt-out-of-customer-email", action="store_true", default=False)
    parser.add_argument("--is-online", action="store_true", default=True)
    parser.add_argument("--no-is-online", dest="is_online", action="store_false")
    parser.add_argument("--dry-run", action="store_true")
    return parser.parse_args()


def load_env(name: str) -> str:
    value = os.getenv(name)
    if not value:
        raise RuntimeError(f"Missing required env var: {name}")
    return value


def read_input_json(path: Optional[str]) -> Dict[str, Any]:
    if path:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    return json.load(sys.stdin)


def require_best_start(payload: Dict[str, Any]) -> str:
    best = payload.get("best_start_time")
    if not isinstance(best, dict):
        raise RuntimeError('Input JSON must contain object key "best_start_time".')
    start = best.get("start")
    if not start or not isinstance(start, str):
        raise RuntimeError('"best_start_time.start" is missing or invalid.')
    return start


def get_access_token() -> str:
    tenant_id = load_env("TENANT_ID")
    client_id = load_env("CLIENT_ID")
    client_secret = load_env("CLIENT_SECRET")

    token_url = TOKEN_URL_TMPL.format(tenant_id=tenant_id)
    resp = requests.post(
        token_url,
        data={
            "client_id": client_id,
            "client_secret": client_secret,
            "scope": "https://graph.microsoft.com/.default",
            "grant_type": "client_credentials",
        },
        timeout=30,
    )
    if not resp.ok:
        raise GraphError(f"Token request failed: {resp.status_code} {resp.text}")
    data = resp.json()
    token = data.get("access_token")
    if not token:
        raise GraphError(f"No access_token in token response: {data}")
    return token


class GraphClient:
    def __init__(self, token: str) -> None:
        self.session = requests.Session()
        self.session.headers.update({
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        })

    def post(self, path: str, body: Dict[str, Any]) -> Dict[str, Any]:
        url = f"{GRAPH_ROOT}{path}"
        resp = self.session.post(url, data=json.dumps(body), timeout=30)
        if not resp.ok:
            raise GraphError(f"POST {url} failed: {resp.status_code} {resp.text}")
        return resp.json()


def paginate_collection(client: GraphClient, path: str, params: Optional[Dict[str, Any]] = None) -> List[Dict[str, Any]]:
    items: List[Dict[str, Any]] = []
    next_url: Optional[str] = f"{GRAPH_ROOT}{path}"
    next_params = params

    while next_url:
        resp = client.session.get(next_url, params=next_params, timeout=30)
        if not resp.ok:
            raise GraphError(f"GET {next_url} failed: {resp.status_code} {resp.text}")
        data = resp.json()
        items.extend(data.get("value", []))
        next_url = data.get("@odata.nextLink")
        next_params = None

    return items


def find_booking_business(client: GraphClient, booking_business_email: str) -> Dict[str, Any]:
    businesses = paginate_collection(client, "/solutions/bookingBusinesses")
    target = booking_business_email.strip().lower()

    for b in businesses:
        if str(b.get("id", "")).lower() == target:
            return b
        if str(b.get("email", "")).lower() == target:
            return b

    raise RuntimeError(
        f'Could not find booking business with email/id "{booking_business_email}". '
        f"Available bookingBusinesses found: {[b.get('id') for b in businesses]}"
    )


def list_services(client: GraphClient, booking_business_id: str) -> List[Dict[str, Any]]:
    return paginate_collection(client, f"/solutions/bookingBusinesses/{booking_business_id}/services")


def choose_service(services: List[Dict[str, Any]], service_name: Optional[str]) -> Dict[str, Any]:
    if not services:
        raise RuntimeError("No services found in this Bookings business.")

    if service_name:
        target = service_name.strip().lower()
        for service in services:
            if str(service.get("displayName", "")).strip().lower() == target:
                return service
        raise RuntimeError(
            f'Service "{service_name}" not found. '
            f"Available services: {[s.get('displayName') for s in services]}"
        )

    return services[0]


def list_staff_members(client: GraphClient, booking_business_id: str) -> List[Dict[str, Any]]:
    return paginate_collection(client, f"/solutions/bookingBusinesses/{booking_business_id}/staffMembers")


def resolve_mike_staff_member_id(staff_members: List[Dict[str, Any]]) -> List[str]:
    mike_email = load_env("MIKE_ID").strip().lower()

    for member in staff_members:
        if str(member.get("emailAddress", "")).strip().lower() == mike_email:
            return [member["id"]]

    raise RuntimeError(
        f'Mike staff member not found for MIKE_ID="{mike_email}". '
        f"Available staff emails: {[m.get('emailAddress') for m in staff_members]}"
    )


def list_customers(client: GraphClient, booking_business_id: str) -> List[Dict[str, Any]]:
    return paginate_collection(client, f"/solutions/bookingBusinesses/{booking_business_id}/customers")


def get_or_create_customer(
    client: GraphClient,
    booking_business_id: str,
    customer_name: str,
    customer_email: str,
    customer_phone: str,
) -> Dict[str, Any]:
    customers = list_customers(client, booking_business_id)
    target = customer_email.strip().lower()

    for customer in customers:
        if str(customer.get("emailAddress", "")).strip().lower() == target:
            return customer

    body = {
        "@odata.type": "#microsoft.graph.bookingCustomer",
        "displayName": customer_name,
        "emailAddress": customer_email,
    }
    if customer_phone:
        body["phones"] = [{
            "number": customer_phone,
            "type": "mobile",
        }]

    return client.post(f"/solutions/bookingBusinesses/{booking_business_id}/customers", body)


def make_datetime_pair(start_str: str, duration_minutes: int) -> tuple[str, str]:
    start_dt = datetime.fromisoformat(start_str)
    end_dt = start_dt + timedelta(minutes=duration_minutes)
    return start_dt.isoformat(), end_dt.isoformat()


def create_appointment(
    client: GraphClient,
    booking_business_id: str,
    service: Dict[str, Any],
    customer: Dict[str, Any],
    args: argparse.Namespace,
    start_str: str,
) -> Dict[str, Any]:
    start_iso, end_iso = make_datetime_pair(start_str, args.duration_minutes)
    staff_member_ids = resolve_mike_staff_member_id(
        list_staff_members(client, booking_business_id)
    )

    customer_info = {
        "@odata.type": "#microsoft.graph.bookingCustomerInformation",
        "customerId": customer["id"],
        "name": args.customer_name,
        "emailAddress": args.customer_email,
    }
    if args.customer_phone:
        customer_info["phone"] = args.customer_phone
    if args.customer_notes:
        customer_info["notes"] = args.customer_notes

    body: Dict[str, Any] = {
        "@odata.type": "#microsoft.graph.bookingAppointment",
        "customerTimeZone": args.timezone,
        "customerName": args.customer_name,
        "customerEmailAddress": args.customer_email,
        "customerPhone": args.customer_phone or None,
        "customerNotes": args.customer_notes or None,
        "smsNotificationsEnabled": args.sms_notifications,
        "isCustomerAllowedToManageBooking": args.allow_customer_manage,
        "isLocationOnline": args.is_online,
        "optOutOfCustomerEmail": args.opt_out_of_customer_email,
        "serviceId": service["id"],
        "serviceName": service.get("displayName"),
        "duration": f"PT{args.duration_minutes}M",
        "staffMemberIds": staff_member_ids,
        "maximumAttendeesCount": 1,
        "filledAttendeesCount": 1,
        "customers@odata.type": "#Collection(microsoft.graph.bookingCustomerInformation)",
        "customers": [customer_info],
        "start": {
            "@odata.type": "#microsoft.graph.dateTimeTimeZone",
            "dateTime": start_iso,
            "timeZone": args.timezone,
        },
        "end": {
            "@odata.type": "#microsoft.graph.dateTimeTimeZone",
            "dateTime": end_iso,
            "timeZone": args.timezone,
        },
    }

    if args.dry_run:
        return {
            "dry_run": True,
            "assigned_to": load_env("MIKE_ID"),
            "booking_business_id": booking_business_id,
            "service_id": service["id"],
            "service_name": service.get("displayName"),
            "staff_member_ids": staff_member_ids,
            "payload": body,
        }

    return client.post(f"/solutions/bookingBusinesses/{booking_business_id}/appointments", body)


def main() -> None:
    args = parse_args()
    input_payload = read_input_json(args.input)
    best_start = require_best_start(input_payload)

    token = get_access_token()
    client = GraphClient(token)

    business = find_booking_business(client, args.booking_business_email)
    booking_business_id = business["id"]

    services = list_services(client, booking_business_id)
    service = choose_service(services, args.service_name)

    customer = get_or_create_customer(
        client=client,
        booking_business_id=booking_business_id,
        customer_name=args.customer_name,
        customer_email=args.customer_email,
        customer_phone=args.customer_phone,
    )

    result = create_appointment(
        client=client,
        booking_business_id=booking_business_id,
        service=service,
        customer=customer,
        args=args,
        start_str=best_start,
    )

    print(json.dumps({
        "assigned_to": load_env("MIKE_ID"),
        "booking_business_id": booking_business_id,
        "booking_business_email": business.get("email"),
        "service_id": service.get("id"),
        "service_name": service.get("displayName"),
        "customer_id": customer.get("id"),
        "appointment": result,
    }, indent=2, default=str))


if __name__ == "__main__":
    main()
