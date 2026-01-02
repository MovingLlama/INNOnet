# **INNOnet Home Assistant Integration**

Dies ist eine **Custom Component** für [Home Assistant](https://www.home-assistant.io/), um Daten aus dem österreichischen Forschungsprojekt **INNOnet** zu integrieren.

Die Integration ruft das aktuelle **Tarifsignal** (Projekttarif, Hochtarif, Sonnenfenster) sowie (falls verfügbar) den dynamischen **INNOnet-Tarifpreis** ab.

**Hinweis:** Die Abfrageintervalle sind gemäß den API-Vorgaben auf 15 Minuten eingestellt, um die Datenbank nicht zu überlasten.

## **Funktionen**

* **Automatische Einrichtung:** Sie benötigen nur Ihren API-Key. Die Integration findet Ihre Zählpunktnummer (ZPN) automatisch.  
* **Sensoren:**  
  * sensor.innonet\_tariff\_signal: Zeigt den aktuellen Status als Text an (z.B. "Low Tariff (Sun)").  
    * Attribut raw\_value: Beinhaltet den numerischen Wert (0, 1, \-1) für einfache Automatisierungen.  
  * sensor.innonet\_tariff\_price: Der aktuelle Tarifpreis (falls für den aktuellen Zeitraum verfügbar).

## **Installation**

### **Via HACS (Empfohlen)**

1. Stelle sicher, dass [HACS](https://hacs.xyz/) installiert ist.  
2. Füge dieses Repository als "Custom Repository" in HACS hinzu:  
   * Gehe zu HACS \-\> Integrationen \-\> 3 Punkte oben rechts \-\> Benutzerdefinierte Repositories.  
   * Füge die URL dieses Repositories ein und wähle die Kategorie **Integration**.  
3. Klicke auf "Herunterladen".  
4. Starte Home Assistant neu.

### **Manuell**

1. Lade den Ordner custom\_components/innonet aus diesem Repository herunter.  
2. Kopiere den Ordner in dein Home Assistant Konfigurationsverzeichnis unter config/custom\_components/.  
3. Starte Home Assistant neu.

## **Konfiguration**

1. Gehe in Home Assistant zu **Einstellungen** \-\> **Geräte & Dienste**.  
2. Klicke unten rechts auf **Integration hinzufügen**.  
3. Suche nach **INNOnet**.  
4. Gib deinen **API-Key** ein.  
   * *Den API-Key findest du in der INNOnet App unter Einstellungen \-\> Konto \-\> Externe Datenfreigabe \-\> Loxone.*

## **Automatisierungs-Beispiel**

Hier ist ein Beispiel, wie du Geräte nur einschaltest, wenn das "Sonnenfenster" (Niedertarif) aktiv ist:

alias: "Waschmaschine bei Sonnenfenster starten"  
trigger:  
  \- platform: state  
    entity\_id: sensor.innonet\_tariff\_signal  
    to: "Low Tariff (Sun)"  
action:  
  \- service: switch.turn\_on  
    target:  
      entity\_id: switch.waschmaschine

Alternativ kannst du das Attribut raw\_value verwenden (-1 ist Niedertarif):

condition:  
  \- condition: numeric\_state  
    entity\_id: sensor.innonet\_tariff\_signal  
    attribute: raw\_value  
    below: 0  \# \-1 ist kleiner als 0  
