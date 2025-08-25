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
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL UNIQUE
        );
        """)
        cur.execute("""
        CREATE TABLE IF NOT EXISTS days_off(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            employee_id INTEGER NOT NULL,
            day TEXT NOT NULL, -- ISO date
            UNIQUE(employee_id, day),
            FOREIGN KEY(employee_id) REFERENCES employees(id) ON DELETE CASCADE
        );
        """)
        cur.execute("""
        CREATE TABLE IF NOT EXISTS shifts(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            site_id INTEGER NOT NULL,
            day TEXT NOT NULL, -- ISO date
            shift_type TEXT NOT NULL, -- 'D' | 'N' | '24'
            employee_id INTEGER NOT NULL,
            UNIQUE(site_id, day, shift_type),
            FOREIGN KEY(site_id) REFERENCES sites(id) ON DELETE CASCADE,
            FOREIGN KEY(employee_id) REFERENCES employees(id) ON DELETE CASCADE
        );
        """)
        con.commit()

def list_employees(con):
    return con.execute("SELECT id, first_name, last_name, contract_type, preference FROM employees ORDER BY last_name, first_name").fetchall()

def list_sites(con):
    return con.execute("SELECT id, name FROM sites ORDER BY name").fetchall()

def employee_fullname(row):
    return f"{row[1]} {row[2]}"

def employee_pref_ok(pref: str, shift_type: str) -> bool:
    if pref == "BRAK":
        return True
    if pref == "24H":
        return shift_type == "24"
    if pref == "DNIOWKI":
        return shift_type == "D"
    if pref == "NOCKI":
        return shift_type == "N"
    return True

def shift_hours(shift_type: str) -> int:
    return 24 if shift_type == "24" else 12

def is_employee_free(con, employee_id: int, day: date) -> Tuple[bool, Optional[str]]:
    d = day.isoformat()
    # Check day off
    off = con.execute("SELECT 1 FROM days_off WHERE employee_id=? AND day=?", (employee_id, d)).fetchone()
    if off:
        return (False, "Dzień wolny")
    # Check any shift that day (any site)
    busy = con.execute("SELECT s2.name FROM shifts sh JOIN sites s2 ON s2.id = sh.site_id WHERE sh.employee_id=? AND sh.day=?", (employee_id, d)).fetchone()
    if busy:
        return (False, f"Już pracuje na obiekcie: {busy[0]}")
    return (True, None)

def assign_shift(con, site_id: int, day: date, shift_type: str, employee_id: int) -> Tuple[bool, str]:
    ok, reason = is_employee_free(con, employee_id, day)
    if not ok:
        return (False, f"Konflikt: {reason}")
    # Check preference
    pref = con.execute("SELECT preference FROM employees WHERE id=?", (employee_id,)).fetchone()[0]
    if not employee_pref_ok(pref, shift_type):
        return (False, f"Niezgodne z preferencją ({pref})")
    try:
        con.execute("INSERT INTO shifts(site_id, day, shift_type, employee_id) VALUES(?,?,?,?)", (site_id, day.isoformat(), shift_type, employee_id))
        con.commit()
        return (True, "Dodano")
    except sqlite3.IntegrityError:
        return (False, "Zmiana już istnieje")

def remove_shift(con, site_id: int, day: date, shift_type: str):
    con.execute("DELETE FROM shifts WHERE site_id=? AND day=? AND shift_type=?", (site_id, day.isoformat(), shift_type))
    con.commit()

def shifts_for_month(con, year: int, month: int):
    d0 = date(year, month, 1)
    if month == 12:
        d1 = date(year+1, 1, 1)
    else:
        d1 = date(year, month+1, 1)
    rows = con.execute("""
        SELECT sh.site_id, sh.day, sh.shift_type, sh.employee_id, e.first_name, e.last_name
        FROM shifts sh
        JOIN employees e ON e.id = sh.employee_id
        WHERE sh.day >= ? AND sh.day < ?
    """, (d0.isoformat(), d1.isoformat())).fetchall()
    # map: (site_id, day, shift_type) -> (emp_id, name)
    out = {}
    for site_id, d, stype, eid, fn, ln in rows:
        out[(site_id, d, stype)] = (eid, f"{fn} {ln}")
    return out

def employee_hours_in_period(con, employee_id: int, start: date, end: date) -> int:
    rows = con.execute("""
        SELECT shift_type FROM shifts WHERE employee_id=? AND day >= ? AND day <= ?
    """, (employee_id, start.isoformat(), end.isoformat())).fetchall()
    return sum(shift_hours(r[0]) for r in rows)

# -----------------------
# UI
# -----------------------
st.set_page_config(page_title="Grafiki Ochrony", layout="wide")
st.title("Grafiki pracowników ochrony")

init_db()
con = get_conn()

with st.sidebar:
    st.header("Ustawienia widoku")
    today = date.today()
    year = st.number_input("Rok", min_value=2020, max_value=2100, value=today.year, step=1)
    month = st.number_input("Miesiąc", min_value=1, max_value=12, value=today.month, step=1)
    st.caption("Widok miesięczny. Podgląd normy i rozliczeń poniżej kalendarza.")
    st.divider()
    st.subheader("Dodaj pracownika")
    with st.form("add_emp"):
        fn = st.text_input("Imię")
        ln = st.text_input("Nazwisko")
        ctype = st.selectbox("Rodzaj umowy", ["UOP", "UZ"], index=0, help="UOP = umowa o pracę, UZ = umowa zlecenie")
        pref = st.selectbox("Preferencja", ["BRAK", "24H", "DNIOWKI", "NOCKI"], index=0)
        submitted = st.form_submit_button("Dodaj pracownika")
        if submitted:
            if fn.strip() and ln.strip():
                try:
                    con.execute("INSERT INTO employees(first_name, last_name, contract_type, preference) VALUES(?,?,?,?)", (fn.strip(), ln.strip(), ctype, pref))
                    con.commit()
                    st.success("Dodano pracownika.")
                except Exception as e:
                    st.error(f"Błąd: {e}")
            else:
                st.error("Wpisz imię i nazwisko.")
    st.subheader("Dodaj obiekt")
    with st.form("add_site"):
        site_name = st.text_input("Nazwa obiektu")
        s_sub = st.form_submit_button("Dodaj obiekt")
        if s_sub:
            if site_name.strip():
                try:
                    con.execute("INSERT INTO sites(name) VALUES(?)", (site_name.strip(),))
                    con.commit()
                    st.success("Dodano obiekt.")
                except sqlite3.IntegrityError:
                    st.error("Taki obiekt już istnieje.")
            else:
                st.error("Wpisz nazwę obiektu.")

employees = list_employees(con)
sites = list_sites(con)

st.subheader("Formularz przypięcia pracownika do grafiku i dni wolnych")
col1, col2 = st.columns(2, gap="large")

with col1:
    st.markdown("**Dni wolne pracownika**")
    emp_opts = {f"{r[1]} {r[2]} ({r[3]})": r[0] for r in employees}
    if emp_opts:
        emp_sel = st.selectbox("Pracownik", list(emp_opts.keys()))
        emp_id = emp_opts[emp_sel]
        off_day = st.date_input("Wybierz dzień wolny", value=date(year, month, 1))
        if st.button("Dodaj dzień wolny"):
            try:
                con.execute("INSERT OR IGNORE INTO days_off(employee_id, day) VALUES(?,?)", (emp_id, off_day.isoformat()))
                con.commit()
                st.success("Dodano dzień wolny.")
            except Exception as e:
                st.error(str(e))
    else:
        st.info("Dodaj pracowników w panelu bocznym.")

with col2:
    st.markdown("**Przypisz do obiektu (skrót)**")
    if emp_opts and sites:
        emp_sel2 = st.selectbox("Pracownik", list(emp_opts.keys()), key="emp2")
        site_dict = {s[1]: s[0] for s in sites}
        site_sel = st.selectbox("Obiekt", list(site_dict.keys()))
        day_sel = st.date_input("Dzień", value=date(year, month, 1), key="day2")
        stype = st.selectbox("Rodzaj służby", ["D", "N", "24"], help="D=12h dzień, N=12h noc, 24=24h")
        if st.button("Dodaj do grafiku"):
            ok, msg = assign_shift(con, site_dict[site_sel], day_sel, stype, emp_opts[emp_sel2])
            if ok:
                st.success("Dodano służbę.")
            else:
                st.error(msg)
    else:
        st.info("Dodaj pracowników i obiekty, aby przypisywać służby.")

st.divider()
st.subheader(f"Kalendarz: {year}-{month:02d}")

# render monthly grid per site
start = date(year, month, 1)
end = (date(year + (month==12), (month % 12) + 1, 1) - timedelta(days=1))
days = [(start + timedelta(days=i)) for i in range((end - start).days + 1)]
hol = set(polish_holidays(year))

shifts_map = shifts_for_month(con, year, month)
site_tabs = st.tabs([s[1] for s in sites] or ["Brak obiektów"])

for idx, tab in enumerate(site_tabs):
    with tab:
        if not sites:
            st.info("Najpierw dodaj obiekty.")
            continue
        site_id = sites[idx][0]
        # Table-like layout
        st.caption("Kliknij, aby dodać/zdjąć obsadę. Widok pokazuje 3 potencjalne służby: D, N, 24.")
        for d in days:
            is_weekend = d.weekday() >= 5
            is_holiday = d in hol
            row_color = "#fff0f0" if is_holiday else ("#f6f6f6" if is_weekend else "#ffffff")
            st.markdown(f"<div style='background:{row_color}; padding:8px; border-radius:8px; margin-bottom:6px;'>", unsafe_allow_html=True)
            st.markdown(f"**{d.strftime('%Y-%m-%d (%a)')}** " + (" — Święto" if is_holiday else ""), unsafe_allow_html=True)
            cols = st.columns(3)
            for ci, stype in enumerate(["D","N","24"]):
                key_base = f"{site_id}-{d.isoformat()}-{stype}"
                assigned = shifts_map.get((site_id, d.isoformat(), stype))
                if assigned:
                    cols[ci].markdown(f"**{stype}**: {assigned[1]}")
                    if cols[ci].button("Usuń", key=key_base+"-rm"):
                        remove_shift(con, site_id, d, stype)
                        st.rerun()
                else:
                    # pick employee
                    opts = ["(pusty)"] + [f"{r[1]} {r[2]} [{r[3]}/{r[4]}]" for r in employees if employee_pref_ok(r[4], stype)]
                    choice = cols[ci].selectbox(f"{stype}", opts, key=key_base+"-sb")
                    if choice != "(pusty)":
                        # find employee id
                        name_part = choice.split(" [")[0]
                        emp = next((r for r in employees if f"{r[1]} {r[2]}" == name_part), None)
                        if emp:
                            ok, msg = assign_shift(con, site_id, d, stype, emp[0])
                            if not ok:
                                cols[ci].error(msg)
                            else:
                                st.rerun()
            st.markdown("</div>", unsafe_allow_html=True)

# -----------------------
# Auto-fill
# -----------------------
st.divider()
st.subheader("Automatyczne uzupełnianie braków")
with st.expander("Uzupełnij automatycznie służby na widocznym miesiącu (uwzględnia dni wolne i preferencje)"):
    site_multi = st.multiselect("Obiekty do uzupełnienia", [s[1] for s in sites])
    if st.button("Wypełnij braki"):
        site_ids = [s[0] for s in sites if s[1] in site_multi] if site_multi else [s[0] for s in sites]
        emp_rows = list_employees(con)
        # simple greedy: iterate days, then site, then shift type -> assign first free & pref-matching employee with the least hours this month (balancing)
        month_start = date(year, month, 1)
        month_end = end
        # precompute hours per employee in month
        hours_cache = {r[0]: employee_hours_in_period(con, r[0], month_start, month_end) for r in emp_rows}
        made = 0
        for d in days:
            for sid in site_ids:
                for stype in ["D","N","24"]:
                    if (sid, d.isoformat(), stype) in shifts_map:
                        continue
                    # choose candidate employees
                    candidates = [r for r in emp_rows if employee_pref_ok(r[4], stype)]
                    # sort by current month hours (asc) to balance, UOP first (to meet norm), then UZ
                    def sort_key(r):
                        return (0 if r[3]=="UOP" else 1, hours_cache[r[0]])
                    candidates.sort(key=sort_key)
                    placed = False
                    for r in candidates:
                        ok, reason = is_employee_free(con, r[0], d)
                        if ok:
                            ok2, msg = assign_shift(con, sid, d, stype, r[0])
                            if ok2:
                                hours_cache[r[0]] += shift_hours(stype)
                                made += 1
                                placed = True
                                break
                    # continue to next slot whether placed or not
        st.success(f"Uzupełniono {made} zmian. Odśwież widok jeśli nie zaktualizował się automatycznie.")
        st.rerun()

# -----------------------
# Raporty
# -----------------------
st.divider()
st.subheader("Raporty i normy czasu pracy")
colA, colB = st.columns(2)
with colA:
    st.markdown("**Norma miesięczna** (UOP):")
    st.write(f"{working_time_norm_month(year, month)} godzin")
    st.markdown("**Norma kwartalna** (UOP):")
    st.write(f"{working_time_norm_quarter(year, quarter_of_month(month))} godzin")

with colB:
    st.markdown("**Podsumowanie godzin (miesiąc)**")
    month_start = date(year, month, 1)
    month_end = end
    data = []
    for r in employees:
        eid = r[0]
        full = f"{r[1]} {r[2]}"
        hours = employee_hours_in_period(con, eid, month_start, month_end)
        norm = working_time_norm_month(year, month) if r[3] == "UOP" else None
        excess = (hours - norm) if norm is not None else None
        data.append({
            "Pracownik": full,
            "Umowa": r[3],
            "Preferencja": r[4],
            "Godziny (miesiąc)": hours,
            "Norma (jeśli UOP)": norm if norm is not None else "-",
            "Nadwyżka/Brak": (excess if excess is not None else "-"),
        })
    st.dataframe(data, hide_index=True, use_container_width=True)

st.download_button("Pobierz raport (CSV)", data="\n".join(
    [",".join(["Pracownik","Umowa","Preferencja","Godziny_miesiąc","Norma","Nadwyżka/Brak"])] +
    [",".join([str(d[k]) for k in ["Pracownik","Umowa","Preferencja","Godziny (miesiąc)","Norma (jeśli UOP)","Nadwyżka/Brak"]]) for d in data]
), file_name=f"raport_{year}_{month:02d}.csv", mime="text/csv")

st.caption("Eksport do Excela/PDF można dodać w kolejnej iteracji. Ten MVP zapisuje dane lokalnie w SQLite (plik 'grafik.db').")
