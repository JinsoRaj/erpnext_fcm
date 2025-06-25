import frappe
import requests
import json
import re
import os
from frappe import enqueue
from google.oauth2 import service_account
from google.auth.transport.requests import Request

# Load service account credentials once
SERVICE_ACCOUNT_FILE = os.path.join(os.path.dirname(__file__), "fcm.json")
SCOPES = ["https://www.googleapis.com/auth/firebase.messaging"]

_creds = service_account.Credentials.from_service_account_file(
    SERVICE_ACCOUNT_FILE, scopes=SCOPES
)

def get_access_token():
    global _creds
    if not _creds.valid:
        _creds.refresh(Request())
    return _creds.token

def user_id(doc):
    return frappe.get_all(
        "User Device", filters={"user": doc.for_user}, fields=["device_id"]
    )

@frappe.whitelist()
def send_notification(doc, event):
    for device in user_id(doc):
        enqueue(
            process_notification,
            queue="default",
            now=False,
            device_id=device.device_id,
            doc_type=doc.document_type,
            doc_name=doc.document_name,
            title=doc.subject,
            body=doc.email_content,
        )

def strip_html(text):
    return re.sub(re.compile(r"<.*?>"), "", text or "")

def process_notification(device_id, doc_type, doc_name, title, body):
    title = strip_html(title) or "Notification"
    body = strip_html(body) or ""

    url = f"https://fcm.googleapis.com/v1/projects/{_creds.project_id}/messages:send"
    message = {
        "message": {
            "token": device_id,
            "notification": {"title": title, "body": body},
            "data": {"doctype": doc_type, "docname": doc_name},
        }
    }

    headers = {
        "Authorization": f"Bearer {get_access_token()}",
        "Content-Type": "application/json; UTF-8",
    }

    resp = requests.post(url, headers=headers, json=message)

    if resp.status_code != 200:
        frappe.log_error(
            title=f"FCM v1 Send Error {resp.status_code}",
            message=f"To: {device_id}\nBody: {json.dumps(message, indent=2)}\nResp: {resp.text}",
        )
