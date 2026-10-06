# E-Mail-Empfänger lokal prüfen

Dieses eigenständige Entwicklerwerkzeug prüft die Empfängerfelder einer gespeicherten `.eml`-Datei anhand einer ausdrücklich festgelegten Regeldatei. Es verändert keine Bestellung und verschickt keine E-Mail.

## Start

1. Vorabversion herunterladen und entpacken. Python ab 3.10 wird benötigt.
2. Die Beispieldatei `examples/policy.json` als eigene lokale Regeldatei kopieren.
3. Erlaubte und erforderliche Empfänger je Feld festlegen.
4. Nachricht mit der passenden Regeldatei untersuchen:

```sh
python3 email_recipient_audit.py nachricht.eml --policy regeln.json --format=json
```

`allowed` enthält erlaubte Adressen getrennt nach `to`, `cc` und `bcc`. Fehlende Felder erlauben keine Adresse. `required` legt fest, welche dieser Adressen in genau diesem Feld vorhanden sein müssen. `allow_bcc: false` verbietet beobachtete Bcc-Empfänger. Verwende eigene Regeln für Kunden- und interne Bestellmails.

Der Bericht nennt keine Adressen, Namen, Betreffzeilen oder Nachrichteninhalte. Er verwendet lokale Kennungen wie `r1`, damit Duplikate erkennbar bleiben. Die Regeldatei und die ursprüngliche E-Mail können persönliche Daten enthalten; verwende für öffentliche Fehlerberichte erfundene Daten.

## Was das Ergebnis bedeutet

- Fehler: etwa unerwarteter Empfänger, erforderlicher Empfänger nicht beobachtet oder unvollständig lesbare Kopfzeile.
- Warnung: etwa ein mehrfach auftauchendes Postfach.
- Die Kennungen gelten nur innerhalb eines Berichts.
- Domains werden vereinheitlicht; der Teil vor `@` bleibt einschließlich Groß-/Kleinschreibung erhalten. Alias-Adressen werden nicht zusammengeführt.

Eine empfangene E-Mail enthält häufig kein Bcc-Feld mehr. Dieses Werkzeug untersucht gespeicherte Kopfzeilen und kann weder tatsächliche SMTP-Empfänger noch Zustellung bestätigen. Es prüft auch keine WooCommerce-Einstellungen auf dem Server.

Version 0.1.0 ist eine Vorabversion. Automatische GitHub-Prüfungen kontrollieren Syntax und Paketbau; umfassende Funktionstests und konkrete Shop-Kombinationen sind damit nicht nachgewiesen.

Entwickelt von [Nakaryu GmbH](https://nakaryu.de), MIT-Lizenz. Weitere Details stehen in der englischen [README](../README.md).
