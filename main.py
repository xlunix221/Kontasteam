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
    """Pobiera kod (5-6 znaków) LUB link weryfikacyjny ze Steam."""
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
                if part.get_content_type() == "text/plain" or part.get_content_type() == "text/html":
                    content += part.get_payload(decode=True).decode(errors='ignore')
        else:
            content = msg.get_payload(decode=True).decode(errors='ignore')

        if search_type == "link":
            # Szukamy linku weryfikacyjnego Steam
            links = re.findall(r'https://store\.steampowered\.com/account/newaccountverification\?[\w=&?]+', content)
            return links[0] if links else None
        else:
            # Szukamy kodu Guard
            code = re.search(r'\b[A-Z0-9]{5}\b', content)
            if not code: code = re.search(r'\b\d{6}\b', content)
            return code.group(0) if code else None
    except:
        return None

# --- INTERFEJS ---
st.set_page_config(page_title="CS Manager PRO", layout="wide")

# LOGOWANIE DWUPOZIOMOWE
if "logged_in_as" not in st.session_state:
    st.session_state.logged_in_as = None

if st.session_state.logged_in_as is None:
    pass_input = st.text_input("Podaj hasło do panelu", type="password")
    if pass_input:
        if pass_input == st.secrets["admin_password"]:
            st.session_state.logged_in_as = "admin"
            st.rerun()
        elif pass_input == st.secrets["user_password"]:
            st.session_state.logged_in_as = "user"
            st.rerun()
        else:
            st.error("Błędne hasło!")
    st.stop()

# Połączenie z arkuszem
sheet = connect_gsheet()
raw_rows = sheet.get_all_values()
headers = raw_rows[0]
df_data = raw_rows[1:]

# --- PANEL ADMINISTRATORA ---
if st.session_state.logged_in_as == "admin":
    with st.expander("⚙️ TRYB ADMINISTRATORA - Zarządzanie bazą"):
        st.warning("Tutaj możesz edytować wszystko. Zmiany zapisują się po kliknięciu 'Zapisz zmiany w arkuszu'.")
        
        # Edytor danych (wygodna tabela)
        import pandas as pd
        df = pd.DataFrame(df_data, columns=headers)
        edited_df = st.data_editor(df, num_rows="dynamic", use_container_width=True)
        
        if st.button("💾 Zapisz wszystkie zmiany w arkuszu"):
            with st.spinner("Aktualizacja..."):
                # Nadpisujemy cały arkusz nowymi danymi z edytora
                new_values = [headers] + edited_df.values.tolist()
                sheet.update(new_values)
                st.success("Dane zostały zaktualizowane!")
                time.sleep(1)
                st.rerun()

st.divider()

# --- PANEL UŻYTKOWNIKA (Kafelki) ---
st.title("🛡️ Konta Steam")
search = st.text_input("Szukaj konta...", "").lower()

# Konwersja do słowników dla kafelków
accounts = [dict(zip(headers, row)) for row in df_data if row and row[0] != ""]
filtered = [a for a in accounts if search in a.get('Nazwa konta', '').lower()]

cols = st.columns(4)
for idx, acc in enumerate(filtered):
    with cols[idx % 4]:
        with st.container(border=True):
            st.subheader(acc.get('Nazwa konta', 'Bez nazwy'))
            time_left = acc.get('Pozostały czas / Status', 'Czyste')
            if time_left == "Czyste" or not time_left:
                st.success("🟢 Gotowe")
            else:
                st.error(f"⏳ {time_left}")
            
            if st.button("Pokaż dane", key=f"btn_{idx}"):
                st.session_state.selected_acc = acc
                st.rerun()

# DIALOG ZARZĄDZANIA (Kody, Linki, Bany)
if "selected_acc" in st.session_state and st.session_state.selected_acc:
    acc = st.session_state.selected_acc
    
    @st.dialog(f"Konto: {acc['Nazwa konta']}")
    def manage():
        t1, t2, t3 = st.tabs(["🔑 Logowanie", "📊 Status", "📧 Weryfikacja"])
        
        with t1:
            st.write("Login:")
            st.code(acc['Nazwa konta'])
            st.write("Hasło:")
            st.code(acc['Hasło'])
            if st.button("Pobierz kod Guard 📩"):
                with st.spinner("Szukam kodu..."):
                    res = get_steam_data("code")
                    st.code(res if res else "Nie znaleziono kodu.")

        with t2:
            st.write(f"Kod znajomego: `{acc.get('Kod znajomego', 'Brak')}`")
            # Znajdź wiersz w arkuszu
            r_idx = 0
            for i, row in enumerate(raw_rows):
                if row[0] == acc['Nazwa konta']:
                    r_idx = i + 1; break
            
            now_pl = (datetime.now() + timedelta(hours=2)).strftime("%Y-%m-%d %H:%M:%S")
            c1, c2 = st.columns(2)
            if c1.button("Ban 20h"):
                sheet.update_cell(r_idx, 3, "20h")
                sheet.update_cell(r_idx, 4, now_pl); st.rerun()
            if c2.button("Wyczyść bana"):
                sheet.update_cell(r_idx, 3, "")
                sheet.update_cell(r_idx, 4, ""); st.rerun()

        with t3:
            st.write("Weryfikacja nowego konta:")
            if st.button("Szukaj linku aktywacyjnego 🔗"):
                with st.spinner("Skanowanie poczty..."):
                    link = get_steam_data("link")
                    if link:
                        st.success("Znaleziono link!")
                        st.link_button("KLIKNIJ, ABY ZWERYFIKOWAĆ", link)
                    else:
                        st.error("Brak linku w ostatnich mailach.")
    manage()
