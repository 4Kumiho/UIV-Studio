<div align="center">

<img src="uiv_studio/resources/icon.png" width="96" alt="UIV Studio">

# UIV Studio

**Registra. Riproduci. Valida.**

Registra un flusso d'interfaccia una volta, poi riproducilo e **validalo automaticamente** su qualsiasi
schermo: prima di ogni azione UIV Studio verifica che l'elemento giusto sia davvero lì, e alla fine ti
consegna un report con punteggi, confronto atteso/trovato e video dell'esecuzione.

![Windows](https://img.shields.io/badge/Windows-10%20%7C%2011-0078D6?logo=windows&logoColor=white)
![Linux](https://img.shields.io/badge/Linux-X11%20%7C%20GNOME%20Wayland-FCC624?logo=linux&logoColor=black)
![Wayland E2E](https://github.com/4Kumiho/UIV-Studio/actions/workflows/wayland-e2e.yml/badge.svg)
![Qt](https://img.shields.io/badge/UI-Qt%206%20(PySide6)-41CD52?logo=qt&logoColor=white)
![ONNX](https://img.shields.io/badge/AI-ONNX%20Runtime%20%C2%B7%20CPU-005CED)
![Lingue](https://img.shields.io/badge/lingua-IT%20%7C%20EN-7C6CFF)

<img src="docs/screenshots/home.png" width="860" alt="Home">

</div>

---

## Indice

- [Installazione](#-installazione)
  - [Windows](#-windows)
  - [Linux](#-linux)
- [Come si usa](#-come-si-usa)
- [Impostazioni](#%EF%B8%8F-impostazioni)
- [Come funziona la validazione](#-come-funziona-la-validazione)
- [Modelli](#-modelli-leggeri-solo-cpu)
- [Sviluppo e build](#%EF%B8%8F-sviluppo-e-build)
- [Struttura del progetto](#-struttura-del-progetto)

---

## 📦 Installazione

Non serve installare Python né nient'altro. Ti serve solo **internet** per il primo download (circa 100–190 MB).
Scegli il tuo sistema:

- [🪟 Windows](#-windows)
- [🐧 Linux](#-linux)
- [🔄 Aggiornare UIV Studio](#-aggiornare-uiv-studio)
- [🧹 Disinstallare](#-disinstallare)
- [🆘 Se qualcosa non va](#-se-qualcosa-non-va)

### 🪟 Windows

Funziona su **Windows 10 e Windows 11** (64 bit).

**1. Scarica UIV Studio**

- Apri la pagina **https://github.com/4Kumiho/UIV-Studio**
- Clicca il pulsante verde **`<> Code`**, poi **`Download ZIP`**.
- Apri la cartella **Download**, fai **clic destro** sul file `UIV-Studio-main.zip` → **Estrai tutto…** → **Estrai**.
- Sposta la cartella estratta dove preferisci (per esempio sul Desktop o in `Documenti`).

> Sai usare git? Allora basta: `git clone https://github.com/4Kumiho/UIV-Studio.git`

**2. Installa**

- Apri la cartella e fai **doppio clic** su **`Installa UIV Studio.exe`** (l'icona viola/azzurra).
- Se compare la finestra blu **“Windows ha protetto il PC”**: clicca **Ulteriori informazioni** → **Esegui comunque**.
  Succede con tutti i programmi nuovi non firmati, è normale.
- Una finestra mostra il download con la barra di avanzamento. Aspetta che finisca: al termine nella cartella
  compare **`UIV Studio.exe`** e l'app si apre da sola.

**3. Primo avvio**

- La prima volta compare **“Preparazione di UIV Studio – Installazione in corso (solo al primo avvio)”**: aspetta circa
  **20 secondi**. Dalla volta dopo l'app si apre subito.
- Si apre una breve guida con i tre passi fondamentali: leggila e clicca **Inizia**.

**4. Da ora in poi**

- Per aprire l'app fai **doppio clic su `UIV Studio.exe`** (non serve più l'installer).
- Comodo: clic destro su `UIV Studio.exe` → **Mostra altre opzioni** → **Invia a** → **Desktop (crea collegamento)**.

> ℹ️ Nella cartella compare solo `UIV Studio.exe`: i file interni dell'app stanno nella cartella nascosta `.uivstudio`
> accanto a lui. **Non cancellarla**: se lo fai, al prossimo avvio l'app si reinstalla da sola (20 secondi).

### 🐧 Linux

Funziona su tutte le distribuzioni recenti a 64 bit: **Ubuntu 20.04 o successive, Debian 11+, Fedora, Rocky/RHEL 9,
openSUSE, Linux Mint, Arch**…

**Quale sessione stai usando?** Apri il **Terminale** (`Ctrl + Alt + T`) e scrivi:

```bash
echo $XDG_SESSION_TYPE
```

| Risposta | Desktop | UIV Studio |
|---|---|---|
| `x11` | qualsiasi | ✅ funziona subito |
| `wayland` | **GNOME** (Ubuntu, Fedora, Debian standard) | ✅ funziona, serve il **passo 3** una volta sola |
| `wayland` | KDE, Sway, Hyprland… | ❌ al login scegli una sessione **X11 / Xorg** |

**1. Scarica UIV Studio**

Nel terminale, copia e incolla una riga alla volta (poi premi `Invio`):

```bash
cd ~
git clone https://github.com/4Kumiho/UIV-Studio.git
cd UIV-Studio
```

> Non hai `git`? Scarica lo ZIP dalla pagina GitHub (**`<> Code`** → **`Download ZIP`**), fai doppio clic per
> estrarlo, poi nel terminale entra nella cartella: `cd ~/Scaricati/UIV-Studio-main` (oppure `~/Downloads/...`).

**2. Installa**

```bash
sh installa-uiv-studio.sh
```

Lo script scarica l'ultima versione (vedi la barra di avanzamento), crea il file **`UIV Studio`** nella cartella e
apre l'app. La prima volta l'app si prepara per circa **20 secondi**.

**3. Solo per GNOME su Wayland (una volta sola)**

Per registrare su Wayland UIV Studio deve leggere mouse e tastiera. Esegui:

```bash
sudo usermod -aG input $USER
```

Ti chiede la tua password (mentre la scrivi non vedi nulla: è normale), poi **esci dalla sessione e rientra**
(o riavvia il PC). Se lo dimentichi, UIV Studio te lo ricorda con un avviso nella Home.

**4. Da ora in poi**

Per aprire l'app: doppio clic su **`UIV Studio`** nella cartella, oppure dal terminale:

```bash
cd ~/UIV-Studio && ./"UIV Studio"
```

> ℹ️ I file interni dell'app stanno nella cartella nascosta `.uivstudio` accanto all'eseguibile
> (per vederla nel file manager: `Ctrl + H`). Non cancellarla.

<details>
<summary><b>Perché su GNOME Wayland serve il gruppo <code>input</code>?</b></summary>

Su Wayland ogni app è isolata, quindi UIV Studio usa i servizi ufficiali di GNOME:
- **schermo** → *Mutter ScreenCast* via **PipeWire**
- **click, tasti e scroll** → *Mutter RemoteDesktop*
- **registrazione** → lettura diretta di mouse, tastiera e touchpad da `/dev/input` (da qui il gruppo `input`).
  Durante la registrazione UIV Studio gestisce lui il puntatore, così conosce la posizione esatta di ogni click;
  l'accelerazione del mouse può sembrare leggermente diversa.

Il layout della tastiera (per esempio italiano, con “@” e lettere accentate) viene letto dalle impostazioni di GNOME.
Tutto questo è verificato da un test automatico su GNOME Wayland vero a ogni modifica ([`tests/wayland`](tests/wayland)).
</details>

### 🔄 Aggiornare UIV Studio

- Nell'app, in basso nella barra laterale, clicca **Aggiornamenti** → **Aggiorna ora**. L'app scarica la nuova versione,
  si chiude e si riapre aggiornata.
- All'avvio l'app controlla da sola: se c'è una novità vedi un avviso e il pulsante diventa **Nuova versione!**
- In alternativa rilancia l'installer (`Installa UIV Studio.exe` o `sh installa-uiv-studio.sh`).

Le tue registrazioni ed esecuzioni **non vengono toccate** dagli aggiornamenti.

### 🧹 Disinstallare

Cancella la cartella di UIV Studio (con dentro l'eseguibile e la cartella nascosta `.uivstudio`). Le tue registrazioni
restano nella cartella **`Documenti/UIV Studio`**: cancellala solo se non ti servono più.

### 🆘 Se qualcosa non va

| Problema | Soluzione |
|---|---|
| Windows: “Windows ha protetto il PC” | **Ulteriori informazioni** → **Esegui comunque** |
| L'installer dice **“Download non riuscito”** | controlla la connessione a internet (o il proxy aziendale) e riprova |
| Linux: `Permission denied` su `UIV Studio` | nel terminale: `chmod +x "UIV Studio"` |
| Linux: avviso **“Per registrare su Wayland…”** | fai il **passo 3** e poi esci/rientra dalla sessione |
| Linux: su KDE/Sway non registra | al login scegli una sessione **X11 / Xorg** |
| L'app non si apre più | cancella la cartella nascosta `.uivstudio` e riapri: si reinstalla in 20 secondi |

I log dell'app (utili se chiedi aiuto) sono in `%APPDATA%\UIV Studio\logs` su Windows e `~/.config/uiv-studio/logs`
su Linux.

---

Al primo avvio una breve guida spiega i tre passi fondamentali:

<p align="center"><img src="docs/screenshots/welcome.png" width="700" alt="Guida di benvenuto"></p>

---

## 🧭 Come si usa

### 1 · Registra

**Nuova registrazione** → dai un nome, scegli lo schermo e usa il tuo programma come sempre.
Click, doppio click, click destro, drag & drop, scroll, testo e combinazioni di tasti diventano step.
Un piccolo indicatore mostra lo stato; la hotkey del menu (predefinita **Ctrl + Shift**) apre pausa,
annulla ultimo step, termina o scarta.

<p align="center"><img src="docs/screenshots/hud.png" width="340" alt="Indicatore di registrazione"></p>

### 2 · Controlla e modifica

Nell'editor vedi ogni step sul suo screenshot. Puoi:

- spostare e ridimensionare il riquadro dell'elemento e il punto di click;
- cambiare azione, tasti modificatori, testo, attese, test case e note;
- riordinare gli step trascinandoli, aggiungerli, duplicarli o eliminarli;
- catturare un nuovo screenshot o unire un'altra registrazione.

<p align="center"><img src="docs/screenshots/editor.png" width="860" alt="Editor"></p>

### Condividere le registrazioni

Ogni utente ha la **sua** libreria, nella cartella `Documenti/UIV Studio` del proprio PC (non nella repo).
Per passare una registrazione a un collega: menu della registrazione → **Esporta per condividere** crea un
unico file `.uivr` (step + screenshot); il collega lo apre con **Importa** nella pagina Registrazioni.

<p align="center"><img src="docs/screenshots/recordings.png" width="860" alt="Libreria registrazioni"></p>

### 3 · Esegui e leggi il report

**Esegui** → scegli la registrazione e lo schermo. UIV Studio ti avvisa se risoluzione o scala sono
diverse da quelle registrate (vengono gestite automaticamente).

<p align="center"><img src="docs/screenshots/run_dialog.png" width="560" alt="Avvio esecuzione"></p>

Durante l'esecuzione la hotkey mette in pausa (riprendi, salta step, interrompi). Alla fine il report
mostra per ogni step l'esito, l'elemento **atteso** accanto a quello **trovato**, i punteggi rispetto alla
soglia e il video sincronizzato (clic sui marker della timeline per saltare allo step). Il report si
esporta in HTML.

<p align="center"><img src="docs/screenshots/report.png" width="860" alt="Report"></p>

<p align="center"><img src="docs/screenshots/runs.png" width="860" alt="Esecuzioni"></p>

---

## ⚙️ Impostazioni

Tutto si regola dall'interfaccia, senza toccare file:

| Sezione | Cosa puoi cambiare |
|---|---|
| **Tasti rapidi** | menu registrazione, chiusura testo, menu esecuzione (clicca e premi la combinazione; i conflitti vengono segnalati) |
| **Validazione** | soglia di confidenza, accettazione immediata, margine di ambiguità, tentativi per step, attesa tra tentativi, raggio di ricerca |
| **Pesi** | peso di aspetto, testo e forma, separati per elementi con e senza testo |
| **Esecuzione** | pausa tra gli step, velocità mouse e digitazione, video e FPS, stop al primo errore |
| **Registrazione** | intervallo doppio click, soglia drag, raggruppamento scroll |
| **Generale** | lingua (IT/EN), posizione dell'indicatore, riduzione finestra, cartella workspace |

<p align="center"><img src="docs/screenshots/settings.png" width="860" alt="Impostazioni"></p>

---

## 🎯 Come funziona la validazione

Per ogni step, a ogni tentativo UIV Studio fa uno screenshot nuovo e:

1. **Ricerca locale** attorno alla posizione registrata. Se il punteggio supera *Accettazione immediata*,
   l'elemento è trovato.
2. **Ricerca globale** multi-scala su tutto lo schermo e, se l'elemento contiene testo, **ricerca per testo**.
3. Ogni candidato riceve un **punteggio composito** pesato:
   - **aspetto**: correlazione dei colori con il ritaglio registrato;
   - **testo**: somiglianza del testo letto con l'OCR;
   - **forma**: descrittore visivo.

   Se due candidati sono quasi pari vince il più vicino alla posizione registrata, così pulsanti identici
   altrove non vengono scambiati.
4. Sopra la **soglia di confidenza** lo step passa e l'azione viene eseguita nel punto corrispondente;
   altrimenti si riprova fino al numero di tentativi impostato.

Nei test automatici l'elemento viene ritrovato con schermo identico, elementi spostati e risoluzione
diversa con scala 125%; un elemento assente viene correttamente segnalato come **Fallito**
(punteggio 0.61 con soglia 0.82: nessun falso positivo).

---

## 🧠 Modelli leggeri, solo CPU

Nessun PyTorch e nessuna GPU richiesta.

| Segnale | Implementazione | Dimensione |
|---|---|---|
| Testo | OCR PP-OCRv4 (rilevamento + riconoscimento) su ONNX Runtime | ~15 MB |
| Aspetto | OpenCV `TM_CCOEFF_NORMED` multi-scala | — |
| Forma | descrittore gradienti + istogramma colore; opzionale MobileNetV3-Small ONNX ([`tools/export_embedder.py`](tools/export_embedder.py)) | 0 / ~6 MB |

---

## 🛠️ Sviluppo e build

```bash
python -m venv .venv
.venv\Scripts\pip install -r requirements.txt      # Linux: .venv/bin/pip
python -m uiv_studio                               # avvia l'app
python tests/test_engine_e2e.py                    # test end-to-end del motore (non muove il mouse)
```

**Provare su GNOME Wayland** (anche da Windows, con Docker Desktop): un GNOME headless con mutter,
XWayland e PipeWire, un'app di prova, registrazione tramite mouse/tastiera virtuali ed esecuzione reale.

```bash
docker build -t uiv-wayland -f tests/wayland/Dockerfile .
docker run --rm --device /dev/uinput --device-cgroup-rule='c 13:* rmw' --cap-add=MKNOD -v "$PWD":/src uiv-wayland bash tests/wayland/session.sh python tests/wayland/e2e_wayland.py
```

**Rilascio di una nuova versione:** aggiorna `__version__` in `uiv_studio/__init__.py`, poi
`git tag v1.0.1 && git push --tags`. GitHub Actions compila gli eseguibili Windows e Linux e li allega alla
Release; gli installer scaricano sempre l'ultima.

**Eseguibile Windows in locale** (unico file, creato nella root del progetto):

```powershell
powershell -ExecutionPolicy Bypass -File packaging\build_windows.ps1
```

**Eseguibile Linux** (unico file, compilato su glibc 2.31 per girare su Ubuntu 20.04+, Debian 11+,
Fedora, RHEL/Rocky 9, openSUSE, Arch, Mint…):

```bash
docker build -t uiv-build -f packaging/Dockerfile.linux .
docker run --rm -v "$PWD":/src uiv-build
```

L'eseguibile è un piccolo launcher con l'app compressa in coda ([`launcher/launcher.py`](launcher/launcher.py)):
al primo avvio la estrae con una barra di avanzamento, poi la avvia.

Dati utente:

- workspace (registrazioni `.uivr` ed esecuzioni `.uivx` + video): `Documenti/UIV Studio`
- impostazioni e log: `%APPDATA%\UIV Studio` · `~/.config/uiv-studio`

---

## 📁 Struttura del progetto

```
uiv_studio/
  core/      impostazioni, tasti, monitor e DPI, modelli dati, archivio SQLite
  vision/    riquadro elemento, OCR, descrittore visivo, matcher
  engine/    cattura input, registratore, esecutore, azioni, video
  ui/        tema, widget animati, indicatore e menu di sessione, pagine
installer/   installer leggero della root: scarica l'eseguibile dalla Release
launcher/    eseguibile unico: estrae l'app al primo avvio e la avvia
packaging/   spec PyInstaller, script di build Windows/Linux, Dockerfile
tests/       test end-to-end del motore
docs/        screenshot
```

---

## 📄 Licenza

Copyright © 2026 **4Kumiho**. Tutti i diritti riservati.

UIV Studio è stato ideato e realizzato da 4Kumiho. Il codice è pubblico solo in consultazione: puoi scaricare
e usare gli eseguibili ufficiali, ma copiare, modificare o ridistribuire il software richiede
l'autorizzazione scritta dell'autore. Dettagli in [LICENSE](LICENSE).
