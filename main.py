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
        st.title("🛡️ Panel Kont")
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

# --- PANEL ADMINA ---
if st.session_state.logged_in_as == "admin":
    with st.expander("⚙️ PANEL ADMINISTRATORA"):
        adm_c1, adm_c2 = st.columns([1, 2])
        with adm_c1:
            st.subheader("➕ Dodaj konto")
            if st.button("Uruchom kreator dodawania"):
                st.session_state.show_add_wizard = True

            @st.dialog("Kreator nowego konta")
            def add_acc_wizard():
                st.write("E-mail do weryfikacji:")
                st.code(EMAIL_USER)
                if st.button("Pobierz link weryfikacyjny 🔗"):
                    link = get_steam_data("link")
                    if link: st.link_button("KLIKNIJ, ABY ZWERYFIKOWAĆ", link)
                    else: st.error("Nie znaleziono linku.")
                st.divider()
                nl = st.text_input("Login")
                nh = st.text_input("Hasło")
                nk = st.text_input("Kod znajomego")
                
                if st.button("Zapisz w bazie ✅"):
                    if nl and nh:
                        with st.spinner("Szukanie miejsca w tabeli..."):
                            # Pobieramy całą kolumnę A, żeby zobaczyć gdzie są luki
                            col_a = sheet.col_values(1)
                            
                            # Szukamy pierwszego pustego wiersza (od drugiego wiersza w górę)
                            target_row = len(col_a) + 1
                            for i, value in enumerate(col_a):
                                if i == 0: continue # Omijamy nagłówek
                                if value.strip() == "": # Znaleźliśmy dziurę w tabeli!
                                    target_row = i + 1
                                    break
                            
                            # Przygotowujemy dane
                            new_data = [nl, nh, "", "", "", "", "nie odblokowany", nk]
                            
                            # Wpisujemy dane w konkretny wiersz zamiast append
                            range_name = f"A{target_row}:H{target_row}"
                            sheet.update(range_name, [new_data])
                            
                            st.success(f"Dodano konto w wierszu {target_row}!")
                            time.sleep(1)
                            st.rerun()
                    else:
                        st.error("Login i hasło są wymagane!")
                st.divider()
                nl = st.text_input("Login")
                nh = st.text_input("Hasło")
                nk = st.text_input("Kod znajomego")
                if st.button("Zapisz w bazie ✅"):
                    if nl and nh:
                        sheet.append_row([nl, nh, "", "", "", "", "nie odblokowany", nk])
                        st.success("Dodano!"); time.sleep(1); st.rerun()
            if "show_add_wizard" in st.session_state: add_acc_wizard()

        with adm_c2:
            st.subheader("📝 Edycja danych")
            import pandas as pd
            df = pd.DataFrame(df_data, columns=headers)
            edited_df = st.data_editor(df, num_rows="dynamic")
            if st.button("Zapisz zmiany w tabeli"):
                sheet.update([headers] + edited_df.values.tolist())
                st.success("Zaktualizowano!"); st.rerun()

st.divider()

# --- GŁÓWNY WIDOK ---
st.title("🛡️ Zarządzanie Kontami")
search = st.text_input("Szukaj...", "").lower()
accounts = [dict(zip(headers, row)) for row in df_data if row and row[0] != ""]
filtered = [a for a in accounts if search in a.get('Nazwa konta', '').lower()]

if "wizard_step" not in st.session_state: st.session_state.wizard_step = 0

cols = st.columns(4)
for idx, acc in enumerate(filtered):
    with cols[idx % 4]:
        with st.container(border=True):
            st.markdown(f"### {acc['Nazwa konta']}")
            tl = acc.get('Pozostały czas / Status', 'Czyste')
            if tl == "Czyste" or not tl: st.success("🟢 Gotowe")
            else: st.error(f"⏳ {tl}")
            
            if st.button("Otwórz Panel", key=f"panel_{idx}", use_container_width=True):
                st.session_state.selected_acc = acc
                st.session_state.wizard_step = 1
                st.rerun()

# DIALOG ZAKŁADKI (Logowanie + Status)
if "selected_acc" in st.session_state and st.session_state.selected_acc:
    acc = st.session_state.selected_acc
    @st.dialog(f"Konto: {acc['Nazwa konta']}")
    def manage():
        t1, t2 = st.tabs(["🔑 Logowanie", "📊 Status"])
        
        with t1:
            step = st.session_state.wizard_step
            if step == 1:
                st.write("Login:"); st.code(acc['Nazwa konta'])
                if st.button("Dalej ➡️"): st.session_state.wizard_step = 2; st.rerun()
            elif step == 2:
                st.write("Hasło:"); st.code(acc['Hasło'])
                if st.button("Dalej ➡️"): st.session_state.wizard_step = 3; st.rerun()
            elif step == 3:
                st.write("Kod Guard:")
                if st.button("Pobierz kod 📩"):
                    st.session_state.temp_code = get_steam_data("code")
                if "temp_code" in st.session_state:
                    st.code(st.session_state.temp_code if st.session_state.temp_code else "Brak kodu.")
                if st.button("Zakończ ✅", use_container_width=True):
                    st.session_state.selected_acc = None
                    st.session_state.wizard_step = 0
                    st.rerun()

        with t2:
            st.write(f"Kod znajomego: `{acc.get('Kod znajomego', 'Brak')}`")
            r_idx = 0
            for i, row in enumerate(raw_rows):
                if row[0] == acc['Nazwa konta']: r_idx = i + 1; break
            
            st.divider()
            st.write("Ustaw bana:")
            now_pl = (datetime.now() + timedelta(hours=2)).strftime("%Y-%m-%d %H:%M:%S")
            c1, c2, c3 = st.columns(3)
            if c1.button("20h"):
                sheet.update_cell(r_idx, 3, "20h"); sheet.update_cell(r_idx, 4, now_pl); st.rerun()
            if c2.button("7 dni"):
                sheet.update_cell(r_idx, 3, "7 dni"); sheet.update_cell(r_idx, 4, now_pl); st.rerun()
            if c3.button("Perm"):
                sheet.update_cell(r_idx, 3, "Perm"); sheet.update_cell(r_idx, 4, now_pl); st.rerun()
            
            if st.button("Wyczyść bana", use_container_width=True):
                sheet.update_cell(r_idx, 3, ""); sheet.update_cell(r_idx, 4, ""); st.rerun()

            st.divider()
            curr_s = acc.get('odblokowanie status', 'nie odblokowany')
            new_s = st.selectbox("Status turniejowy", ["nie odblokowany", "odblokowany"], 
                                 index=0 if curr_s == "nie odblokowany" else 1)
            if st.button("Zapisz status"):
                sheet.update_cell(r_idx, 7, new_s); st.success("Zmieniono!"); time.sleep(1); st.rerun()
    manage()
