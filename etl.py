import kaggle
from pathlib import Path
import pandas as pd
import os
from urllib.parse import quote_plus
from dotenv import load_dotenv
from sqlalchemy import create_engine

RAW_DIR = Path("data/raw")
RAW_FILE = RAW_DIR / "Patient_Health_Records_Raw.csv"
PROCESSED_DIR = Path("data/processed")

TABLE_NAME = "patients"


def extract():
    if RAW_FILE.exists():
        return

    RAW_DIR.mkdir(parents=True, exist_ok=True)
    kaggle.api.dataset_download_files(
        "mursaleen880/patient-health-record-raw-csv",
        path=RAW_DIR,
        unzip=True,
    )
    # print("Downloaded files:", [f.name for f in RAW_DIR.iterdir()])  


def transform(df):
    df = df.copy()

    # standardize column names
    df.columns = df.columns.str.lower()

    # rebuild missing patient_ids from row position, formatted as ID-1
    missing_id = df["patient_id"].isna()
    id_number = pd.to_numeric(df["patient_id"].str.replace("ID-", "", regex=False), errors="coerce")
    expected_number = pd.Series(df.index + 1, index=df.index)
    id_number = id_number.fillna(expected_number).astype(int)
    df["patient_id"] = "ID-" + id_number.astype(str)
    # print(f"Rebuilt {missing_id.sum()} missing patient_ids")

    # clean names: fix spaces, flip "LAST, First", fix capitals
    df["name"] = df["name"].str.strip().str.replace(r"\s+", " ", regex=True)

    has_comma = df["name"].str.contains(",", na=False)
    parts = df.loc[has_comma, "name"].str.split(",", n=1, expand=True)
    df.loc[has_comma, "name"] = parts[1].str.strip() + " " + parts[0].str.strip()

    df["name"] = df["name"].str.title()


    # clean age: words -> numbers, impossible values -> missing
    df["age"] = df["age"].replace({"twenty": "20"})
    df["age"] = pd.to_numeric(df["age"], errors="coerce")

    valid_before = df["age"].notna().sum()
    df["age"] = df["age"].where(df["age"].between(0, 120))
    # print(f"Set {valid_before - df['age'].notna().sum()} impossible ages to missing")

    df["age"] = df["age"].astype("Int64")


    # clean gender: standardize labels, treat "Unknown" as missing
    gender_map = {
        "male": "Male",
        "m": "Male",
        "female": "Female",
        "f": "Female",
    }
    df["gender"] = df["gender"].str.strip().str.lower().map(gender_map)


    # clean city: fix typos and abbreviations
    city_map = {
        "chicago": "Chicago",
        "boston": "Boston",
        "ny": "New York",
        "new york": "New York",
        "nwe yrok": "New York",
        "newyork": "New York",
        "la": "Los Angeles",
        "los angeles": "Los Angeles",
    }
    city_clean = df["city"].str.strip().str.lower().map(city_map)
    unrecognized = df["city"].notna() & city_clean.isna()
    assert unrecognized.sum() == 0, "unknown city spelling found"
    df["city"] = city_clean


    # clean bmi: remove units, keep realistic values only
    df["bmi"] = pd.to_numeric(df["bmi"].str.extract(r"(\d+\.?\d*)")[0], errors="coerce")

    bmi_before = df["bmi"].notna().sum()
    df["bmi"] = df["bmi"].where(df["bmi"].between(10, 60))
    # print(f"Set {bmi_before - df['bmi'].notna().sum()} unrealistic BMI values to missing")


    # clean blood pressure: split "120/80", "120 over 80", "120 - 80" into two numeric columns
    bp = df["blood_pressure"].str.extract(r"(\d+)\D+(\d+)")
    df["systolic"] = pd.to_numeric(bp[0], errors="coerce")
    df["diastolic"] = pd.to_numeric(bp[1], errors="coerce")

    # keep only plausible readings: systolic must be higher than diastolic
    plausible = (
        df["systolic"].between(70, 250)
        & df["diastolic"].between(40, 150)
        & (df["systolic"] > df["diastolic"])
    )
    invalid = df["systolic"].notna() & ~plausible
    # print(f"Set {invalid.sum()} implausible blood pressure readings to missing")
    df.loc[~plausible, ["systolic", "diastolic"]] = None
    df = df.drop(columns=["blood_pressure"])


    # clean heart rate: words -> numbers, impossible values -> missing
    df["heart_rate"] = df["heart_rate"].replace({"eighty": "80"})
    df["heart_rate"] = pd.to_numeric(df["heart_rate"], errors="coerce")

    hr_before = df["heart_rate"].notna().sum()
    df["heart_rate"] = df["heart_rate"].where(df["heart_rate"].between(30, 220))
    # print(f"Set {hr_before - df['heart_rate'].notna().sum()} impossible heart rates to missing")

    df["heart_rate"] = df["heart_rate"].astype("Int64")


    # clean cholesterol: numbers -> category (standard mg/dL thresholds), keep words
    chol = df["cholesterol_level"].str.strip().str.lower()
    chol_num = pd.to_numeric(chol, errors="coerce")

    # standard cut-offs: <200 normal, 200-239 borderline, 240+ high
    by_number = pd.cut(
        chol_num,
        bins=[0, 200, 240, 1000],
        labels=["normal", "borderline", "high"],
        right=False,
    )
    df["cholesterol_category"] = by_number.astype("object").fillna(
        chol.where(chol.isin(["normal", "high"]))
    )
    df = df.drop(columns=["cholesterol_level"])

    # clean diabetic: standardize yes/no, treat "Unknown" as missing
    diabetic_map = {
        "yes": "Yes",
        "y": "Yes",
        "no": "No",
        "n": "No",
    }
    df["diabetic"] = df["diabetic"].str.strip().str.lower().map(diabetic_map)

    # clean smoker: current / never / former
    smoker_map = {
        "yes": "Yes",
        "no": "No",
        "former": "Former",
        "ex-smoker": "Former",
    }
    df["smoker"] = df["smoker"].str.strip().str.lower().map(smoker_map)


    # clean medications: split on , ; /, standardize names, sort, rejoin
    def join_drugs(drugs):
        if not isinstance(drugs, list):
            return None
        names = sorted({d.strip().title() for d in drugs if d.strip()})
        return ", ".join(names)

    df["medications"] = df["medications"].str.split(r"[,;/]", regex=True).apply(join_drugs)


    # clean last_visit_date: try each known format, then store as real dates
    raw_dates = df["last_visit_date"].str.strip()
    formats = ["%b %d %Y", "%Y%m%d", "%Y-%m-%d", "%d/%m/%Y"]

    parsed = pd.Series(pd.NaT, index=df.index, dtype="datetime64[ns]")
    for fmt in formats:
        parsed = parsed.fillna(pd.to_datetime(raw_dates, format=fmt, errors="coerce"))

    # print(f"Could not read {parsed.isna().sum()} visit dates")
    df["last_visit_date"] = parsed


    # clean follow_up: "two weeks" -> 14, store as whole days, clearer name
    df["follow_up"] = df["follow_up"].str.strip().str.lower().replace({"two weeks": "14"})
    df["follow_up"] = pd.to_numeric(df["follow_up"], errors="coerce").astype("Int64")
    df = df.rename(columns={"follow_up": "follow_up_days"})


    # clean diagnosis_code: "unknown" -> missing, keep real codes
    df["diagnosis_code"] = df["diagnosis_code"].str.strip().where(
        lambda s: s.str.lower() != "unknown"
    )


    # clean notes: remove emoji and stray spaces
    df["notes"] = df["notes"].str.replace(r"[^\x00-\x7F]+", "", regex=True).str.strip()


    # clean has_disease: 0/1 flag, "unknown" and blanks -> missing
    df["has_disease"] = pd.to_numeric(
        df["has_disease"].str.strip().where(lambda s: s.str.lower() != "unknown"),
        errors="coerce",
    ).astype("Int64")


    # fill blanks in text columns; numbers stay blank
    text_fill = {
        "gender": "Unknown",
        "city": "Unknown",
        "diabetic": "Unknown",
        "smoker": "Unknown",
        "diagnosis_code": "Unknown",
        "cholesterol_category": "Unknown",
        "medications": "Unknown",
        "notes": "No note",
    }
    df = df.fillna(text_fill)


    # safety checks
    assert df["patient_id"].notna().all()
    assert df["patient_id"].is_unique

    return df


def load(df):
    # save a CSV copy so you can check the result in Excel
    PROCESSED_DIR.mkdir(parents=True, exist_ok=True)
    df.to_csv(PROCESSED_DIR / "clean_patients.csv", index=False)
    print("Saved cleaned data to data/processed/clean_patients.csv")

    # write the table into PostgreSQL
    load_dotenv()
    user = os.getenv("DB_USER")
    password = quote_plus(os.getenv("DB_PASSWORD"))
    host = os.getenv("DB_HOST")
    port = os.getenv("DB_PORT")
    name = os.getenv("DB_NAME")

    url = f"postgresql+psycopg2://{user}:{password}@{host}:{port}/{name}"
    engine = create_engine(url)
    df.to_sql(TABLE_NAME, engine, if_exists="replace", index=False)
    print(f"Loaded {len(df)} rows into table '{TABLE_NAME}'")

if __name__ == "__main__":
    extract()
    raw = pd.read_csv(RAW_FILE)
    clean = transform(raw)
    load(clean)
