import smtplib
import streamlit as st
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

def get_smtp_config():
    try:
        return {
            "host":     st.secrets.get("SMTP_HOST", "smtp.gmail.com"),
            "port":     int(st.secrets.get("SMTP_PORT", 587)),
            "user":     st.secrets.get("SMTP_USER", ""),
            "password": st.secrets.get("SMTP_PASSWORD", ""),
            "from":     st.secrets.get("FROM_EMAIL", ""),
        }
    except Exception:
        return {"host": "smtp.gmail.com", "port": 587, "user": "", "password": "", "from": ""}

def send_email(to_email: str, subject: str, body: str) -> tuple[bool, str]:
    cfg = get_smtp_config()
    if not cfg["user"] or not cfg["password"]:
        return False, "SMTP credentials not configured. Go to Settings to configure email."
    try:
        msg = MIMEMultipart("alternative")
        msg["Subject"] = subject
        msg["From"]    = cfg["from"] or cfg["user"]
        msg["To"]      = to_email
        msg.attach(MIMEText(body, "plain"))
        with smtplib.SMTP(cfg["host"], cfg["port"]) as server:
            server.ehlo()
            server.starttls()
            server.login(cfg["user"], cfg["password"])
            server.sendmail(cfg["from"] or cfg["user"], to_email, msg.as_string())
        return True, "Email sent successfully."
    except Exception as e:
        return False, str(e)

# ── Templates ──────────────────────────────────────────────────────────────────

def template_confirmation(name: str, event_name: str, event_date: str,
                           event_time: str, venue: str, city: str) -> dict:
    return {
        "subject": f"Event Confirmed: {event_name} on {event_date}",
        "body": (
            f"Dear {name},\n\n"
            f"This is to confirm your participation in the NH Humanities & CDFA "
            f"Community Conversations program.\n\n"
            f"Event Details:\n"
            f"  Event:   {event_name}\n"
            f"  Date:    {event_date}\n"
            f"  Time:    {event_time}\n"
            f"  Venue:   {venue}\n"
            f"  City:    {city}, NH\n\n"
            f"Please don't hesitate to reach out if you have any questions or need "
            f"additional information.\n\n"
            f"Thank you for your partnership in this important community initiative.\n\n"
            f"Best regards,\nCommunity Conversations Coordinator\n"
            f"NH Humanities & CDFA"
        ),
    }

def template_reminder(name: str, event_name: str, event_date: str,
                       event_time: str, venue: str, city: str) -> dict:
    return {
        "subject": f"Reminder: {event_name} on {event_date}",
        "body": (
            f"Dear {name},\n\n"
            f"This is a friendly reminder that the following Community Conversations "
            f"event is coming up soon.\n\n"
            f"Event Details:\n"
            f"  Event:   {event_name}\n"
            f"  Date:    {event_date}\n"
            f"  Time:    {event_time}\n"
            f"  Venue:   {venue}\n"
            f"  City:    {city}, NH\n\n"
            f"Please confirm you are all set and reach out if you need anything before "
            f"the event.\n\n"
            f"Looking forward to a great event!\n\n"
            f"Best regards,\nCommunity Conversations Coordinator\n"
            f"NH Humanities & CDFA"
        ),
    }

def template_post_event(name: str, event_name: str, event_date: str,
                         role: str = "participant") -> dict:
    return {
        "subject": f"Thank You for {('Hosting' if role=='host' else 'Facilitating')} {event_name}",
        "body": (
            f"Dear {name},\n\n"
            f"Thank you so much for your involvement in the NH Humanities & CDFA "
            f"Community Conversations event held on {event_date}.\n\n"
            f"Your contribution as a {'host' if role=='host' else 'facilitator'} was "
            f"invaluable to making this event a success for our community.\n\n"
            f"We would love to hear your feedback about the event. Please take a moment "
            f"to share any reflections, suggestions, or observations.\n\n"
            f"Regarding payment: If you have not already done so, please submit your "
            f"invoice at your earliest convenience so we can process your payment promptly.\n\n"
            f"Thank you again for your partnership in this important initiative.\n\n"
            f"Warm regards,\nCommunity Conversations Coordinator\n"
            f"NH Humanities & CDFA"
        ),
    }
