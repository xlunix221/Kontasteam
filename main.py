import streamlit as st
import gspread
from oauth2client.service_account import ServiceAccountCredentials
import imaplib
import email
import re
import time
import json
import os
from datetime import datetime

# --- KONFIGURACJA ---
SHEET_NAME = "naszekonta"
SCOPE = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]

EMAIL_USER = "jestesmygejami211569809@op.pl"
EMAIL_PASS = "QHHZ-4BGJ-UEDR-UZOV"
IMAP_SERVER = "imap.poczta.onet.pl"

# --- LOGIKA BACKENDU ---

def connect_gsheet():
    # 1. Pobieramy dane z Secrets
    creds_info = dict(st.secrets["gcp_service_account"])
    
    if "private_key" in creds_info:
        # 2. Usuwamy tekstowe \n jeśli są
        key = creds_info["private_key"].replace("\\n", "\n")
        
        # 3. FIX na "Incorrect padding": Usuwamy spacje z każdej linijki klucza
        # Często przy kopiowaniu na końcu linii wpada spacja, co psuje szyfrowanie
        clean_lines = [line.strip() for line in key.split("\n") if line.strip()]
        creds_info["private_key"] = "\n".join(clean_lines).strip()
        
    creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_info, SCOPE)
    client = gspread.authorize(creds)
    return client.open(SHEET_NAME).sheet1
    
def get_steam_code():
    try:
        # Poprawione połączenie (tylko raz, z timeoutem)
        mail = imaplib.IMAP4_SSL(IMAP_SERVER, port=993, timeout=20) 
        mail.login(EMAIL_USER, EMAIL_PASS)
        mail.select("Powiadomienia")
        
        result, data = mail.search(None, 'ALL') 
        ids = data[0].split()
        if not ids: return "Brak maili"
        
        latest_id = ids[-1]
        result, data = mail.fetch(latest_id, "(RFC822)")
        raw_email = data[0][1]
        msg = email.message_from_bytes(raw_email)
        
        content = ""
        if msg.is_multipart():
            for part in msg.walk():
                if part.get_content_type() == "text/plain":
                    content = part.get_payload(decode=True).decode()
        else:
            content = msg.get_payload(decode=True).decode()
            
        code_match = re.search(r'\b[A-Z0-9]{5}\b', content)
        if not code_match:
            code_match = re.search(r'\b\d{6}\b', content)
            
        return code_match.group(0) if code_match else "Kod nie dotarł..."
    except Exception as e:
        return f"Błąd poczty: {e}"

# --- INTERFEJS ---

st.set_page_config(page_title="CS Manager", layout="wide")
# Dodaj to na samym początku interfejsu (pod st.set_page_config)
password = st.text_input("Podaj hasło do panelu", type="password")
if password != "Mam3latka":
    st.warning("Błędne hasło!")
    st.stop()

try:
    sheet = connect_gsheet()
    raw_data = sheet.get_all_values()
    headers = raw_data[0]
    data = [dict(zip(headers, row)) for row in raw_data[1:] if row[0] != ""]
except Exception as e:
    st.error(f"Błąd połączenia z Google Sheets: {e}")
    st.stop()

if 'selected_acc' not in st.session_state:
    st.session_state.selected_acc = None
if 'wizard_step' not in st.session_state:
    st.session_state.wizard_step = 0

st.title("🛡️ Panel Zarządzania Kontami")
search = st.text_input("Szukaj konta...", "").lower()

filtered_data = [d for d in data if search in d['Nazwa konta'].lower()]

cols = st.columns(4)
for idx, acc in enumerate(filtered_data):
    with cols[idx % 4]:
        with st.container(border=True):
            st.markdown(f"### {acc['Nazwa konta']}")
            ban_status = acc.get('Typ bana (Lista)', '')
            if not ban_status or ban_status == "":
                st.success("🟢 Czyste")
            else:
                st.error(f"🔴 Ban: {ban_status}")
            
            t_status = acc.get('odblokowanie status', '')
            st.write(f"Status: **{t_status}**")

            if st.button("Otwórz Panel", key=f"acc_{idx}"):
                st.session_state.selected_acc = acc
                st.session_state.wizard_step = 1
                st.rerun()

if st.session_state.selected_acc:
    acc = st.session_state.selected_acc
    
    @st.dialog(f"Zarządzanie: {acc['Nazwa konta']}")
    def manage():
        t1, t2 = st.tabs(["📊 Status", "🔑 Logowanie"])
        
        with t1:
            row_idx = 0
            for i, r in enumerate(raw_data):
                if r[0] == acc['Nazwa konta']:
                    row_idx = i + 1
                    break
            
            st.write(f"**Kod znajomego:** `{acc.get('Kod znajomego', 'Brak')}`")
            st.divider()
            
            now_timestamp = datetime.now().strftime("%Y-%m-%d %H:%M")

            st.write("Ustaw bana:")
            c1, c2, c3 = st.columns(3)
            
            if c1.button("20h", use_container_width=True):
                sheet.update_cell(row_idx, 3, "20h")
                sheet.update_cell(row_idx, 4, now_timestamp)
                st.rerun()
            if c2.button("7 dni", use_container_width=True):
                sheet.update_cell(row_idx, 3, "7 dni")
                sheet.update_cell(row_idx, 4, now_timestamp)
                st.rerun()
            if c3.button("Perm", use_container_width=True):
                sheet.update_cell(row_idx, 3, "Perm")
                sheet.update_cell(row_idx, 4, now_timestamp)
                st.rerun()
            
            st.divider()
            st.write("Status turniejowy:")
            current_status = acc.get('odblokowanie status', 'nie odblokowany')
            
            # Dodano klucz (key), żeby Streamlit nie głupiał przy zmianie
            new_status = st.selectbox("Wybierz nowy status", ["nie odblokowany", "odblokowany"], 
                                      index=0 if current_status == "nie odblokowany" else 1,
                                      key="status_selector")
            
            # Przycisk zatwierdzający - eliminuje pętlę ładowania
            if st.button("Zapisz status turniejowy", use_container_width=True):
                with st.spinner("Zapisywanie..."):
                    sheet.update_cell(row_idx, 7, new_status)
                    st.success("Zmieniono status!")
                    time.sleep(1) # Chwila oddechu dla Google Sheets
                    st.rerun()

        with t2:
            step = st.session_state.wizard_step
            if step == 1:
                st.write("Krok 1: Login")
                st.code(acc['Nazwa konta'])
                if st.button("Dalej ➡️", key="next1"):
                    st.session_state.wizard_step = 2
                    st.rerun()
            elif step == 2:
                st.write("Krok 2: Hasło")
                st.code(acc['Hasło'])
                if st.button("Dalej ➡️", key="next2"):
                    st.session_state.wizard_step = 3
                    st.rerun()
            elif step == 3:
                st.write("Krok 3: Kod z Onetu")
                if st.button("Pobierz kod teraz 📩"):
                    with st.spinner("Łączenie z Onetem..."):
                        code = get_steam_code()
                        st.session_state.current_code = code
                
                if 'current_code' in st.session_state:
                    st.code(st.session_state.current_code)
                    if st.button("Gotowe ✅"):
                        st.session_state.selected_acc = None
                        st.session_state.wizard_step = 0
                        if 'current_code' in st.session_state:
                            del st.session_state.current_code
                        st.rerun()

    manage()
