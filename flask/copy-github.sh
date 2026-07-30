#!/bin/bash

# Variablen definieren
REPO_URL="https://github.com/roger-infanger-weibel/parkhaus-data-crawler.git"
TARGET_DIR="latest-github"

# Falls das Zielverzeichnis bereits existiert, wird es zuerst entfernt
if [ -d "$TARGET_DIR" ]; then
    echo "🧹 Altes Verzeichnis '$TARGET_DIR' wird entfernt..."
    rm -rf "$TARGET_DIR"
fi

echo "🚀 Starte Download des gesamten Repositories..."

# Komplettes Repo ohne tiefen Verlauf in den Zielordner kopieren
git clone --depth 1 "$REPO_URL" "$TARGET_DIR"

if [ -d "$TARGET_DIR" ]; then
    # Git-Verlauf entfernen, da keine Weiterarbeit im Git-Verbund gewünscht ist
    rm -rf "$TARGET_DIR/.git"
    echo "✅ Fertig! Alle Ordner (flask, scanner, linux-cmd) wurden nach '$TARGET_DIR' kopiert."
else
    echo "❌ Fehler beim Herunterladen des Repositories."
fi
