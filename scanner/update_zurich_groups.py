"""Update parking_group for Zurich and St. Gallen parkhouses based on PLS grouping.
Zurich source: https://www.pls-zh.ch/geb_1.jsp (Oerlikon), geb_2.jsp (Innenstadt), geb_3.jsp (Zuerich-West)
St. Gallen source: https://www.pls-sg.ch (screenshot)
Run once, then delete.
"""
from db_utils import get_connection, load_db_config

ZURICH_GROUPS = {
    "Innenstadt": [
        "Zürichhorn", "Feldegg", "Utoquai", "Opéra", "Park Hyatt",
        "Bleicherweg", "Hohe Promenade", "Talgarten", "Urania", "Jelmoli",
        "Globus", "City Parking", "USZ Süd", "Hauptbahnhof", "Helvetiaplatz",
        "USZ Nord", "Stampfenbach",
    ],
    "Oerlikon": [
        "Uni Irchel", "Dorflinde", "Theater 11", "Züri 11 Shopping",
        "Nordhaus", "Messe Zürich", "Jungholz", "Center Eleven",
        "Cityport", "Parkside", "Accu", "Max-Bill-Platz", "Octavo",
    ],
    "Zürich-West": [
        "Puls 5", "Pfingstweid", "Hardau II",
        "Albisriederplatz", "P-West", "P West", "Crowne Plaza",
    ],
}

STGALLEN_GROUPS = {
    "Zentrum West": [
        "Neumarkt", "Rathaus", "Manor", "Bahnhof", "Kreuzbleiche",
    ],
    "Klosterviertel": [
        "Oberer Graben", "Raiffeisenzentrum", "Einstein",
    ],
    "Marktplatz": [
        "Burggraben", "Spisertor", "Brühltor",
    ],
    "Zentrum Ost": [
        "Stadtpark", "Spelteriniplatz", "Spelterini",
    ],
    "OLMA": [
        "OLMA",
    ],
}

# Klosterviertel: Raiffeisen = Raiffeisenzentrum
STGALLEN_GROUPS["Klosterviertel"].append("Raiffeisen")


def build_suffix_map(groups):
    """Map lowercase suffix keywords to group names."""
    m = {}
    for group, keywords in groups.items():
        for kw in keywords:
            m[kw.lower()] = group
    return m


def match_group(name, suffix_map):
    """Find group by checking if any keyword appears in the parkhaus name."""
    name_lower = name.lower()
    for suffix, group in suffix_map.items():
        if suffix in name_lower:
            return group
    return None


def update_groups(city_id, suffix_map, conn=None):
    own_conn = conn is None
    if own_conn:
        conn = get_connection()
    cur = conn.cursor()

    cur.execute("""
        SELECT p.id, p.name, p.parking_group
        FROM parkhaeuser p
        JOIN cities c ON c.id = p.city_id
        WHERE c.id = %s AND p.is_active = 1
    """, (city_id,))
    rows = cur.fetchall()

    updated = 0
    missing = []
    for pid, name, current_group in rows:
        target = match_group(name, suffix_map)
        if target is None:
            missing.append(name)
            continue
        if current_group != target:
            cur.execute(
                "UPDATE parkhaeuser SET parking_group = %s WHERE id = %s",
                (target, pid),
            )
            print(f"  {name}: '{current_group}' -> '{target}'")
            updated += 1
        else:
            print(f"  {name}: already '{target}'")

    if missing:
        print(f"\n  No group mapping for: {missing}")

    conn.commit()
    if own_conn:
        conn.close()
    total = len(rows)
    print(f"  {updated} updated, {total - updated - len(missing)} unchanged, {len(missing)} unmapped")


if __name__ == "__main__":
    import mysql.connector
    config = load_db_config()
    dbs = ["ph_fetch_test", "ph_fetch_prod"]
    zh_map = build_suffix_map(ZURICH_GROUPS)
    sg_map = build_suffix_map(STGALLEN_GROUPS)
    for db in dbs:
        print(f"\n{'='*40}\nDatabase: {db}\n{'='*40}")
        config['database'] = db
        conn = mysql.connector.connect(**config)
        print("=== ZÜRICH ===")
        update_groups("zurich", zh_map, conn)
        print("\n=== ST. GALLEN ===")
        update_groups("stgallen", sg_map, conn)
        conn.close()
