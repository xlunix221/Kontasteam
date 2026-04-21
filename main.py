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

if "logged_in_as" not in st.session_state:
    st.session_state.logged_in_as = None

# LOGOWANIE
if st.session_state.logged_in_as is None:
    c1, c2, c3 = st.columns([1,2,1])
    with c2:
        st.title("🛡️ System Zarządzania")
        pass_input = st.text_input("Wprowadź hasło", type="password")
        if pass_input:
            if pass_input == st.secrets["admin_password"]:
                st.session_state.logged_in_as = "admin"; st.rerun()
            elif pass_input == st.secrets["user_password"]:
                st.session_state.logged_in_as = "user"; st.rerun()
            else: st.error("Błędne hasło!")
    st.stop()

# Pobieranie danych z bazy
sheet = connect_gsheet()
raw_rows = sheet.get_all_values()
headers = raw_rows[0]
df_data = raw_rows[1:]

# --- DEFINICJE OKIEN DIALOGOWYCH ---

@st.dialog("Nowe konto")
def add_acc_wizard_dialog():
    st.info(f"Email: {EMAIL_USER}")
    if st.button("Pobierz link weryfikacyjny 🔗"):
        link = get_steam_data("link")
        if link: st.link_button("ZWERYFIKUJ KONTO", link)
        else: st.error("Brak linku w ostatnich mailach.")
    st.divider()
    nl = st.text_input("Login")
    nh = st.text_input("Hasło")
    nk = st.text_input("Kod znajomego")
    if st.button("Zapisz ✅"):
        if nl and nh:
            col_a = sheet.col_values(1)
            target_row = len(col_a) + 1
            for i, val in enumerate(col_a):
                if i == 0: continue
                if not val or val.strip() == "": target_row = i + 1; break
            sheet.update(range_name=f"A{target_row}:B{target_row}", values=[[nl, nh]])
            sheet.update(range_name=f"G{target_row}:H{target_row}", values=[["nie odblokowany", nk]])
            st.success("Dodano konto!"); time.sleep(1)
            st.session_state.show_add_wizard = False
            st.rerun()
        else: st.error("Wymagany login i hasło!")

@st.dialog("Zarządzanie kontem")
def manage_account_dialog(acc):
    r_idx = 0
    for i, row in enumerate(raw_rows):
        if row and row[0] == acc['Nazwa konta']: r_idx = i + 1; break

    # FLOW WIZARDA LOGOWANIA
    if "wizard_step" in st.session_state and st.session_state.wizard_step > 0:
        step = st.session_state.wizard_step
        if step == 1:
            st.subheader("Krok 1: Login"); st.code(acc['Nazwa konta'])
            if st.button("Dalej ➡️", use_container_width=True): st.session_state.wizard_step = 2; st.rerun()
        elif step == 2:
            st.subheader("Krok 2: Hasło"); st.code(acc['Hasło'])
            if st.button("Dalej ➡️", use_container_width=True): st.session_state.wizard_step = 3; st.rerun()
        elif step == 3:
            st.subheader("Krok 3: Steam Guard")
            if st.button("Pobierz kod 📩", use_container_width=True):
                with st.spinner("Szukam..."): st.session_state.temp_code = get_steam_data("code")
            if "temp_code" in st.session_state: st.code(st.session_state.temp_code if st.session_state.temp_code else "Kod nie dotarł.")
            if st.button("Gotowe ✅", use_container_width=True):
                st.session_state.wizard_step = 0; del st.session_state.temp_code; st.rerun()
        return

    # GŁÓWNE ZAKŁADKI (Zmienione: Brak zakładki logowania)
    tabs_list = ["📊 Status"]
    if st.session_state.logged_in_as == "admin": tabs_list.append("⚙️ Admin")
    tabs = st.tabs(tabs_list)
    
    with tabs[0]:
        st.write(f"Kod znajomego: `{acc.get('Kod znajomego', 'Brak')}`")
        now_pl = (datetime.now() + timedelta(hours=2)).strftime("%Y-%m-%d %H:%M:%S")
        c1, c2, c3 = st.columns(3)
        if c1.button("20h"): sheet.update_cell(r_idx, 3, "20h"); sheet.update_cell(r_idx, 4, now_pl); st.rerun()
        if c2.button("7 dni"): sheet.update_cell(r_idx, 3, "7 dni"); sheet.update_cell(r_idx, 4, now_pl); st.rerun()
        if c3.button("Perm"): sheet.update_cell(r_idx, 3, "Perm"); sheet.update_cell(r_idx, 4, now_pl); st.rerun()
        if st.button("Wyczyść bana 🟢", use_container_width=True):
            sheet.update_cell(r_idx, 3, ""); sheet.update_cell(r_idx, 4, ""); st.rerun()
        
        st.divider()
        curr_st = acc.get('odblokowanie status', 'nie odblokowany')
        new_st = st.selectbox("Status turniejowy", ["nie odblokowany", "odblokowany"], 
                              index=0 if curr_st == "nie odblokowany" else 1, key="sel_stat")
        if new_st != curr_st:
            with st.spinner("Zapisywanie..."): sheet.update_cell(r_idx, 7, new_st); st.rerun()

    if st.session_state.logged_in_as == "admin" and len(tabs) > 1:
        with tabs[1]:
            st.subheader("Edycja konta")
            new_l = st.text_input("Login", acc['Nazwa konta'])
            new_p = st.text_input("Hasło", acc['Hasło'])
            new_k = st.text_input("Kod Znajomego", acc.get('Kod znajomego', ''))
            
            cc1, cc2 = st.columns(2)
            if cc1.button("Zapisz zmiany 💾"):
                sheet.update(range_name=f"A{r_idx}:B{r_idx}", values=[[new_l, new_p]])
                sheet.update_cell(r_idx, 8, new_k); st.success("Zapisano!"); time.sleep(1); st.rerun()
            if cc2.button("USUŃ KONTO 🗑️", type="primary"):
                sheet.update(range_name=f"A{r_idx}:B{r_idx}", values=[["", ""]]); sheet.update_cell(r_idx, 8, "")
                st.session_state.selected_acc = None; st.rerun()

    st.divider()
    if st.button("🚀 ZALOGUJ SIĘ", use_container_width=True):
        st.session_state.wizard_step = 1; st.rerun()

# --- PANEL GŁÓWNY ---

if st.session_state.logged_in_as == "admin":
    with st.expander("🛠️ NARZĘDZIA ADMINISTRATORA"):
        adm_c1, adm_c2 = st.columns([1, 2])
        with adm_c1:
            st.subheader("Dodaj konto")
            if st.button("➕ Uruchom Kreator"):
                st.session_state.show_add_wizard = True
                st.session_state.selected_acc = None # Blokada kolizji
                st.rerun()
        with adm_c2:
            st.subheader("Podgląd bazy")
            df = pd.DataFrame(df_data, columns=headers)
            st.dataframe(df, use_container_width=True, hide_index=True)

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
            tl = acc.get('Pozostały czas / Status', 'Czyste')
            if tl == "Czyste" or not tl: st.success("🟢 Gotowe")
            else: st.error(f"⏳ {tl}")
            if st.button("Zarządzaj", key=f"panel_{idx}", use_container_width=True):
                st.session_state.selected_acc = acc
                st.session_state.show_add_wizard = False # Blokada kolizji
                st.session_state.wizard_step = 0
                st.rerun()

# --- LOGIKA WYWOŁYWANIA DIALOGÓW (Zabezpieczenie przed kolizją) ---

if st.session_state.get("show_add_wizard"):
    add_acc_wizard_dialog()
elif st.session_state.get("selected_acc"):
    manage_account_dialog(st.session_state.selected_acc)
