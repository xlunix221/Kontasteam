import streamlit as st
import gspread
from oauth2client.service_account import ServiceAccountCredentials
import imaplib
import email
import re
import time
import pandas as pd
from datetime import datetime, timedelta

# --- KONFIGURACJA ---
SHEET_NAME = "naszekonta"
SCOPE = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]

EMAIL_USER = "jestesmygejami211569809@op.pl"
EMAIL_PASS = "QHHZ-4BGJ-UEDR-UZOV"
IMAP_SERVER = "imap.poczta.onet.pl"

# --- LOGIKA BACKENDU ---

def connect_gsheet():
    creds_info = dict(st.secrets["gcp_service_account"])
    if "private_key" in creds_info:
        key = creds_info["private_key"].replace("\\n", "\n")
        clean_lines = [line.strip() for line in key.split("\n") if line.strip()]
        creds_info["private_key"] = "\n".join(clean_lines).strip()
    creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_info, SCOPE)
    client = gspread.authorize(creds)
    return client.open(SHEET_NAME).sheet1

def get_steam_data(search_type="code"):
    try:
        mail = imaplib.IMAP4_SSL(IMAP_SERVER, port=993, timeout=20) 
        mail.login(EMAIL_USER, EMAIL_PASS)
        mail.select("Powiadomienia")
        result, data = mail.search(None, 'ALL') 
        ids = data[0].split()
        if not ids: return None
        latest_id = ids[-1]
        result, data = mail.fetch(latest_id, "(RFC822)")
        raw_email = data[0][1]
        msg = email.message_from_bytes(raw_email)
        content = ""
        if msg.is_multipart():
            for part in msg.walk():
                if part.get_content_type() in ["text/plain", "text/html"]:
                    content += part.get_payload(decode=True).decode(errors='ignore')
        else: content = msg.get_payload(decode=True).decode(errors='ignore')

        if search_type == "link":
            links = re.findall(r'https://store\.steampowered\.com/account/newaccountverification\?[\w=&?]+', content)
            return links[0] if links else None
        else:
            code = re.search(r'\b[A-Z0-9]{5}\b', content)
            if not code: code = re.search(r'\b\d{6}\b', content)
            return code.group(0) if code else None
    except: return None

# --- INTERFEJS ---
st.set_page_config(page_title="CS Manager PRO", layout="wide")

if "logged_in_as" not in st.session_state: st.session_state.logged_in_as = None
if "wizard_step" not in st.session_state: st.session_state.wizard_step = 0
if "selected_acc" not in st.session_state: st.session_state.selected_acc = None

# LOGOWANIE
if st.session_state.logged_in_as is None:
    c1, c2, c3 = st.columns([1,2,1])
    with c2:
        st.title("🛡️ System Zarządzania")
        pass_input = st.text_input("Hasło dostępu", type="password")
        if pass_input:
            if pass_input == st.secrets["admin_password"]:
                st.session_state.logged_in_as = "admin"; st.rerun()
            elif pass_input == st.secrets["user_password"]:
                st.session_state.logged_in_as = "user"; st.rerun()
            else: st.error("Błędne hasło!")
    st.stop()

sheet = connect_gsheet()
raw_rows = sheet.get_all_values()
headers = raw_rows[0]
df_data = raw_rows[1:]

# --- DIALOGI ---

@st.dialog("Nowe konto")
def add_acc_dialog():
    st.info(f"Email: {EMAIL_USER}")
    if st.button("Pobierz link weryfikacyjny 🔗"):
        link = get_steam_data("link")
        if link: st.link_button("ZWERYFIKUJ", link)
        else: st.error("Brak linku.")
    st.divider()
    nl, nh, nk = st.text_input("Login"), st.text_input("Hasło"), st.text_input("Kod znajomego")
    if st.button("Zapisz ✅"):
        if nl and nh:
            col_a = sheet.col_values(1)
            target_row = len(col_a) + 1
            for i, val in enumerate(col_a):
                if i > 0 and (not val or val.strip() == ""):
                    target_row = i + 1; break
            sheet.update(range_name=f"A{target_row}:B{target_row}", values=[[nl, nh]])
            sheet.update(range_name=f"G{target_row}:H{target_row}", values=[["nie odblokowany", nk]])
            st.success("Dodano!"); time.sleep(1)
            st.session_state.show_add_wizard = False; st.rerun()

@st.dialog("Zarządzanie kontem")
def manage_dialog(acc):
    # Wyświetlamy aktualnie obsługiwane konto
    st.subheader(f"Zarządzasz kontem: {acc['Nazwa konta']}")
    st.divider()

    r_idx = 0
    for i, row in enumerate(raw_rows):
        if row and row[0] == acc['Nazwa konta']: r_idx = i + 1; break

    # WIZARD LOGOWANIA
    if st.session_state.wizard_step > 0:
        step = st.session_state.wizard_step
        if step == 1:
            st.write("Krok 1: Login"); st.code(acc['Nazwa konta'])
            if st.button("Dalej ➡️", use_container_width=True): st.session_state.wizard_step = 2; st.rerun()
        elif step == 2:
            st.write("Krok 2: Hasło"); st.code(acc['Hasło'])
            if st.button("Dalej ➡️", use_container_width=True): st.session_state.wizard_step = 3; st.rerun()
        elif step == 3:
            st.write("Krok 3: Steam Guard")
            if st.button("Pobierz kod 📩", use_container_width=True):
                with st.spinner("Szukam..."): st.session_state.temp_code = get_steam_data("code")
            if "temp_code" in st.session_state: st.code(st.session_state.temp_code if st.session_state.temp_code else "Brak kodu.")
            
            # POPRAWKA: Kliknięcie Gotowe nie zamyka dialogu, tylko wraca do opcji konta
            if st.button("Gotowe ✅", use_container_width=True):
                st.session_state.wizard_step = 0
                st.session_state.pop("temp_code", None); st.rerun()
        return

    # ZAKŁADKI (STATUS / ADMIN)
    t_names = ["📊 Status"]
    if st.session_state.logged_in_as == "admin": t_names.append("⚙️ Admin")
    tabs = st.tabs(t_names)
    
    with tabs[0]:
        st.write(f"Kod znajomego: `{acc.get('Kod znajomego', 'Brak')}`")
        now_pl = (datetime.now() + timedelta(hours=2)).strftime("%Y-%m-%d %H:%M:%S")
        st.write("Ustaw bana:")
        c1, c2, c3 = st.columns(3)
        if c1.button("20h"): sheet.update_cell(r_idx, 3, "20h"); sheet.update_cell(r_idx, 4, now_pl); st.rerun()
        if c2.button("7 dni"): sheet.update_cell(r_idx, 3, "7 dni"); sheet.update_cell(r_idx, 4, now_pl); st.rerun()
        if c3.button("Perm"): sheet.update_cell(r_idx, 3, "Perm"); sheet.update_cell(r_idx, 4, now_pl); st.rerun()
        
        st.divider()
        curr_st = acc.get('odblokowanie status', 'nie odblokowany')
        new_st = st.selectbox("Status turniejowy", ["nie odblokowany", "odblokowany"], 
                              index=0 if curr_st == "nie odblokowany" else 1, key=f"sel_{acc['Nazwa konta']}")
        if new_st != curr_st:
            sheet.update_cell(r_idx, 7, new_st); st.rerun()

    if st.session_state.logged_in_as == "admin" and len(tabs) > 1:
        with tabs[1]:
            st.subheader("Opcje Administratora")
            if st.button("WYCZYŚĆ BANA 🟢", use_container_width=True):
                sheet.update_cell(r_idx, 3, ""); sheet.update_cell(r_idx, 4, ""); st.rerun()
            
            st.divider()
            nl = st.text_input("Zmień Login", acc['Nazwa konta'])
            np = st.text_input("Zmień Hasło", acc['Hasło'])
            nk = st.text_input("Zmień Kod Znajomego", acc.get('Kod znajomego', ''))
            
            cc1, cc2 = st.columns(2)
            if cc1.button("Zapisz zmiany 💾"):
                sheet.update(range_name=f"A{r_idx}:B{r_idx}", values=[[nl, np]])
                sheet.update_cell(r_idx, 8, nk); st.success("OK!"); time.sleep(0.5); st.rerun()
            if cc2.button("USUŃ KONTO 🗑️", type="primary"):
                sheet.update(range_name=f"A{r_idx}:B{r_idx}", values=[["", ""]]); sheet.update_cell(r_idx, 8, "")
                st.session_state.selected_acc = None; st.rerun()

    st.divider()
    if st.button("🚀 ZALOGUJ SIĘ", use_container_width=True):
        st.session_state.wizard_step = 1; st.rerun()

# --- PANEL GŁÓWNY ---

if st.session_state.logged_in_as == "admin":
    with st.expander("🛠️ NARZĘDZIA ADMINISTRATORA"):
        ac1, ac2 = st.columns([1, 2])
        with ac1:
            if st.button("➕ Dodaj nowe konto"):
                st.session_state.show_add_wizard = True; st.rerun()
        with ac2:
            st.dataframe(pd.DataFrame(df_data, columns=headers), use_container_width=True, hide_index=True)

st.divider()
st.title("🛡️ Twoje Konta")
search = st.text_input("Szukaj...", "").lower()
accounts = [dict(zip(headers, row)) for row in df_data if row and row[0] != ""]
filtered = [a for a in accounts if search in a.get('Nazwa konta', '').lower()]

cols = st.columns(4)
for idx, acc in enumerate(filtered):
    with cols[idx % 4]:
        with st.container(border=True):
            st.markdown(f"### {acc['Nazwa konta']}")
            
            # STATUS BANA
            tl = acc.get('Pozostały czas / Status', 'Czyste')
            if tl == "Czyste" or not tl: 
                st.success("🟢 Brak bana")
            else: 
                st.error(f"⏳ {tl}")
            
            # STATUS TURNIEJOWY
            t_status = acc.get('odblokowanie status', 'nie odblokowany')
            st.write(f"Turek: **{t_status}**")
            
            # KOD ZNAJOMEGO
            f_code = acc.get('Kod znajomego', '').strip()
            if not f_code or f_code.lower() == "brak" or f_code == "":
                st.warning("⚠️ Brak kodu znajomego")

            if st.button("Zarządzaj", key=f"btn_{idx}", use_container_width=True):
                st.session_state.selected_acc = acc
                st.session_state.wizard_step = 0; st.rerun()

if st.session_state.get("show_add_wizard"): add_acc_dialog()
elif st.session_state.get("selected_acc"): manage_dialog(st.session_state.selected_acc)
