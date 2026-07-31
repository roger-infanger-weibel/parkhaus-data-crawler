"""Die aktiven Modelldateien zum Kopieren auf den Server bereitlegen.

Nach einem Training auf dem PC stehen die Modelle zwar in der Datenbank als
aktiv, die zugehoerigen .joblib-Dateien liegen aber nur lokal. Der Server
findet sie dann nicht und erzeugt gar keine Prognosen mehr.

Dieses Skript sammelt genau die Dateien, die der Server braucht, in einen
Ordner - damit beim Kopieren keine falsche oder veraltete Version erwischt wird.

    python -m scripts.export_models --env prod
    python -m scripts.export_models --env prod --env test
"""
import argparse
import shutil

import config
import db

EXPORT_DIR = config.BASE_DIR / "export_models"


def export(envs: list[str]) -> None:
    EXPORT_DIR.mkdir(exist_ok=True)
    for alt in EXPORT_DIR.glob("*.joblib"):
        alt.unlink()

    gesamt = 0
    for env in envs:
        rows = db.query(
            "SELECT model_type, horizon_h, trained_at, artifact_path "
            "FROM ai_model_runs WHERE is_active = 1 ORDER BY model_type, horizon_h",
            env=env,
        )
        if not rows:
            print(f"{env}: keine aktiven Modelle in der Datenbank")
            continue
        print(f"\n{env} ({config.db_name(env)}):")
        for r in rows:
            quelle = config.artifact_file(r["artifact_path"])
            if not quelle.exists():
                print(f"  FEHLT: {r['artifact_path']} - zuerst trainieren!")
                continue
            shutil.copy2(quelle, EXPORT_DIR / quelle.name)
            groesse = quelle.stat().st_size
            gesamt += groesse
            bez = f"+{r['horizon_h']}h" if r["horizon_h"] else "Basis"
            print(f"  {bez:6} {quelle.name:34} {groesse/1e6:5.1f} MB  "
                  f"(trainiert {r['trained_at']:%d.%m. %H:%M})")

    anzahl = len(list(EXPORT_DIR.glob("*.joblib")))
    print(f"\n{anzahl} Dateien, {gesamt/1e6:.1f} MB in:\n  {EXPORT_DIR}")
    print("\nAuf den Server kopieren (WinSCP oder scp):")
    print(f"  scp {EXPORT_DIR}\\*.joblib root@87.106.222.137:/root/FastAPI-ML/models_store/")
    print("\nDanach dort pruefen:")
    print("  curl -sS http://localhost:8080/api/health   # last_prediction muss frisch werden")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--env", action="append", choices=["prod", "test"],
                        help="mehrfach angebbar; Standard: prod")
    args = parser.parse_args()
    export(args.env or ["prod"])
