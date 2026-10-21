# Patient Records ETL: Kaggle API → Pandas → PostgreSQL

A beginner-to-practical ETL pipeline that downloads a messy patient health dataset from Kaggle, cleans it step by step with Pandas, and loads the result into a PostgreSQL database.

The raw data is synthetic, and the names and values are not real patients. The dataset was chosen because it's messy on purpose, which makes it a good practice ground for cleaning.

## Pipeline

```
Kaggle API → data/raw/ (CSV) → Pandas transform() → data/processed/ (CSV) + PostgreSQL table "patients"
```

| Stage | Function | What it does |
|---|---|---|
| Extract | `extract()` | Downloads the dataset with the Kaggle API. Skips the download if the raw file already exists. |
| Transform | `transform()` | Cleans every column: standardizes labels, converts types, removes impossible values, and fills gaps. |
| Load | `load()` | Saves a CSV copy for checking in Excel, then writes the table to PostgreSQL. |

## Results

| | Raw | Cleaned |
|---|---|---|
| Rows | 10,000 | 10,000 |
| Columns | 17 | 18 |
| Patient IDs | 507 missing | 0 missing (rebuilt from row order) |

Blank values in numeric columns are stored as `NULL` in PostgreSQL. Blank values in text columns are stored as `Unknown` or `No note`.

## Cleaning decisions

| Column | Problem in raw data | What was done | Result |
|---|---|---|---|
| `patient_id` | 507 blank IDs | Verified that all 9,493 existing IDs matched their row position, then rebuilt the missing ones in the same `ID-1` format | 10,000 unique IDs |
| `name` | 5 names, each written differently (spacing, capitals, "Last, First") | Trimmed spaces, flipped "Last, First" to "First Last", applied title case | 5 clean names |
| `age` | Words (`twenty`), impossible values (`-5`, `250`) | Converted words to numbers. Kept ages 0 to 120, set everything else to blank. Not averaged or filled. | 5,044 valid, 4,956 blank |
| `gender` | Six spellings (`M`, `male`, `FEMALE`, `Unknown`...) | Mapped to Male and Female. `Unknown` and blanks treated as missing. | Male 3,310, Female 3,264, Unknown 3,426 |
| `city` | Ten spellings of four cities (`NY`, `Nwe Yrok`, `la`...) | Mapped to four standard names. An assert stops the run if an unknown spelling appears. | New York 4,014, Chicago 2,019, Los Angeles 1,941, Boston 1,023, Unknown 1,003 |
| `bmi` | Units attached (`22kg/m2`) | Extracted the number, kept values from 10 to 60 | 7,582 valid, 2,418 blank |
| `blood_pressure` | Three formats (`120/80`, `120 over 80`, `120 - 80`) | Split into `systolic` and `diastolic`. Dropped readings where the systolic wasn't higher than the diastolic or the values were out of range. | 7,912 valid, 2,088 blank, 58 implausible removed |
| `heart_rate` | Word (`eighty`), placeholders (`0`, `500`) | Converted the word, kept values from 30 to 220 | 5,033 valid, 4,967 blank |
| `cholesterol_level` | Numbers and words mixed | Numbers converted to categories using standard mg/dL cut-offs (under 200 normal, 200 to 239 borderline, 240 or more high). Words kept. Renamed `cholesterol_category`. | normal 4,042, high 3,906, Unknown 2,052 |
| `diabetic` | Six spellings | Mapped to Yes and No, `Unknown` treated as missing | Yes 3,327, No 3,372, Unknown 3,301 |
| `smoker` | `yes`, `No`, `EX-smoker`, `Former` | Mapped to Yes, No, and Former. Former smokers kept separate from current smokers. | Yes 1,646, No 1,663, Former 3,457, Unknown 3,234 |
| `medications` | Same drugs in different separators and orders | Split on commas, semicolons and slashes, standardized names, sorted, rejoined | Aspirin, Metformin 3,965; Lisinopril, Metformin 2,011; Unknown 4,024 |
| `last_visit_date` | Four date formats in one column | Tried each known format in turn. Verified slash dates are day-first (DD/MM/YYYY) in every row. Stored as real dates. | 10,000 dates, 2020-01-01 to 2025-10-01 |
| `follow_up` | Words (`two weeks`) and numbers | Converted to whole days, renamed `follow_up_days` | 14 days 5,002, 30 days 2,474, blank 2,524 |
| `diagnosis_code` | `unknown` and blanks | Kept the four ICD-10 codes, treated `unknown` as missing | B20, I10, E11.9, A00 for 6,634 rows; Unknown 3,366 |
| `notes` | Emoji on one phrase | Removed the emoji and extra spaces | 3 phrases; blanks labelled `No note` |
| `has_disease` | `0`, `1`, `unknown` | Kept 0 and 1 as whole numbers, `unknown` treated as missing | 0 for 2,513; 1 for 2,461; blank 5,026 |

## Data quality findings

These patterns are in the source data. The cleaning code makes the data usable, but it can't make the underlying values realistic.

- **Placeholder values.** Several columns contain a value repeated far more often than any real measurement would be. BMI is dominated by a single default around 22: 22.5 appears 2,610 times, and 2,467 raw entries read “22kg/m2”, which becomes 22.0 after the unit is removed. Blood pressure shows 120/80 about 6,000 times across its three formats. About half of the valid heart rates (2,459 of 5,033) came from the word “eighty”, which became 80. These look like defaults filled in by the dataset generator.
- **Fake extremes.** Ages of -5 and 250 appear about 2,500 times each. Heart rates of 0 and 500 appear about 2,500 times each. They were removed, not corrected.
- **Cholesterol values.** Only two numeric values exist (190 and 250), so the category column has no borderline entries.
- **Inconsistent records.** Diagnosis codes and medications don't match each other clinically. For example, a patient can have a cholera code (A00) and be on metformin. This data should be used to practise pipelines, not to draw medical conclusions.
- **Impossible combinations.** Some records show ages of 16 with occupations like "Retired", which the dataset doesn't check.
- **Missingness.** Missing values are common across most columns (up to about half of some). Each column's blanks were handled separately, so the counts above describe what was missing, not what was true.

## Project structure

```
ETL/
├── etl.py              # the pipeline: extract, transform, load
├── requirements.txt    # libraries and exact versions
├── .gitignore          # keeps secrets and large files out of Git
├── .env                # database password (not in Git)
├── data/
│   ├── raw/            # downloaded CSV (not in Git)
│   └── processed/      # cleaned CSV (not in Git)
└── venv/               # virtual environment (not in Git)
```

## Setup and run

**Requirements:** Python 3.10 or newer, PostgreSQL 16 or newer, and a Kaggle account.

1. **Clone the repo and create a virtual environment**

```bash
   git clone https://github.com/hafsamaryam08/patient-records-etl-postgres.git
   cd patient-records-etl-postgres
   python -m venv venv
   venv\Scripts\activate        # Windows
   source venv/bin/activate     # Mac/Linux
   pip install -r requirements.txt
```

2. **Add Kaggle credentials.** Create an API token at kaggle.com under Settings → API, then save it to `~/.kaggle/kaggle.json` (or `access_token` in the same folder, depending on the token type Kaggle gives you).

3. **Create the database.** In pgAdmin or psql, create a database called `patients_etl`.

4. **Create a `.env` file** in the project root:

```
   DB_USER=postgres
   DB_PASSWORD=your_password
   DB_HOST=localhost
   DB_PORT=5432
   DB_NAME=patients_etl
```

5. **Run the pipeline**

```bash
   python etl.py
```

   Expected output:

```
   Saved cleaned data to data/processed/clean_patients.csv
   Loaded 10000 rows into table 'patients'
```

6. **Check the result**

```sql
   SELECT COUNT(*) FROM patients;
```

   Should return `10000`.

## Design choices

- **Blanks stay blank in numeric columns.** Filling an age or a heart rate with an average would invent data and distort any later analysis.
- **Unknown is labelled in text columns.** A category that says `Unknown` is more honest than a blank, and it stays visible in counts.
- **Raw data is never edited.** Cleaning happens in memory, and the raw CSV is kept as the source of truth.
- **Safe to re-run.** Extraction skips the download if the raw file exists, and loading replaces the table rather than appending to it.
- **Checks fail loudly.** The pipeline stops if an ID is missing or repeated, or if a city spelling isn't recognized.

## Next improvements

- Schedule the pipeline with Apache Airflow so it runs daily.
- Load incrementally, so only new or changed rows are written.
- Add automated tests with pytest for each cleaning function.
- Move the database into Docker Compose so the setup works on any machine.
- Add a data quality report that counts rule violations on every run.

## What I learned

- How to rebuild missing identifiers from a verified pattern instead of inventing them.
- Why each cleaning rule should be checked against the data before it's written.
- How to keep credentials out of source control with `.env` and `.gitignore`.
- Why the same messy column can need a different fix depending on what the value means.
