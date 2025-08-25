import streamlit as st
import pandas as pd
import calendar
from io import BytesIO

# --- Konfiguracja aplikacji ---
st.set_page_config(page_title="Grafik Ochrony", layout="wide")
st.title("📅 Grafik Pracowników Ochrony")

# --- Parametry ---
year = st.sidebar.number_input("Rok", 2025, 2100, 2025)
month = st.sidebar.selectbox("Miesiąc", list(range(1, 13)), index=7)
days_in_month = calendar.monthrange(year, month)[1]

# --- Lista pracowników (na start przykładowi) ---
default_workers = ["PIASECKI LESŁAW", "RYĆ JULIA", "STENCEL PIOTR", "GOŚCINIAK PAWEŁ", "STOPIŃSKI DAMIAN"]
workers = st.sidebar.text_area("Pracownicy (po jednym wierszu)", "\n".join(default_workers)).splitlines()

# --- Symbole i godziny ---
shift_hours = {"D": 12, "N": 12, "U": 0, "W": 0, "X": 12, "": 0}

# --- Tworzenie pustej tabeli ---
columns = [str(i) for i in range(1, days_in_month + 1)]
df = pd.DataFrame("", index=workers, columns=columns)

# --- Sesja (zachowanie zmian) ---
if "schedule" not in st.session_state:
    st.session_state["schedule"] = df.copy()

schedule = st.session_state["schedule"]

# --- Edycja tabeli ---
edited = st.data_editor(schedule, num_rows="dynamic")

# --- Obliczanie sum godzin ---
def calculate_hours(row):
    total = 0
    for v in row:
        total += shift_hours.get(v, 0)
    return total

edited["RAZEM"] = edited.apply(calculate_hours, axis=1)

# --- Wyświetlenie tabeli z sumami ---
st.subheader("✅ Grafik z podsumowaniem")
st.dataframe(edited, use_container_width=True)

# --- Eksport do Excel ---
def to_excel(df):
    output = BytesIO()
    writer = pd.ExcelWriter(output, engine="openpyxl")
    df.to_excel(writer, sheet_name="Grafik")
    writer.close()
    return output.getvalue()

excel_data = to_excel(edited)

st.download_button(
    label="💾 Pobierz grafik do Excel",
    data=excel_data,
    file_name=f"grafik_{year}_{month}.xlsx",
    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
)

# --- Zapisywanie zmian ---
st.session_state["schedule"] = edited.drop(columns=["RAZEM"])
