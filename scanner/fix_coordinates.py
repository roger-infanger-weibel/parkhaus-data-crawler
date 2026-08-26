"""Update all parking garage coordinates from verified sources.
Sources: Basel open data (data.bs.ch/100044), Bern web research,
Luzern address verification, St. Gallen open data (daten.stadt.sg.ch),
Zürich PLS + address lookup.
Run once on both ph_fetch_test and ph_fetch_prod, then delete.
"""
import mysql.connector
from db_utils import load_db_config

DATABASES = ["ph_fetch_test", "ph_fetch_prod"]

# All coordinates verified from official open data portals and address lookups
COORDS = {
    # === BASEL (source: data.bs.ch dataset 100044) ===
    "Basel Parkhaus Aeschen": (47.5504, 7.5943),
    "Basel Parkhaus Anfos": (47.5516, 7.5935),
    "Basel Parkhaus Bad Bahnhof": (47.5652, 7.6089),
    "Basel Parkhaus Bahnhof Süd": (47.5459, 7.5885),
    "Basel Parkhaus Centralbahn": (47.5473, 7.5923),
    "Basel Parkhaus City": (47.5611, 7.5824),
    "Basel Parkhaus Clarahuus": (47.5623, 7.5918),
    "Basel Parkhaus Claramatte": (47.5640, 7.5947),
    "Basel Parkhaus Elisabethen": (47.5506, 7.5875),
    "Basel Parkhaus Europe": (47.5630, 7.5967),
    "Basel Parkhaus Kunstmuseum": (47.5545, 7.5927),
    "Basel Parkhaus Messe": (47.5632, 7.6022),
    "Basel Parkhaus Post Basel": (47.5469, 7.5929),
    "Basel Parkhaus Rebgasse": (47.5607, 7.5943),
    "Basel Parkhaus Steinen": (47.5525, 7.5859),
    "Basel Parkhaus Storchen": (47.5592, 7.5866),

    # === BERN (source: address verification) ===
    "Bern Park + Ride Neufeld": (46.9640, 7.4313),
    "Bern Parkhaus Bahnhof": (46.9499, 7.4378),
    "Bern Parkhaus Casino": (46.9468, 7.4473),
    "Bern Parkhaus City West": (46.9463, 7.4340),
    "Bern Parkhaus Expo": (46.9569, 7.4683),
    "Bern Parkhaus Kursaal": (46.9528, 7.4482),
    "Bern Parkhaus Metro": (46.9500, 7.4449),
    "Bern Parkhaus Mobiliar": (46.9468, 7.4441),
    "Bern Parkhaus Rathaus": (46.9491, 7.4527),
    "Bern Parkhaus Zentrum": (46.9490, 7.4744),
    "Bern SBB Kurzparking": (46.9488, 7.4391),

    # === LUZERN (source: address verification + Google Maps) ===
    "Luzern Parkhaus Kantonalbank": (47.0472, 8.3077),
    "Luzern Parkhaus Altstadt": (47.0520, 8.2992),
    "Luzern Parkhaus Bahnhof": (47.0502, 8.3100),
    "Luzern Parkhaus Bahnhofparking P1+P2": (47.0506, 8.3113),
    "Luzern Parkhaus Bahnhofparking P3": (47.0498, 8.3135),
    "Luzern Parkhaus Casino-Palace": (47.0550, 8.3170),
    "Luzern Parkhaus City Parking": (47.0579, 8.3097),
    "Luzern Parkhaus Flora": (47.0501, 8.3077),
    "Luzern Parkhaus Hirzenmatt": (47.0470, 8.3068),
    "Luzern Parkhaus Kesselturm": (47.0498, 8.3024),
    "Luzern Parkhaus Nationalhof": (47.0554, 8.3153),
    "Luzern Parkhaus Schweizerhof": (47.0543, 8.3102),

    # === ST. GALLEN (source: daten.stadt.sg.ch open data API) ===
    "St. Gallen Parkhaus Bahnhof": (47.4228, 9.3671),
    "St. Gallen Parkhaus Oberer Graben": (47.4222, 9.3746),
    "St. Gallen Parkhaus Spisertor": (47.4240, 9.3793),
    "St. Gallen Parkhaus Rathaus": (47.4245, 9.3712),
    "St. Gallen Parkhaus Manor": (47.4238, 9.3727),
    "St. Gallen Parkhaus Neumarkt": (47.4218, 9.3709),
    "St. Gallen Parkhaus Kreuzbleiche": (47.4202, 9.3624),
    "St. Gallen Parkhaus Einstein": (47.4218, 9.3742),
    "St. Gallen Parkhaus Central": (47.4283, 9.3752),
    "St. Gallen Parkhaus Burggraben": (47.4254, 9.3793),
    "St. Gallen Parkhaus Stadtpark": (47.4293, 9.3805),
    "St. Gallen Parkhaus Stadtpark AZSG": (47.4302, 9.3848),
    "St. Gallen Parkhaus Spelterini": (47.4293, 9.3805),
    "St. Gallen Parkhaus OLMA Messen": (47.4323, 9.3672),
    "St. Gallen Parkhaus OLMA Parkplatz": (47.4310, 9.3837),
    "St. Gallen Parkhaus Raiffeisen": (47.4208, 9.3723),

    # === ZÜRICH (source: PLS + address lookup) ===
    "Zuerich Parkhaus Park Hyatt": (47.3650, 8.5365),
    "Zürich Parkhaus Accu": (47.4115, 8.5420),
    "Zürich Parkhaus Albisriederplatz": (47.3794, 8.5082),
    "Zürich Parkhaus Bleicherweg": (47.3669, 8.5358),
    "Zürich Parkhaus Center Eleven": (47.4103, 8.5552),
    "Zürich Parkhaus City Parking": (47.3756, 8.5353),
    "Zürich Parkhaus Cityport": (47.4120, 8.5434),
    "Zürich Parkhaus Crowne Plaza": (47.3732, 8.5034),
    "Zürich Parkhaus Dorflinde": (47.4078, 8.5488),
    "Zürich Parkhaus Feldegg": (47.3604, 8.5537),
    "Zürich Parkhaus Globus": (47.3762, 8.5381),
    "Zürich Parkhaus Hardau II": (47.3815, 8.5095),
    "Zürich Parkhaus Hauptbahnhof": (47.3780, 8.5400),
    "Zürich Parkhaus Helvetiaplatz": (47.3742, 8.5268),
    "Zürich Parkhaus Hohe Promenade": (47.3698, 8.5475),
    "Zürich Parkhaus Jelmoli": (47.3739, 8.5372),
    "Zürich Parkhaus Jungholz": (47.4101, 8.5463),
    "Zürich Parkhaus Messe Zürich": (47.4111, 8.5512),
    "Zürich Parkhaus Nordhaus": (47.4087, 8.5482),
    "Zürich Parkhaus Octavo": (47.4109, 8.5451),
    "Zürich Parkhaus Opéra": (47.3653, 8.5463),
    "Zürich Parkhaus P-West": (47.3915, 8.5103),
    "Zürich Parkhaus Parkside": (47.4082, 8.5448),
    "Zürich Parkhaus Pfingstweid": (47.3879, 8.5173),
    "Zürich Parkhaus Stampfenbach": (47.3814, 8.5432),
    "Zürich Parkhaus Talgarten": (47.3725, 8.5378),
    "Zürich Parkhaus Uni Irchel": (47.3965, 8.5492),
    "Zürich Parkhaus Urania": (47.3744, 8.5392),
    "Zürich Parkhaus USZ Nord": (47.3790, 8.5510),
    "Zürich Parkhaus Utoquai": (47.3640, 8.5500),
    "Zürich Parkhaus Zürichhorn": (47.3550, 8.5550),
    "Zürich Parkhaus Züri 11 Shopping": (47.4000, 8.5360),
    "Zürich Parkplatz Max-Bill-Platz": (47.4142, 8.5389),
    "Zürich Parkplatz Theater 11": (47.4101, 8.5493),
    "Zürich Parkplatz USZ Süd": (47.3780, 8.5520),
    "Zürich Puls 5 Parkgarage": (47.3875, 8.5195),
}

# Luzern: match DB names with Umlauts
UMLAUT_ALIASES = {
    "Luzern Parkhaus am Gütsch": "Luzern Parking am Guetsch",
    "Luzern Parkhaus Löwen-Center": "Luzern Parkhaus Loewen-Center",
    "Luzern Parkhaus Sportgebäude": "Luzern Parkhaus Sportgebaeude",
    "Luzern Parking Stadt Theater": "Luzern Parking Stadt Theater",
    "St. Gallen Parkhaus Brühltor": "St. Gallen Parkhaus Bruehltor",
}

# Extra coords for Umlaut names not in main dict
EXTRA = {
    "Luzern Parkhaus am Gütsch": (47.0530, 8.2925),
    "Luzern Parkhaus Löwen-Center": (47.0570, 8.3099),
    "Luzern Parkhaus Sportgebäude": (47.0313, 8.3047),
    "Luzern Parking Stadt Theater": (47.0506, 8.3062),
    "St. Gallen Parkhaus Brühltor": (47.4271, 9.3780),
}
COORDS.update(EXTRA)


def main():
    config = load_db_config()
    for db in DATABASES:
        print(f"\n{'='*60}\nDatabase: {db}\n{'='*60}")
        config['database'] = db
        conn = mysql.connector.connect(**config)
        cur = conn.cursor()

        cur.execute("""
            SELECT p.id, p.name, p.latitude, p.longitude
            FROM parkhaeuser p WHERE p.is_active = 1
            ORDER BY p.name
        """)
        rows = cur.fetchall()

        updated = 0
        skipped = 0
        missing = []

        for pid, name, old_lat, old_lon in rows:
            coords = COORDS.get(name)
            if coords is None:
                missing.append(name)
                continue

            new_lat, new_lon = coords
            if old_lat is not None and old_lon is not None:
                if abs(new_lat - float(old_lat)) < 0.0005 and abs(new_lon - float(old_lon)) < 0.0005:
                    skipped += 1
                    continue

            cur.execute(
                "UPDATE parkhaeuser SET latitude=%s, longitude=%s WHERE id=%s",
                (new_lat, new_lon, pid),
            )
            old_str = f"({old_lat}, {old_lon})" if old_lat else "(NULL)"
            print(f"  {name}: {old_str} -> ({new_lat}, {new_lon})")
            updated += 1

        conn.commit()
        cur.close()
        conn.close()

        if missing:
            print(f"\n  No coords for: {missing}")
        print(f"  {updated} updated, {skipped} unchanged, {len(missing)} missing")


if __name__ == "__main__":
    main()
