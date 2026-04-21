import streamlit as st
import gspread
from oauth2client.service_account import ServiceAccountCredentials
import imaplib
import email
import re
import time
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
        else:
            content = msg.get_payload(decode=True).decode(errors='ignore')

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
        st.title("🛡️ System Zarządzania Kontami")
        pass_input = st.text_input("Wprowadź hasło dostępu", type="password")
        if pass_input:
            if pass_input == st.secrets["admin_password"]:
                st.session_state.logged_in_as = "admin"; st.rerun()
            elif pass_input == st.secrets["user_password"]:
                st.session_state.logged_in_as = "user"; st.rerun()
            else: st.error("Błędne hasło!")
    st.stop()

# Pobieranie danych
sheet = connect_gsheet()
raw_rows = sheet.get_all_values()
headers = raw_rows[0]
df_data = raw_rows[1:]

# --- PANEL ADMINA ---
if st.session_state.logged_in_as == "admin":
    with st.expander("🛠️ PANEL ADMINISTRATORA"):
        col_adm1, col_adm2 = st.columns([1, 2])
        
        with col_adm1:
            st.subheader("➕ Dodaj konto")
            if st.button("Uruchom kreator dodawania"):
                st.session_state.show_add_wizard = True

            @st.dialog("Kreator nowego konta")
            def add_acc_wizard():
                st.write("1. E-mail przypisany do kont:")
                st.code(EMAIL_USER)
                if st.button("Szukaj linku weryfikacyjnego Steam 🔗"):
                    link = get_steam_data("link")
                    if link: st.link_button("KLIKNIJ, ABY ZWERYFIKOWAĆ", link)
                    else: st.error("Nie znaleziono linku w mailach.")
                
                st.divider()
                n_login = st.text_input("Nazwa konta (Steam Login)")
                n_pass = st.text_input("Hasło konta")
                n_friend = st.text_input("Kod znajomego")
                
                if st.button("Zapisz konto w bazie 💾"):
                    if n_login and n_pass:
                        new_row = [n_login, n_pass, "", "", "", "", "nie odblokowany", n_friend]
                        sheet.append_row(new_row)
                        st.success("Dodano!"); time.sleep(1); st.rerun()
                    else: st.error("Login i hasło są wymagane!")
            
            if "show_add_wizard" in st.session_state:
                add_acc_wizard()

        with col_adm2:
            st.subheader("📝 Szybka edycja bazy")
            import pandas as pd
            df = pd.DataFrame(df_data, columns=headers)
            edited_df = st.data_editor(df, num_rows="dynamic")
            if st.button("Zapisz zmiany w całej tabeli"):
                sheet.update([headers] + edited_df.values.tolist())
                st.success("Baza zaktualizowana!"); st.rerun()

st.divider()

# --- GŁÓWNY WIDOK KONTA ---
st.title("🛡️ Twoje Konta")
search = st.text_input("Szukaj...", "").lower()
accounts = [dict(zip(headers, row)) for row in df_data if row and row[0] != ""]
filtered = [a for a in accounts if search in a.get('Nazwa konta', '').lower()]

if "wizard_step" not in st.session_state: st.session_state.wizard_step = 0

cols = st.columns(4)
for idx, acc in enumerate(filtered):
    with cols[idx % 4]:
        with st.container(border=True):
            st.markdown(f"### {acc['Nazwa konta']}")
            time_left = acc.get('Pozostały czas / Status', 'Czyste')
            if time_left == "Czyste" or not time_left: st.success("🟢 Gotowe")
            else: st.error(f"⏳ {time_left}")
            
            if st.button("🚀 Zaloguj", key=f"log_{idx}", use_container_width=True):
                st.session_state.selected_acc = acc
                st.session_state.wizard_step = 1
                st.rerun()

# FLOW LOGOWANIA (WIZARD)
if "selected_acc" in st.session_state and st.session_state.selected_acc:
    acc = st.session_state.selected_acc
    
    @st.dialog(f"Logowanie: {acc['Nazwa konta']}")
    def login_wizard():
        step = st.session_state.wizard_step
        
        if step == 1:
            st.write("Krok 1: Podaj Login")
            st.code(acc['Nazwa konta'])
            if st.button("Dalej ➡️"):
                st.session_state.wizard_step = 2; st.rerun()
        
        elif step == 2:
            st.write("Krok 2: Podaj Hasło")
            st.code(acc['Hasło'])
            if st.button("Dalej ➡️"):
                st.session_state.wizard_step = 3; st.rerun()
        
        elif step == 3:
            st.write("Krok 3: Kod Steam Guard")
            if st.button("Pobierz kod teraz 📩"):
                with st.spinner("Łączenie..."):
                    st.session_state.temp_code = get_steam_data("code")
            if "temp_code" in st.session_state:
                st.code(st.session_state.temp_code if st.session_state.temp_code else "Kod nie dotarł.")
            
            st.divider()
            # Opcja dla Admina: Ustawianie bana
            if st.session_state.logged_in_as == "admin":
                st.write("Administracja bana:")
                r_idx = 0
                for i, row in enumerate(raw_rows):
                    if row[0] == acc['Nazwa konta']: r_idx = i + 1; break
                now_pl = (datetime.now() + timedelta(hours=2)).strftime("%Y-%m-%d %H:%M:%S")
                if st.button("Nałóż ban 20h"):
                    sheet.update_cell(r_idx, 3, "20h")
                    sheet.update_cell(r_idx, 4, now_pl); st.success("Nałożono!"); time.sleep(1); st.rerun()

            if st.button("Zakończ ✅", use_container_width=True):
                st.session_state.selected_acc = None
                st.session_state.wizard_step = 0
                if "temp_code" in st.session_state: del st.session_state.temp_code
                st.rerun()
    login_wizard()
