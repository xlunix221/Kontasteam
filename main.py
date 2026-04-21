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

def get_steam_code():
    try:
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

# LOGOWANIE
if "admin_password" not in st.secrets:
    st.error("BŁĄD: Nie ustawiono hasła 'admin_password' w Secrets!")
    st.stop()

input_pass = st.text_input("Podaj hasło do panelu", type="password")
if input_pass != st.secrets["admin_password"]:
    if input_pass != "":
        st.warning("Błędne hasło!")
    st.stop()

# Inicjalizacja stanów dla Wizarda dodawania konta
if 'add_wizard_step' not in st.session_state:
    st.session_state.add_wizard_step = 0
if 'new_acc_data' not in st.session_state:
    st.session_state.new_acc_data = {}

try:
    sheet = connect_gsheet()
    raw_data = sheet.get_all_values()
    headers = raw_data[0]
    data = [dict(zip(headers, row)) for row in raw_data[1:] if row and row[0] != ""]
except Exception as e:
    st.error(f"Błąd połączenia z Google Sheets: {e}")
    st.stop()

# DIALOG: DODAWANIE KONTA
@st.dialog("➕ Dodaj nowe konto")
def add_account_wizard():
    step = st.session_state.add_wizard_step
    
    if step == 0:
        st.write(f"Krok 1: Powiąż konto z e-mailem:")
        st.info(EMAIL_USER)
        if st.button("Gotowe, idź dalej ➡️"):
            st.session_state.add_wizard_step = 1
            st.rerun()

    elif step == 1:
        st.write("Krok 2: Podaj nazwę użytkownika Steam")
        name = st.text_input("Nazwa konta (login)")
        if st.button("Dalej ➡️"):
            if name:
                st.session_state.new_acc_data['name'] = name
                st.session_state.add_wizard_step = 2
                st.rerun()
            else:
                st.error("Podaj nazwę!")

    elif step == 2:
        st.write(f"Krok 3: Podaj hasło dla **{st.session_state.new_acc_data['name']}**")
        password = st.text_input("Hasło", type="default")
        if st.button("Dalej ➡️"):
            if password:
                st.session_state.new_acc_data['pass'] = password
                st.session_state.add_wizard_step = 3
                st.rerun()
            else:
                st.error("Podaj hasło!")

    elif step == 3:
        st.write("Krok 4: Podaj Kod Znajomego (Friend Code)")
        f_code = st.text_input("Kod znajomego")
        if st.button("Zapisz konto ✅"):
            with st.spinner("Zapisywanie w arkuszu..."):
                # Przygotowanie wiersza: 
                # [Nazwa, Hasło, TypBana, StartBana, KoniecBana, TimeLeft(puste-formula), Status, KodZnajomego]
                new_row = [
                    st.session_state.new_acc_data['name'],
                    st.session_state.new_acc_data['pass'],
                    "", "", "", "", # Ban info puste
                    "nie odblokowany",
                    f_code if f_code else "Brak"
                ]
                sheet.append_row(new_row)
                st.success("Konto dodane pomyślnie!")
                time.sleep(1.5)
                # Reset wizarda
                st.session_state.add_wizard_step = 0
                st.session_state.new_acc_data = {}
                st.rerun()

# --- GŁÓWNY PANEL ---
st.title("🛡️ Panel Zarządzania Kontami")

# Górne menu sterujące
m1, m2 = st.columns([3, 1])
with m1:
    search = st.text_input("Szukaj konta...", "").lower()
with m2:
    st.write("##") # Margines
    if st.button("➕ Dodaj konto", use_container_width=True):
        st.session_state.add_wizard_step = 0
        add_account_wizard()

filtered_data = [d for d in data if search in d.get('Nazwa konta', '').lower()]

# Wyświetlanie kont
if 'selected_acc' not in st.session_state:
    st.session_state.selected_acc = None
if 'wizard_step' not in st.session_state:
    st.session_state.wizard_step = 0

cols = st.columns(4)
for idx, acc in enumerate(filtered_data):
    with cols[idx % 4]:
        with st.container(border=True):
            st.markdown(f"### {acc.get('Nazwa konta', 'Bez nazwy')}")
            time_left = acc.get('Pozostały czas / Status', 'Czyste')
            if time_left == "Czyste" or time_left == "":
                st.success("🟢 Czyste")
            else:
                st.error(f"⏳ {time_left}")
            
            t_status = acc.get('odblokowanie status', '')
            st.write(f"Turniejowy: **{t_status}**")

            if st.button("Otwórz Panel", key=f"acc_{idx}"):
                st.session_state.selected_acc = acc
                st.session_state.wizard_step = 1
                st.rerun()

# DIALOG: ZARZĄDZANIE KONTYM
if st.session_state.selected_acc:
    acc = st.session_state.selected_acc
    @st.dialog(f"Zarządzanie: {acc.get('Nazwa konta')}")
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
            
            now_pl = datetime.now() + timedelta(hours=2)
            now_timestamp = now_pl.strftime("%Y-%m-%d %H:%M:%S")

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
            new_status = st.selectbox("Status turniejowy", ["nie odblokowany", "odblokowany"], 
                                      index=0 if acc.get('odblokowanie status') == "nie odblokowany" else 1)
            
            if st.button("Zapisz zmiany", use_container_width=True):
                sheet.update_cell(row_idx, 7, new_status)
                st.success("Zapisano!")
                time.sleep(1)
                st.rerun()

        with t2:
            step = st.session_state.wizard_step
            if step == 1:
                st.write("Krok 1: Login")
                st.code(acc['Nazwa konta'])
                if st.button("Dalej ➡️"):
                    st.session_state.wizard_step = 2
                    st.rerun()
            elif step == 2:
                st.write("Krok 2: Hasło")
                st.code(acc['Hasło'])
                if st.button("Dalej ➡️"):
                    st.session_state.wizard_step = 3
                    st.rerun()
            elif step == 3:
                if st.button("Pobierz kod 📩"):
                    with st.spinner("Łączenie..."):
                        st.session_state.current_code = get_steam_code()
                if 'current_code' in st.session_state:
                    st.code(st.session_state.current_code)
                    if st.button("Gotowe ✅"):
                        st.session_state.selected_acc = None
                        st.session_state.wizard_step = 0
                        del st.session_state.current_code
                        st.rerun()
    manage()
