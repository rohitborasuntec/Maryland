import pandas as pd
import ast
import re




def save_csv(df,file_path):
    df.to_csv(file_path, index=False)
    print("File has been saved")


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
    value = str(value)
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
def clean_list_items(raw_list):
    """
    Clean a list of strings by removing brackets, empty strings,
    and stripping whitespace. Returns a flat list of non-empty strings.
    """
    cleaned = []
    for item in raw_list:
        item = str(item).strip()
        # Remove all bracket characters
        item = item.replace("[", "").replace("]", "").strip()
        if item:
            cleaned.append(item)
    return cleaned


def process_rows(results, file_path):
    df = pd.DataFrame(results)

    # ================================================================
    # Pre-create all Personal Rep / Attorney columns as object (string)
    # dtype BEFORE the loop. Otherwise pandas may create them as
    # float64 (all-NaN) and then reject string values later.
    # ================================================================
    MAX_REPS = 5
    MAX_ATTORNEYS = 5

    for k in range(1, MAX_REPS + 1):
        for field in ["First_Name", "Last_Name", "Address", "City", "State", "Pincode"]:
            col = f"Personal Rep_{k}_{field}"
            if col not in df.columns:
                df[col] = pd.Series([""] * len(df), dtype="object")
            else:
                df[col] = df[col].astype("object")

    for k in range(1, MAX_ATTORNEYS + 1):
        for field in ["First_Name", "Last_Name", "Address", "City", "State", "Pincode"]:
            col = f"Attorney_{k}_{field}"
            if col not in df.columns:
                df[col] = pd.Series([""] * len(df), dtype="object")
            else:
                df[col] = df[col].astype("object")

    for index, row in df.iterrows():

        if row["Status"] != "OPEN":
            continue

        print(f"Processing row: {index}")

        pro_date = str(row.get("Date of Probate", "")).replace("Aliases:", "").strip()
        df.at[index, "Date of Probate"] = pro_date

        # ============================================================
        # PERSONAL REPRESENTATIVES
        # ============================================================
        prep_reps_raw = safe_literal_eval(row.get("Personal Reps", ""))
        prep_reps = clean_list_items(prep_reps_raw)

        print("Personal Reps (cleaned):", prep_reps)

        j = 0
        i = 0

        while i < len(prep_reps):

            if i + 1 >= len(prep_reps):
                break

            name = prep_reps[i].strip()
            address_string = prep_reps[i + 1].strip()

            first_name, last_name = parse_name(name)

            if first_name == "Add":
                # Name slot is actually an address; shift by 1
                address_string = name
                first_name = ""
                last_name = ""
                address, city, state, pincode = parse_address(address_string)

                j += 1
                if j > MAX_REPS:
                    break

                df.at[index, f"Personal Rep_{j}_First_Name"] = first_name
                df.at[index, f"Personal Rep_{j}_Last_Name"]  = last_name
                df.at[index, f"Personal Rep_{j}_Address"]    = address
                df.at[index, f"Personal Rep_{j}_City"]       = city
                df.at[index, f"Personal Rep_{j}_State"]      = state
                df.at[index, f"Personal Rep_{j}_Pincode"]    = pincode

                i += 1
                continue

            address, city, state, pincode = parse_address(address_string)

            j += 1
            if j > MAX_REPS:
                break

            df.at[index, f"Personal Rep_{j}_First_Name"] = first_name
            df.at[index, f"Personal Rep_{j}_Last_Name"]  = last_name
            df.at[index, f"Personal Rep_{j}_Address"]    = address
            df.at[index, f"Personal Rep_{j}_City"]       = city
            df.at[index, f"Personal Rep_{j}_State"]      = state
            df.at[index, f"Personal Rep_{j}_Pincode"]    = pincode

            i += 2

        # ============================================================
        # ATTORNEY
        # ============================================================
        attorney_raw = safe_literal_eval(row.get("Attorney", ""))
        attorney_clean = clean_list_items(attorney_raw)

        print("Attorney Clean:", attorney_clean)

        j = 0
        i = 0

        while i < len(attorney_clean):

            if i + 1 >= len(attorney_clean):
                break

            full_name = attorney_clean[i]
            address_string = attorney_clean[i + 1]

            first_name, last_name = parse_name(full_name)

            if first_name == "Add":
                address_string = full_name
                first_name = ""
                last_name = ""
                address, city, state, pincode = parse_address(address_string)

                j += 1
                if j > MAX_ATTORNEYS:
                    break

                df.at[index, f"Attorney_{j}_First_Name"] = first_name
                df.at[index, f"Attorney_{j}_Last_Name"]  = last_name
                df.at[index, f"Attorney_{j}_Address"]    = address
                df.at[index, f"Attorney_{j}_City"]       = city
                df.at[index, f"Attorney_{j}_State"]      = state
                df.at[index, f"Attorney_{j}_Pincode"]    = pincode

                i += 1
                continue

            address, city, state, pincode = parse_address(address_string)

            j += 1
            if j > MAX_ATTORNEYS:
                break

            df.at[index, f"Attorney_{j}_First_Name"] = first_name
            df.at[index, f"Attorney_{j}_Last_Name"]  = last_name
            df.at[index, f"Attorney_{j}_Address"]    = address
            df.at[index, f"Attorney_{j}_City"]       = city
            df.at[index, f"Attorney_{j}_State"]      = state
            df.at[index, f"Attorney_{j}_Pincode"]    = pincode

            i += 2

    save_csv(df, file_path)
# def process_rows(results,file_path):
#     try:
#         df = pd.DataFrame(results)
#     except:
#         pass
    
#     for index, row in df.iterrows():

#         # Only process OPEN records
#         # if str(row.get("Status", "")).strip().upper() != "OPEN":
#         #     continue
#         if row["Status"]!="OPEN":
#             continue

#         print(f"Processing row: {index}")

#         # FIX: cast to str first so NaN/blank cells don't crash .replace()
#         pro_date = str(row.get("Date of Probate", "")).replace("Aliases:", "").strip()
#         df.at[index, "Date of Probate"] = pro_date

#         # ============================================================
#         # PERSONAL REPRESENTATIVES
#         # ============================================================
#         prep_reps = safe_literal_eval(row.get("Personal Reps", ""))

#         print("Personal Reps:", prep_reps)

#         j = 0
#         i = 0

#         while i < len(prep_reps):

#             # Need both name and address
#             if i + 1 >= len(prep_reps):
#                 break

#             name = str(prep_reps[i]).strip()
#             address_string = str(prep_reps[i + 1]).strip()

#             first_name, last_name = parse_name(name)
#             if first_name == "Add":
#                 address_string = name
#                 first_name = ""

#             address, city, state, pincode = parse_address(address_string)

#             j += 1

#             df.at[index, f"Personal Rep_{j}_First_Name"] = first_name
#             df.at[index, f"Personal Rep_{j}_Last_Name"] = last_name
#             df.at[index, f"Personal Rep_{j}_Address"] = address
#             df.at[index, f"Personal Rep_{j}_City"] = city
#             df.at[index, f"Personal Rep_{j}_State"] = state
#             df.at[index, f"Personal Rep_{j}_Pincode"] = pincode

#             # Name + Address = 2 items
#             i += 2

#         attorney = safe_literal_eval(row.get("Attorney", ""))

#         # Clean attorney data
#         attorney_clean = []


#         for item in attorney:

#             item = str(item).strip()

#             # Remove [, ], etc.
#             item = item.replace("[", "").replace("]", "").strip()

#             if item:
#                 attorney_clean.append(item)

#         print("Attorney Clean:", attorney_clean)

#         # ============================================================
#         # ATTORNEY = NAME + ADDRESS
#         # ============================================================

#         j = 0
#         i = 0

#         while i < len(attorney_clean):

#             # We need NAME + ADDRESS
#             if i + 1 >= len(attorney_clean):
#                 break

#             full_name = attorney_clean[i]
#             address_string = attorney_clean[i + 1]

#             # --------------------------------------------------------
#             # NAME
#             # --------------------------------------------------------

#             first_name, last_name = parse_name(full_name)

#             # FIX: was referencing undefined/stale `name` from the Personal Reps
#             # loop above; should reference `full_name`, the attorney's own name.
#             if first_name == "Add":
#                 address_string = full_name

#             # Remove suffix from last name
#             suffixes = {
#                 "JR", "JR.",
#                 "SR", "SR.",
#                 "II", "III", "IV", "V"
#             }

#             # if last_name.upper() in suffixes:
#             #     if len(name_parts) >= 3:
#             #         last_name = name_parts[-2]

#             # --------------------------------------------------------
#             # ADDRESS
#             # --------------------------------------------------------

#             address, city, state, pincode = parse_address(address_string)

#             # --------------------------------------------------------
#             # WRITE TO DATAFRAME
#             # --------------------------------------------------------

#             j += 1

#             df.at[index, f"Attorney_{j}_First_Name"] = first_name
#             df.at[index, f"Attorney_{j}_Last_Name"] = last_name
#             df.at[index, f"Attorney_{j}_Address"] = address
#             df.at[index, f"Attorney_{j}_City"] = city
#             df.at[index, f"Attorney_{j}_State"] = state
#             df.at[index, f"Attorney_{j}_Pincode"] = pincode

#             # NAME + ADDRESS
#             i += 2

#     save_csv(df,file_path)
# # ================================================================
# SAVE ONLY ONCE AFTER ALL ROWS ARE PROCESSED (already outside the loop)
# ================================================================

if __name__ == "__main__":
    INPUT_FILE = r'Output/Complete_data_maryland_final_20260910_140538__.csv'
    OUTPUT_FILE = r'Output/Complete_data_maryland_final_20260910_140538__.csv'

    df = pd.read_csv(INPUT_FILE)
    
    process_rows(df,OUTPUT_FILE)

    print(f"\nDone!")
    print(f"Output saved to: {OUTPUT_FILE}")