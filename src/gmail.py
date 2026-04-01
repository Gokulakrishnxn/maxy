import os
import base64
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build

SCOPES = [
    "https://www.googleapis.com/auth/gmail.readonly",
    "https://www.googleapis.com/auth/gmail.send",
    "https://www.googleapis.com/auth/gmail.modify",
]

from maxy_home import CREDS_FILE, TOKEN_FILE

def get_service():
    creds = None
    if os.path.exists(TOKEN_FILE):
        creds = Credentials.from_authorized_user_file(TOKEN_FILE, SCOPES)
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file(CREDS_FILE, SCOPES)
            creds = flow.run_local_server(port=0)
        with open(TOKEN_FILE, "w") as f:
            f.write(creds.to_json())
    return build("gmail", "v1", credentials=creds)

def get_unread_emails(max_results=5):
    service = get_service()
    results = service.users().messages().list(
        userId="me",
        labelIds=["INBOX", "UNREAD"],
        maxResults=max_results
    ).execute()
    messages = results.get("messages", [])
    if not messages:
        return []
    emails = []
    for msg in messages:
        full = service.users().messages().get(
            userId="me", id=msg["id"], format="full"
        ).execute()
        headers = {h["name"]: h["value"] for h in full["payload"]["headers"]}
        subject = headers.get("Subject", "(no subject)")
        sender  = headers.get("From", "unknown")
        date    = headers.get("Date", "")
        body = ""
        payload = full["payload"]
        if "parts" in payload:
            for part in payload["parts"]:
                if part["mimeType"] == "text/plain":
                    data = part["body"].get("data", "")
                    if data:
                        body = base64.urlsafe_b64decode(data).decode("utf-8", errors="ignore")
                        break
        elif "body" in payload:
            data = payload["body"].get("data", "")
            if data:
                body = base64.urlsafe_b64decode(data).decode("utf-8", errors="ignore")
        emails.append({
            "id":      msg["id"],
            "subject": subject,
            "from":    sender,
            "date":    date,
            "body":    body[:500]
        })
    return emails

def send_email(to, subject, body):
    service = get_service()
    message = MIMEMultipart()
    message["to"]      = to
    message["subject"] = subject
    message.attach(MIMEText(body, "plain"))
    raw = base64.urlsafe_b64encode(message.as_bytes()).decode()
    service.users().messages().send(
        userId="me",
        body={"raw": raw}
    ).execute()
    return f"Email sent to {to}"

def mark_as_read(msg_id):
    service = get_service()
    service.users().messages().modify(
        userId="me",
        id=msg_id,
        body={"removeLabelIds": ["UNREAD"]}
    ).execute()

def format_emails_for_maxy(emails):
    if not emails:
        return "No unread emails."
    lines = []
    for i, e in enumerate(emails, 1):
        lines.append(
            f"{i}. FROM: {e['from']}\n"
            f"   SUBJECT: {e['subject']}\n"
            f"   DATE: {e['date']}\n"
            f"   PREVIEW: {e['body'][:200]}\n"
        )
    return "\n".join(lines)

if __name__ == "__main__":
    emails = get_unread_emails(3)
    print(format_emails_for_maxy(emails))
