import streamlit as st
import time
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from utils.database import (
    log_activity, add_notification,
    get_all_hosts, get_all_facilitators, get_all_events,
    get_all_nhh, get_all_cdfa,
    add_communication, get_all_communications, init_db)
from utils.email_utils import (send_email, template_confirmation,
                                template_reminder, template_post_event)
from utils.styles import inject_css, page_header

st.set_page_config(page_title="Communications · CC Platform", page_icon="📧", layout="wide")
inject_css()
try:
    from utils.database import init_all
    init_all()
except ImportError:
    init_db()

role = st.session_state.get("user_role", None)
linked_id = st.session_state.get("linked_id", None)

if role is None:
    st.warning("Please log in.")
    st.stop()

if role != "coordinator":
    st.error("Communications is only accessible to the Coordinator.")
    st.stop()

_role = role
_is_coord = True
_user_label = st.session_state.get("user_label", "Coordinator")

page_header("📧 Communications", "Send and track emails to hosts, facilitators, colleagues, or any address")

hosts  = get_all_hosts()
facs   = get_all_facilitators()
nhh    = get_all_nhh()
cdfa   = get_all_cdfa()
events = get_all_events()

tab_send, tab_log = st.tabs(["✉️ Send Communication", "📋 Communications Log"])

with tab_send:
    st.markdown("### Compose & Send")
    col_left, col_right = st.columns([2, 1])

    with col_left:
        comm_type = st.selectbox("Communication Type",
                                  ["Confirmation", "Reminder", "Post-Event", "General"])

        # ── Build recipient dropdown including all contacts + Other ─────────────
        recip_options = {}
        for h in hosts:
            recip_options[f"host_{h['host_id']}"] = f"👥 [Host] {h['name']} <{h.get('email','')}>"
        for f in facs:
            recip_options[f"fac_{f['facilitator_id']}"] = f"🎤 [Facilitator] {f['name']} <{f.get('email','')}>"
        for n in nhh:
            recip_options[f"nhh_{n['nhh_id']}"] = f"🏛️ [NHH] {n['name']} <{n.get('email','')}>"
        for c in cdfa:
            recip_options[f"cdfa_{c['cdfa_id']}"] = f"🌾 [CDFA] {c['name']} <{c.get('email','')}>"
        recip_options["other"] = "✏️ Other — type a new email address"

        recip_sel = st.multiselect(
            "Select Recipient(s)",
            options=list(recip_options.keys()),
            format_func=lambda x: recip_options[x],
            help="Select one or more contacts, or choose 'Other' to enter a custom email"
        )

        # Show custom email fields if "Other" is selected
        custom_email = ""
        custom_name  = ""
        if "other" in recip_sel:
            st.markdown("**Other Recipient:**")
            col_a, col_b = st.columns(2)
            with col_a:
                custom_email = st.text_input("Email Address *", placeholder="anyone@example.com")
            with col_b:
                custom_name  = st.text_input("Recipient Name", placeholder="e.g., John Smith")

        # Related event
        event_opts = {e["event_id"]: f"{e['event_name']} ({e['event_date']})" for e in events}
        rel_event  = st.selectbox("Related Event (optional)", options=[""] + list(event_opts.keys()),
                                   format_func=lambda x: "— None —" if x=="" else event_opts[x])

        # Auto-fill template
        subject_default = ""
        body_default    = ""

        if rel_event and recip_sel:
            ev = next((e for e in events if e["event_id"] == rel_event), None)
            if ev:
                key = [k for k in recip_sel if k != "other"]
                r_name = ""
                r_role = "facilitator"
                if key:
                    k = key[0]
                    if k.startswith("host_"):
                        r = next((h for h in hosts if h["host_id"]==int(k.replace("host_",""))), {})
                        r_name = r.get("contact_person") or r.get("name","")
                        r_role = "host"
                    elif k.startswith("fac_"):
                        r = next((f for f in facs if f["facilitator_id"]==int(k.replace("fac_",""))), {})
                        r_name = r.get("name","")
                    elif k.startswith("nhh_"):
                        r = next((n for n in nhh if n["nhh_id"]==int(k.replace("nhh_",""))), {})
                        r_name = r.get("name","")
                    elif k.startswith("cdfa_"):
                        r = next((c for c in cdfa if c["cdfa_id"]==int(k.replace("cdfa_",""))), {})
                        r_name = r.get("name","")
                elif custom_name:
                    r_name = custom_name

                if comm_type == "Confirmation":
                    tmpl = template_confirmation(r_name, ev.get("event_name",""),
                                                  ev.get("event_date",""), ev.get("event_time",""),
                                                  ev.get("venue_name","") or ev.get("venue_address",""),
                                                  ev.get("city",""))
                elif comm_type == "Reminder":
                    tmpl = template_reminder(r_name, ev.get("event_name",""),
                                              ev.get("event_date",""), ev.get("event_time",""),
                                              ev.get("venue_name","") or ev.get("venue_address",""),
                                              ev.get("city",""))
                elif comm_type == "Post-Event":
                    tmpl = template_post_event(r_name, ev.get("event_name",""),
                                                ev.get("event_date",""), r_role)
                else:
                    tmpl = {"subject": "", "body": ""}
                subject_default = tmpl["subject"]
                body_default    = tmpl["body"]

        subject = st.text_input("Subject *", value=subject_default)
        body    = st.text_area("Email Body *", value=body_default, height=240)

    with col_right:
        st.markdown("### 📋 Preview")
        preview_tos = []
        for key in recip_sel:
            if key == "other":
                if custom_email:
                    preview_tos.append(f"{custom_name} <{custom_email}>" if custom_name else custom_email)
            else:
                preview_tos.append(recip_options.get(key, key))
        to_display = ", ".join(preview_tos) if preview_tos else "— No recipient selected —"

        st.markdown(f"""
        <div style='background:white;border:1px solid #D5D8DC;border-radius:8px;
        padding:1rem;font-size:0.85rem;min-height:200px'>
            <div style='border-bottom:1px solid #eee;padding-bottom:0.5rem;margin-bottom:0.5rem'>
                <strong>To:</strong> {to_display}<br>
                <strong>Subject:</strong> {subject or '(none)'}
            </div>
            <div style='white-space:pre-wrap;font-size:0.83rem'>{body or '(empty)'}</div>
        </div>
        """, unsafe_allow_html=True)

    st.markdown("---")
    col_s1, col_s2 = st.columns(2)
    with col_s1:
        send_btn = st.button("📤 Send Email", use_container_width=True, type="primary")
    with col_s2:
        log_btn  = st.button("📝 Log Without Sending", use_container_width=True)

    if send_btn or log_btn:
        if not recip_sel:
            st.error("Please select at least one recipient.")
        elif "other" in recip_sel and not custom_email:
            st.error("Please enter an email address for 'Other' recipient.")
        elif not subject or not body:
            st.error("Subject and body are required.")
        else:
            # Build targets list
            targets = []
            for key in recip_sel:
                if key == "other":
                    targets.append((custom_email, custom_name or custom_email, "General", None))
                elif key.startswith("host_"):
                    r = next((h for h in hosts if h["host_id"]==int(key.replace("host_",""))), {})
                    targets.append((r.get("email",""), r.get("name",""), "Host", r.get("host_id")))
                elif key.startswith("fac_"):
                    r = next((f for f in facs if f["facilitator_id"]==int(key.replace("fac_",""))), {})
                    targets.append((r.get("email",""), r.get("name",""), "Facilitator", r.get("facilitator_id")))
                elif key.startswith("nhh_"):
                    r = next((n for n in nhh if n["nhh_id"]==int(key.replace("nhh_",""))), {})
                    targets.append((r.get("email",""), r.get("name",""), "NHH", r.get("nhh_id")))
                elif key.startswith("cdfa_"):
                    r = next((c for c in cdfa if c["cdfa_id"]==int(key.replace("cdfa_",""))), {})
                    targets.append((r.get("email",""), r.get("name",""), "CDFA", r.get("cdfa_id")))

            success_count = 0
            errors = []

            for to_email, to_name, r_type, r_id in targets:
                if send_btn:
                    if to_email:
                        ok, msg = send_email(to_email, subject, body)
                        if ok:
                            success_count += 1
                        else:
                            errors.append(f"{to_name}: {msg}")
                    else:
                        errors.append(f"{to_name}: No email address on file.")
                else:
                    success_count += 1

                add_communication({
                    "recipient_type":     r_type,
                    "recipient_id":       r_id,
                    "event_id":           rel_event or None,
                    "communication_type": comm_type,
                    "subject":            subject,
                    "body":               body,
                })

            if success_count:
                action = "sent" if send_btn else "logged"
                log_activity("Communication " + ("Sent" if send_btn else "Logged"),
                             f"{comm_type} — {subject[:50]} — {success_count} recipient(s)")
                add_notification(f"Communication {action}: {subject[:50]}", "all")
                st.success(f"✅ {success_count} message(s) {action} successfully!")
                for err in errors:
                    st.warning(f"⚠️ {err}")
                time.sleep(3)
                st.rerun()
            for err in errors:
                st.warning(f"⚠️ {err}")

with tab_log:
    st.markdown("### Communications Log")
    comms = get_all_communications()

    c1, c2 = st.columns(2)
    with c1:
        type_f  = st.selectbox("Filter by type",
                                ["All","Confirmation","Reminder","Post-Event","General"])
    with c2:
        recip_f = st.selectbox("Filter by recipient",
                                ["All","Host","Facilitator","NHH","CDFA","General"])

    filtered = comms
    if type_f  != "All": filtered = [c for c in filtered if c.get("communication_type")==type_f]
    if recip_f != "All": filtered = [c for c in filtered if c.get("recipient_type")==recip_f]

    if not filtered:
        st.info("No communications logged yet.")
    else:
        st.caption(f"Showing {len(filtered)} communication(s)")
        for c in filtered:
            date_str = str(c.get("sent_date",""))[:16] if c.get("sent_date") else ""
            icon = {"Confirmation":"✅","Reminder":"🔔","Post-Event":"🙏","General":"💬"}.get(
                c.get("communication_type",""),"📧")
            with st.expander(
                f"{icon} {date_str} · {c.get('communication_type','')} → "
                f"{c.get('recipient_type','')} · {c.get('subject','')[:50]}"
            ):
                st.markdown(f"**Related Event:** {c.get('event_name','') or '—'}")
                st.markdown(f"**Subject:** {c.get('subject','')}")
                st.markdown("**Body:**")
                st.code(c.get("body",""), language=None)
