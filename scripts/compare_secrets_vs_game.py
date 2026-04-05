"""Compare Group 1 DataTable JSON files from the secrets pak against base game versions.

Checks for: structural differences, missing/added rows, type mismatches,
NameMap differences, Import index issues, and Tags field correctness.
"""

import json
import os
import sys


def get_row_names(data):
    """Extract row names from DataTable JSON."""
    try:
        rows = data['Exports'][0]['Table']['Data']
        return {row.get('Name', f'UNNAMED_{i}'): row for i, row in enumerate(rows)}
    except (KeyError, IndexError, TypeError):
        return {}


def get_namemap(data):
    """Extract NameMap from JSON."""
    return data.get('NameMap', [])


def get_imports(data):
    """Extract Imports from JSON."""
    return data.get('Imports', [])


def compare_row_structure(game_row, secrets_row, row_name):
    """Compare the structure of two rows - field names, types, and values."""
    issues = []
    game_vals = {v.get('Name', f'?{i}'): v for i, v in enumerate(game_row.get('Value', []))}
    secrets_vals = {v.get('Name', f'?{i}'): v for i, v in enumerate(secrets_row.get('Value', []))}

    game_fields = set(game_vals.keys())
    secrets_fields = set(secrets_vals.keys())

    # Fields missing from secrets
    missing = game_fields - secrets_fields
    if missing:
        issues.append(f"MISSING from secrets: {sorted(missing)}")

    # Fields added in secrets
    added = secrets_fields - game_fields
    if added:
        issues.append(f"ADDED in secrets: {sorted(added)}")

    # Type mismatches on shared fields
    for field in sorted(game_fields & secrets_fields):
        g = game_vals[field]
        s = secrets_vals[field]
        g_type = g.get('$type', '')
        s_type = s.get('$type', '')
        if g_type != s_type:
            issues.append(
                f"TYPE MISMATCH '{field}': "
                f"game={g_type.split('.')[-1]} vs secrets={s_type.split('.')[-1]}"
            )

        # Check Value type (string vs array vs dict)
        g_val = g.get('Value')
        s_val = s.get('Value')
        if type(g_val) != type(s_val):
            issues.append(
                f"VALUE TYPE MISMATCH '{field}': "
                f"game={type(g_val).__name__}({str(g_val)[:60]}) vs "
                f"secrets={type(s_val).__name__}({str(s_val)[:60]})"
            )

        # For GameplayTagContainer, check inner structure
        if 'GameplayTagContainer' in g.get('StructType', ''):
            g_inner = g.get('Value', [{}])
            s_inner = s.get('Value', [{}])
            if isinstance(g_inner, list) and isinstance(s_inner, list):
                for gi, si in zip(g_inner, s_inner):
                    gi_val = gi.get('Value')
                    si_val = si.get('Value')
                    if type(gi_val) != type(si_val):
                        issues.append(
                            f"TAG CONTAINER MISMATCH '{field}': "
                            f"game inner={type(gi_val).__name__} vs "
                            f"secrets inner={type(si_val).__name__}"
                        )

    return issues


def check_import_references(data, label):
    """Check for negative import indices that are out of range."""
    imports = get_imports(data)
    issues = []
    try:
        rows = data['Exports'][0]['Table']['Data']
        for row in rows:
            for val in row.get('Value', []):
                vtype = val.get('$type', '')
                v = val.get('Value')
                if 'ObjectProperty' in vtype and isinstance(v, int) and v < -len(imports):
                    issues.append(
                        f"{label} row '{row.get('Name')}' field '{val.get('Name')}': "
                        f"import index {v} out of range (only {len(imports)} imports)"
                    )
    except (KeyError, IndexError, TypeError):
        pass
    return issues


def main():
    appdata = os.environ['APPDATA']
    secrets_json_dir = os.path.join(appdata, 'MoriaMODCreator', 'Secrets Source', 'jsondata')
    game_json_dir = os.path.join(appdata, 'MoriaMODCreator', 'output', 'jsondata')

    group1_files = [
        "Moria/Content/Character/AI/DT_Loot.json",
        "Moria/Content/Tech/Data/Building/DT_ConstructionRecipes.json",
        "Moria/Content/Tech/Data/Building/DT_Constructions.json",
        "Moria/Content/Tech/Data/DT_CategoryTags.json",
        "Moria/Content/Tech/Data/Economy/DT_OfferDecks.json",
        "Moria/Content/Tech/Data/Economy/DT_OfferTemplates.json",
        "Moria/Content/Tech/Data/Economy/DT_RecipeBundles.json",
        "Moria/Content/Tech/Data/GameWorld/DT_Moria_Flora.json",
        "Moria/Content/Tech/Data/Items/DT_Armor.json",
        "Moria/Content/Tech/Data/Items/DT_ItemRecipes.json",
        "Moria/Content/Tech/Data/Items/DT_Items.json",
        "Moria/Content/Tech/Data/Items/DT_Tools.json",
        "Moria/Content/Tech/Data/Items/DT_Weapons.json",
    ]

    print("=" * 80)
    print("SECRETS PAK vs BASE GAME - COMPREHENSIVE COMPARISON")
    print("=" * 80)

    for rel_path in group1_files:
        game_path = os.path.join(game_json_dir, rel_path)
        secrets_path = os.path.join(secrets_json_dir, rel_path)

        filename = os.path.basename(rel_path)
        print(f"\n{'=' * 80}")
        print(f"FILE: {filename}")
        print(f"  Game:    {game_path}")
        print(f"  Secrets: {secrets_path}")
        print(f"{'=' * 80}")

        if not os.path.exists(game_path):
            print("  !! GAME FILE MISSING")
            continue
        if not os.path.exists(secrets_path):
            print("  !! SECRETS FILE MISSING")
            continue

        game_data = json.load(open(game_path, encoding='utf-8'))
        secrets_data = json.load(open(secrets_path, encoding='utf-8'))

        # 1. File size
        game_size = os.path.getsize(game_path)
        secrets_size = os.path.getsize(secrets_path)
        print(f"\n  FILE SIZE: game={game_size:,} bytes, secrets={secrets_size:,} bytes (delta={secrets_size - game_size:+,})")

        # 2. Top-level keys
        game_keys = set(game_data.keys())
        secrets_keys = set(secrets_data.keys())
        if game_keys != secrets_keys:
            print(f"\n  TOP-LEVEL KEY DIFF:")
            if game_keys - secrets_keys:
                print(f"    Game only: {game_keys - secrets_keys}")
            if secrets_keys - game_keys:
                print(f"    Secrets only: {secrets_keys - game_keys}")

        # 3. NameMap
        game_nm = get_namemap(game_data)
        secrets_nm = get_namemap(secrets_data)
        game_nm_set = set(game_nm)
        secrets_nm_set = set(secrets_nm)
        nm_added = secrets_nm_set - game_nm_set
        nm_removed = game_nm_set - secrets_nm_set
        print(f"\n  NAMEMAP: game={len(game_nm)}, secrets={len(secrets_nm)} (added={len(nm_added)}, removed={len(nm_removed)})")
        if nm_removed:
            print(f"    !! REMOVED: {sorted(nm_removed)[:20]}")
        if nm_added and len(nm_added) <= 20:
            print(f"    Added: {sorted(nm_added)}")
        elif nm_added:
            print(f"    Added (first 20 of {len(nm_added)}): {sorted(nm_added)[:20]}")

        # 4. Imports
        game_imports = get_imports(game_data)
        secrets_imports = get_imports(secrets_data)
        print(f"\n  IMPORTS: game={len(game_imports)}, secrets={len(secrets_imports)} (delta={len(secrets_imports) - len(game_imports):+})")

        imp_issues_s = check_import_references(secrets_data, "secrets")
        if imp_issues_s:
            print(f"    !! SECRETS IMPORT INDEX ISSUES ({len(imp_issues_s)}):")
            for iss in imp_issues_s[:10]:
                print(f"      {iss}")

        # 5. Exports
        game_exports = game_data.get('Exports', [])
        secrets_exports = secrets_data.get('Exports', [])
        print(f"\n  EXPORTS: game={len(game_exports)}, secrets={len(secrets_exports)}")
        if len(game_exports) != len(secrets_exports):
            print(f"    !! EXPORT COUNT MISMATCH")

        # 6. DataTable rows
        game_rows = get_row_names(game_data)
        secrets_rows = get_row_names(secrets_data)
        game_row_set = set(game_rows.keys())
        secrets_row_set = set(secrets_rows.keys())

        added_rows = secrets_row_set - game_row_set
        removed_rows = game_row_set - secrets_row_set
        shared_rows = game_row_set & secrets_row_set

        print(f"\n  ROWS: game={len(game_row_set)}, secrets={len(secrets_row_set)}")
        print(f"    Shared: {len(shared_rows)}")
        print(f"    Added in secrets: {len(added_rows)}")
        if added_rows and len(added_rows) <= 30:
            print(f"      {sorted(added_rows)}")
        elif added_rows:
            print(f"      (first 30 of {len(added_rows)}): {sorted(added_rows)[:30]}")
        if removed_rows:
            print(f"    !! REMOVED from secrets: {len(removed_rows)}")
            print(f"      {sorted(removed_rows)}")

        # 7. Structural check on shared rows
        print(f"\n  STRUCTURAL CHECK (shared rows):")
        all_issues = {}
        for rname in sorted(shared_rows):
            issues = compare_row_structure(game_rows[rname], secrets_rows[rname], rname)
            if issues:
                all_issues[rname] = issues

        if all_issues:
            total = sum(len(v) for v in all_issues.values())
            print(f"    !! FOUND {total} ISSUES in {len(all_issues)} rows:")
            for rname, issues in sorted(all_issues.items()):
                print(f"    ROW '{rname}':")
                for iss in issues:
                    print(f"      {iss}")
        else:
            print(f"    OK - All {len(shared_rows)} shared rows have matching structure")

        # 8. Tags field audit
        print(f"\n  TAGS FIELD AUDIT:")
        tag_issues = 0
        for rname, row in secrets_rows.items():
            for val in row.get('Value', []):
                if val.get('Name') == 'Tags' and 'GameplayTagContainer' in val.get('StructType', ''):
                    for inner in val.get('Value', []):
                        if inner.get('Name') == 'Tags':
                            iv = inner.get('Value')
                            if isinstance(iv, str):
                                print(f"    !! STRING instead of ARRAY: row='{rname}' value='{iv}'")
                                tag_issues += 1
                            elif isinstance(iv, list):
                                for item in iv:
                                    if not isinstance(item, str):
                                        print(f"    !! NON-STRING in tag array: row='{rname}' type={type(item).__name__}")
                                        tag_issues += 1
                # Also check RequiredTags
                if val.get('Name') == 'RequiredTags' and 'GameplayTagContainer' in val.get('StructType', ''):
                    for inner in val.get('Value', []):
                        if inner.get('Name') in ('Tags', 'RequiredTags'):
                            iv = inner.get('Value')
                            if isinstance(iv, str):
                                print(f"    !! RequiredTags STRING instead of ARRAY: row='{rname}' value='{iv}'")
                                tag_issues += 1
        if tag_issues == 0:
            print(f"    OK - All Tags/RequiredTags fields are correctly typed")

    print(f"\n{'=' * 80}")
    print("COMPARISON COMPLETE")
    print(f"{'=' * 80}")


if __name__ == '__main__':
    main()
