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

@st.cache_resource
def get_gspread_client():
    creds_info = dict(st.secrets["gcp_service_account"])
    if "private_key" in creds_info:
        key = creds_info["private_key"].replace("\\n", "\n")
        clean_lines = [line.strip() for line in key.split("\n") if line.strip()]
        creds_info["private_key"] = "\n".join(clean_lines).strip()
    creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_info, SCOPE)
    return gspread.authorize(creds)

@st.cache_data(ttl=10)
def fetch_sheet_data():
    client = get_gspread_client()
    sheet = client.open(SHEET_NAME).sheet1
    return sheet.get_all_values()

def get_steam_data(search_type="code"):
    try:
        mail = imaplib.IMAP4_SSL(IMAP_SERVER, port=993, timeout=20) 
        mail.login(EMAIL_USER, EMAIL_PASS)
        mail.select("Powiadomienia")
        result, data = mail.search(None, 'ALL') 
        ids = data[0].split()
        if not ids: return None, None
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
        res_val = None
        if search_type == "link":
            links = re.findall(r'https://store\.steampowered\.com/account/newaccountverification\?[\w=&?]+', content)
            res_val = links[0] if links else None
        else:
            code = re.search(r'\b[A-Z0-9]{5}\b', content)
            if not code: code = re.search(r'\b\d{6}\b', content)
            res_val = code.group(0) if code else None
        mail.logout()
        return res_val, latest_id
    except: return None, None

def delete_steam_email(msg_id):
    if not msg_id: return
    try:
        mail = imaplib.IMAP4_SSL(IMAP_SERVER, port=993, timeout=20)
        mail.login(EMAIL_USER, EMAIL_PASS)
        mail.select("Powiadomienia")
        mail.store(msg_id, '+FLAGS', '\\Deleted')
        mail.expunge()
        mail.logout()
    except: pass

# --- INTERFEJS ---
st.set_page_config(page_title="CS Manager PRO", layout="wide")

# Inicjalizacja stanów
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
            if pass_input == st.secrets["admin_password"]: st.session_state.logged_in_as = "admin"; st.rerun()
            elif pass_input == st.secrets["user_password"]: st.session_state.logged_in_as = "user"; st.rerun()
            else: st.error("Błędne hasło!")
    st.stop()

# Dane
raw_rows = fetch_sheet_data()
headers = raw_rows[0]
df_data = raw_rows[1:]
client = get_gspread_client()
sheet = client.open(SHEET_NAME).sheet1

# --- DIALOGI ---

@st.dialog("Nowe konto")
def add_acc_dialog():
    st.info(f"Email: {EMAIL_USER}")
    if st.button("Pobierz link 🔗"):
        link, mid = get_steam_data("link")
        if link: st.link_button("ZWERYFIKUJ", link); st.session_state.last_mid = mid
        else: st.error("Brak linku.")
    st.divider()
    nl, nh, nk = st.text_input("Login"), st.text_input("Hasło"), st.text_input("Kod znajomego")
    if st.button("Zapisz ✅"):
        if nl and nh:
            if "last_mid" in st.session_state: delete_steam_email(st.session_state.last_mid)
            col_a = sheet.col_values(1)
            target_row = len(col_a) + 1
            for i, val in enumerate(col_a):
                if i > 0 and (not val or val.strip() == ""): target_row = i + 1; break
            sheet.update(range_name=f"A{target_row}:B{target_row}", values=[[nl, nh]])
            sheet.update(range_name=f"G{target_row}:H{target_row}", values=[["nie odblokowany", nk]])
            st.cache_data.clear()
            st.session_state.show_add_wizard = False
            st.rerun()

@st.dialog("Zarządzanie kontem")
def manage_dialog(acc):
    st.subheader(f"Zarządzasz: {acc['Nazwa konta']}")
    
    r_idx = 0
    for i, row in enumerate(raw_rows):
        if row and row[0] == acc['Nazwa konta']: r_idx = i + 1; break

    # WIZARD LOGOWANIA
    if st.session_state.wizard_step > 0:
        step = st.session_state.wizard_step
        if step == 1:
            st.write("Krok 1: Login"); st.code(acc['Nazwa konta'])
            if st.button("Dalej ➡️", width='stretch'): st.session_state.wizard_step = 2; st.rerun()
        elif step == 2:
            st.write("Krok 2: Hasło"); st.code(acc['Hasło'])
            if st.button("Dalej ➡️", width='stretch'): st.session_state.wizard_step = 3; st.rerun()
        elif step == 3:
            if st.button("Pobierz kod 📩", width='stretch'):
                with st.spinner("Szukam..."): 
                    code, mid = get_steam_data("code")
                    st.session_state.temp_code = code
                    st.session_state.last_mid = mid
            if "temp_code" in st.session_state: st.code(st.session_state.temp_code)
            if st.button("Gotowe ✅", width='stretch'):
                if "last_mid" in st.session_state: delete_steam_email(st.session_state.last_mid)
                st.session_state.wizard_step = 0
                st.session_state.selected_acc = None
                st.session_state.pop("temp_code", None)
                st.rerun()
        return

    # ZAKŁADKI: STATUS / ADMIN
    tabs = st.tabs(["📊 Status", "⚙️ Admin"] if st.session_state.logged_in_as == "admin" else ["📊 Status"])
    
    with tabs[0]:
        st.write(f"Kod znajomego: `{acc.get('Kod znajomego', 'Brak')}`")
        now_pl = (datetime.now() + timedelta(hours=2)).strftime("%Y-%m-%d %H:%M:%S")
        st.write("Ustaw bana:")
        c1, c2, c3 = st.columns(3)
        if c1.button("20h"): sheet.update_cell(r_idx, 3, "20h"); sheet.update_cell(r_idx, 4, now_pl); st.cache_data.clear(); st.rerun()
        if c2.button("7 dni"): sheet.update_cell(r_idx, 3, "7 dni"); sheet.update_cell(r_idx, 4, now_pl); st.cache_data.clear(); st.rerun()
        if c3.button("Perm"): sheet.update_cell(r_idx, 3, "Perm"); sheet.update_cell(r_idx, 4, now_pl); st.cache_data.clear(); st.rerun()
        
        st.divider()
        st.write("Status turniejowy:")
        curr_s = acc.get('odblokowanie status', 'nie odblokowany')
        col_st1, col_st2 = st.columns([2, 1])
        with col_st1:
            st.write(f"Status turniejowy: **{curr_s.upper()}**")
        with col_st2:
            target_s = "odblokowany" if curr_s == "nie odblokowany" else "nie odblokowany"
            if st.button("Zmień 🔄", width='stretch'):
                st.session_state.selected_acc['odblokowanie status'] = target_s
                sheet.update_cell(r_idx, 7, target_s)
                st.cache_data.clear()
                st.rerun()

    if st.session_state.logged_in_as == "admin" and len(tabs) > 1:
        with tabs[1]:
            if st.button("WYCZYŚĆ BANA 🟢", width='stretch'):
                sheet.update_cell(r_idx, 3, ""); sheet.update_cell(r_idx, 4, ""); st.cache_data.clear(); st.rerun()
            st.divider()
            nl, np, nk = st.text_input("Login", acc['Nazwa konta']), st.text_input("Hasło", acc['Hasło']), st.text_input("Kod Znajomego", acc.get('Kod znajomego', ''))
            cc1, cc2 = st.columns(2)
            if cc1.button("Zapisz zmiany 💾"):
                sheet.update(range_name=f"A{r_idx}:B{r_idx}", values=[[nl, np]]); sheet.update_cell(r_idx, 8, nk); st.cache_data.clear(); st.rerun()
            if cc2.button("USUŃ KONTO 🗑️", type="primary"):
                sheet.update(range_name=f"A{r_idx}:B{r_idx}", values=[["", ""]]); sheet.update_cell(r_idx, 8, ""); st.cache_data.clear(); st.session_state.selected_acc = None; st.rerun()

    st.divider()
    if st.button("🚀 ZALOGUJ SIĘ", width='stretch'):
        st.session_state.wizard_step = 1; st.rerun()

# --- PANEL GŁÓWNY ---
if st.session_state.logged_in_as == "admin":
    with st.expander("🛠️ ADMIN"):
        if st.button("➕ Dodaj nowe konto"): 
            st.session_state.selected_acc = None # Czyścimy wybrane konto przy dodawaniu
            st.session_state.show_add_wizard = True; st.rerun()
        st.dataframe(pd.DataFrame(df_data, columns=headers), width='stretch', hide_index=True)

st.divider()
st.title("🛡️ Konta")

# FILTROWANIE
c_f1, c_f2, c_f3 = st.columns([2, 1, 1])
with c_f1:
    search = st.text_input("Szukaj...", "").lower()
with c_f2:
    st.write("##") # Margines
    # Dodajemy callback, który czyści 'selected_acc' przy kliknięciu filtra
    sort_ban = st.checkbox("Bany na górze ⏳", on_change=lambda: st.session_state.update({"selected_acc": None}))
with c_f3:
    st.write("##") # Margines
    sort_turek = st.checkbox("Odblokowane na górze 🏆", on_change=lambda: st.session_state.update({"selected_acc": None}))

# Sortowanie kont
accounts = [dict(zip(headers, row)) for row in df_data if row and row[0] != ""]
filtered = [a for a in accounts if search in a.get('Nazwa konta', '').lower()]

def sort_logic(acc):
    b_val = 0 if (sort_ban and acc.get('Pozostały czas / Status') != "Czyste" and acc.get('Pozostały czas / Status') != "") else 1
    t_val = 0 if (sort_turek and acc.get('odblokowanie status') == "odblokowany") else 1
    return (b_val, t_val, acc['Nazwa konta'])

filtered.sort(key=sort_logic)

# Wyświetlanie
cols = st.columns(4)
for idx, acc in enumerate(filtered):
    with cols[idx % 4]:
        with st.container(border=True):
            st.markdown(f"### {acc['Nazwa konta']}")
            tl = acc.get('Pozostały czas / Status', 'Czyste')
            if tl == "Czyste" or not tl: st.success("🟢 Brak bana")
            else: st.error(f"⏳ {tl}")
            st.write(f"Turek: **{acc.get('odblokowanie status', 'nie odblokowany')}**")
            if not acc.get('Kod znajomego', '').strip() or acc.get('Kod znajomego') == "Brak": st.warning("⚠️ Brak kodu")
            
            # Przycisk ZARZĄDZAJ
            if st.button("Zarządzaj", key=f"btn_{idx}", width='stretch'):
                st.session_state.selected_acc = acc
                st.session_state.wizard_step = 0
                st.rerun()

# --- LOGIKA WYWOŁYWANIA OKIEN ---
if st.session_state.get("show_add_wizard"):
    add_acc_dialog()
elif st.session_state.get("selected_acc"):
    # Tutaj dzieje się magia: okno odpala się TYLKO jeśli wybrano konto
    manage_dialog(st.session_state.selected_acc)
