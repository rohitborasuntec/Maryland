import pandas as pd
import ast
import re


INPUT_FILE = r'/home/suntec/Downloads/New folder/inside/Concatenated_Data.csv'
OUTPUT_FILE = 'Output/Modified.csv'


df = pd.read_csv(INPUT_FILE)


def parse_name(full_name):
    """
    Convert:
        JERRY MICHAEL LAFFERTY
    into:
        first_name = JERRY
        last_name = LAFFERTY

    Middle names are ignored.
    """
    full_name = str(full_name).strip()

    # FIX: re.complit -> re.compile, and compare len(list) instead of the list itself
    if len(re.compile(r'(?s)\d+').findall(full_name)) > 0:
        return "Add", ""
    parts = full_name.split()
    if not parts:
        return "", ""
    i = 1
    if "." in parts[0] or len(parts[0]) <= 1:
        i = 2
        first_name = " ".join(parts[:i]).replace("[", "").replace("]", "").strip()
    else:
        first_name = parts[0]

    if len(parts) == 1:
        last_name = ""
    else:
        last_name = " ".join(parts[i:]).replace("[", "").replace("]", "").strip()

    return first_name, last_name


def parse_address(address):

    address = str(address).strip()

    parts = [
        x.strip()
        for x in address.split(",")
        if x.strip()
    ]

    if len(parts) < 3:
        return "", "", "", ""

    # First component = street address
    street_address = parts[0]

    # Last component = STATE ZIP
    state_zip = parts[-1]

    state_zip_parts = state_zip.split()

    state = state_zip_parts[0] if len(state_zip_parts) >= 1 else ""

    zip_code = state_zip_parts[1] if len(state_zip_parts) >= 2 else ""

    # Everything between street and STATE ZIP
    # is considered part of city
    city = ", ".join(parts[1:-1])

    return street_address, city, state, zip_code


def safe_literal_eval(value):
    """
    Safely convert a string representation of a Python list
    into an actual list.
    """

    if pd.isna(value):
        return []

    if isinstance(value, list):
        return value

    try:
        result = ast.literal_eval(str(value))

        if isinstance(result, list):
            return result

        return []

    except (ValueError, SyntaxError):
        return []


for index, row in df.iterrows():

    # Only process OPEN records
    # if str(row.get("Status", "")).strip().upper() != "OPEN":
    #     continue
    if row["Status"]!="OPEN":
        continue

    print(f"Processing row: {index}")

    # FIX: cast to str first so NaN/blank cells don't crash .replace()
    pro_date = str(row.get("Date of Probate", "")).replace("Aliases:", "").strip()
    df.at[index, "Date of Probate"] = pro_date

    # ============================================================
    # PERSONAL REPRESENTATIVES
    # ============================================================

    prep_reps = safe_literal_eval(row.get("Personal Reps", ""))

    print("Personal Reps:", prep_reps)

    # Expected structure:
    #
    # [
    #   "JERRY MICHAEL LAFFERTY",
    #   "735 WARREN DR, ANNAPOLIS, MD 21403-2809",
    #   "MARK ANDREW LAFFERTY",
    #   "45 DENBIGH BLVD, NEWPORT NEWS, VA 23608-3315"
    # ]

    j = 0
    i = 0

    while i < len(prep_reps):

        # Need both name and address
        if i + 1 >= len(prep_reps):
            break

        name = str(prep_reps[i]).strip()
        address_string = str(prep_reps[i + 1]).strip()

        first_name, last_name = parse_name(name)
        if first_name == "Add":
            address_string = name
            first_name = ""

        address, city, state, pincode = parse_address(address_string)

        j += 1

        df.at[index, f"Personal Rep_{j}_First_Name"] = first_name
        df.at[index, f"Personal Rep_{j}_Last_Name"] = last_name
        df.at[index, f"Personal Rep_{j}_Address"] = address
        df.at[index, f"Personal Rep_{j}_City"] = city
        df.at[index, f"Personal Rep_{j}_State"] = state
        df.at[index, f"Personal Rep_{j}_Pincode"] = pincode

        # Name + Address = 2 items
        i += 2

    # ============================================================
    # ATTORNEYS
    # ============================================================

    # IMPORTANT: CSV column is "Attorney", not "Attroney"
    attorney = safe_literal_eval(row.get("Attorney", ""))

    # Clean attorney data
    attorney_clean = []

    for item in attorney:

        item = str(item).strip()

        # Remove [, ], etc.
        item = item.replace("[", "").replace("]", "").strip()

        if item:
            attorney_clean.append(item)

    print("Attorney Clean:", attorney_clean)

    # ============================================================
    # ATTORNEY = NAME + ADDRESS
    # ============================================================

    j = 0
    i = 0

    while i < len(attorney_clean):

        # We need NAME + ADDRESS
        if i + 1 >= len(attorney_clean):
            break

        full_name = attorney_clean[i]
        address_string = attorney_clean[i + 1]

        # --------------------------------------------------------
        # NAME
        # --------------------------------------------------------

        first_name, last_name = parse_name(full_name)

        # FIX: was referencing undefined/stale `name` from the Personal Reps
        # loop above; should reference `full_name`, the attorney's own name.
        if first_name == "Add":
            address_string = full_name

        # Remove suffix from last name
        suffixes = {
            "JR", "JR.",
            "SR", "SR.",
            "II", "III", "IV", "V"
        }

        # if last_name.upper() in suffixes:
        #     if len(name_parts) >= 3:
        #         last_name = name_parts[-2]

        # --------------------------------------------------------
        # ADDRESS
        # --------------------------------------------------------

        address, city, state, pincode = parse_address(address_string)

        # --------------------------------------------------------
        # WRITE TO DATAFRAME
        # --------------------------------------------------------

        j += 1

        df.at[index, f"Attorney_{j}_First_Name"] = first_name
        df.at[index, f"Attorney_{j}_Last_Name"] = last_name
        df.at[index, f"Attorney_{j}_Address"] = address
        df.at[index, f"Attorney_{j}_City"] = city
        df.at[index, f"Attorney_{j}_State"] = state
        df.at[index, f"Attorney_{j}_Pincode"] = pincode

        # NAME + ADDRESS
        i += 2

# ================================================================
# SAVE ONLY ONCE AFTER ALL ROWS ARE PROCESSED (already outside the loop)
# ================================================================
df.to_csv(OUTPUT_FILE, index=False)

print(f"\nDone!")
print(f"Output saved to: {OUTPUT_FILE}")