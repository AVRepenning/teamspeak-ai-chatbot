# TeamSpeak 6 / Neuro — lokal prototype

Dette er en **manuel push-to-talk prototype**, ikke en færdig TeamSpeak-bot.
Den forbinder ikke automatisk til serveren eller flytter sig selv ud af AFK.
Den optager kun, når operatøren trykker Enter; kun ytringer der begynder med
"Hey Bot" sendes til Hermes-motoren. Det gamle vækkeord "Neuro" og "Bot"
alene udløser ikke et svar.
Ingen optagelse mellem tryk.

## Status på denne pc
- TS6-klienten og Python-pakkerne `numpy`, `sounddevice`, `faster-whisper`,
  `edge-tts`, `av`, `requests` findes allerede.
- VB-CABLE og Voicemeeter er installeret, pc'en genstartet, og begge vises
  som lydenheder. Den ende-til-ende lydrute er endnu ikke godkendt ved test.
- TS6 Remote Apps på lokal port 5899 svarede ikke. API'et kan give hændelser,
  men dokumenterer ikke ind/udgående talelyd.
- Hermes-profilen `tshermes` er oprettet med egen API-nøgle. Alle API-værktøjer
  er deaktiveret og kontrolleret via `/p/tshermes/v1/toolsets`.
- Værtens gateway er startet manuelt, og tekstkæden er verificeret med et svar.
  Den er ikke installeret som autostart-service; start med `hermes gateway run`.
- Separat TS6-profil (`--cpa=HermesBot`) er oprettet med TeamSpeak-brugernavnet
  `Neuro_Sama_Bot` og koblet til `-=The Flying Circus=-` via invitation.
  Mikrofonen er slået fra i botklienten. Capture er sat til CABLE Output;
  playback er nu sat til Voicemeeter Input (bekræftet i botklientens UI),
  og botklientens Output Volume blev ændret fra -28,5 dB til 0 dB og
  kontrolleret efter genåbning af lydindstillingerne. Dette påvirker ikke
  ejerens normale TeamSpeak-klient. En efterfølgende input-test gav
  RMS=0,015131, peak=0,315254 og "Hej neuro, vejløro!": vækkeordet blev
  genkendt, mens spørgsmålet fortsat blev fejltransskriberet. Næste forsøg
  sammenlignede samme 15-sekunders klip med og uden Whispers VAD:
  RMS=0,021498, peak=0,421734; med VAD "Hej, Nero! Vælg ordentligt!",
  uden VAD "Hej Nero, vejl E.O.R.u.". VAD-frakobling rettede altså ikke
  denne fejl; ingen lydfil blev gemt, og ingen bot-svar blev udsendt.
  Der er endnu ikke udført en ende-til-ende TeamSpeak-taletest.
- Voicemeeter Basic (type 1) er startet og afgrænset via dens Remote API:
  hardware-strips 0/1 er muted og frakoblet B1; virtuel strip 2 er
  frakoblet fysiske A1/A2 og tilkoblet B1. Parametrene er læst tilbage.
  En samtidig 48-kHz toneprøve fra `Voicemeeter Input` til `Voicemeeter Out B1`
  viste peak 0,030; VB-CABLE fra `CABLE Input` til `CABLE Output` viste
  peak 0,020. Dette tester kun de lokale virtuelle ruter, ikke TS6-lyd.
- Hermes-API gav svaret `Neuro er klar til test.`; Whisper `small` blev
  indlæst på CPU; Edge TTS gennemførte afspilning til CABLE Input, mens
  botklienten var muted. Syv automatiske tests består.
- En tidligere diagnostisk optagelse viste RMS=0 og peak=0. Botklientens
  playback viste sig siden at være Default Device (VAIO3); den blev sat til
  Voicemeeter Input. En efterfølgende input-test gav RMS=0,000620,
  peak=0,010956 og transskriptionen "Enero, hvad hedder du?". Lyd når altså
  frem, men vækkeordet blev ikke genkendt korrekt; intet svar blev afspillet.
- Den tidligere langvarige interaktive proces efterlod Python-børn, når
  terminalens wrapper blev stoppet. Brug engangsdiagnose eller verificér
  alle `bot.py --safe-devices`-processer efter stop.
- Prototypekoden er nu sat til engelsk: Whisper `language='en'`, engelsk
  systembesked og standard-TTS `en-US-JennyNeural`. En aftalt lokal
  25-sekunders inputoptagelse fangede kun brugerens ene ytring sidst i
  vinduet (ca. sekund 22–25); Damme_ var gået. Whisper `small` gav med VAD
  `How was your day?` og uden VAD `Hey Nero, how was your day?`. Det er
  væsentligt tættere på den aftalte engelske sætning, men vækkeordet blev
  ikke nøjagtigt genkendt, og den anden taler blev ikke prøvet. WAV-filen
  blev slettet efter analysen; ingen bot-svar blev sendt.
- Vækkeordet er efterfølgende ændret til præcis `Hey Bot` i prototypen,
  uden at ændre den separate TS6-klients synlige navn. En aftalt
  25-sekunders inputtest med to gentagelser gav med VAD
  `hey bud how's your day hey bud how's your day ...` og uden VAD
  `Hey, but how's your day hey, but how's your day ...`. Spørgsmålet blev
  omtrent genkendt, men ingen af transskriptionerne matcher det præcise
  vækkeord. `bud`/`but` tilføjes ikke som alias pga. risiko for falsk
  aktivering. Intet Hermes-kald eller svar blev sendt; WAV blev slettet.

## Krav før stemme i kanalen
1. Botklientens playback er `Voicemeeter Input (VB-Audio Voicemeeter VAIO)`.
   Kontrollér før en ny kørsel, at hardwareinput er muted og fysisk A-output
   er frakoblet; Voicemeeters miks kan ændres af andre programmer.
2. Python-input skal være returenden af denne rute; Python-output skal være
   CABLE Input (TS6 capture = CABLE Output). Undgå standardenheder,
   headset, højttalere og Stereo Mix.
3. Start den lokale Hermes-gateway; API-nøglen læses fra tshermes-profilens
   .env-fil og må ikke kopieres til projektfiler.
4. Vis tydeligt for alle deltagere, at botten behandler stemmeklip ved aktivering.
   Talegenkendelse sker lokalt med faster-whisper; edge-tts sender selve svaret
   til en ekstern TTS-tjeneste. Slå ikke optagelse til uden deres accept.

## Kørsel
```bash
python bot.py --list-devices
python bot.py --safe-devices --test-text "How are you?"
python bot.py --safe-devices --diagnose-input --seconds 45
python capture_clip.py --seconds 25  # kun efter særskilt samtykke fra alle til gemt klip
python bot.py --safe-devices --manual-question --seconds 15
python bot.py --safe-devices
python -m unittest discover -s . -p 'test*.py' -v
```

Whisper `small` er hentet og indlæst. Programmet optager kun ved Enter
(7 sekunder som standard), svarer kun når transskriptionen begynder med
`Hey Bot`, og lytter ikke mellem
optagelser. Start først efter at **kun**
botklientens Playback Device viser `Voicemeeter Input (VB-Audio Voicemeeter
VAIO)` og efter samtykke fra testdeltagerne. Hold mikrofonen muted, indtil
en isoleret testkanal er klar; afmut kun under den aftalte test.
`--manual-question` er kun til en aftalt, manuelt startet prøve: Efter Enter
sendes hele det genkendte klip som spørgsmål uden vækkeord. Brug det ikke som
automatisk lytter; botklienten forbliver muted, indtil en særskilt svartest
er aftalt. `--diagnose-input` har altid forrang og sender aldrig svar.
`capture_clip.py` er en separat, engangs lokal optagelse fra kun Voicemeeter
Out B1. Den venter på Enter, gemmer højst 25 sekunder som WAV under Hermes'
scratch-mappe, transskriberer ikke og afspiller/sender intet. Brug kun efter
samtykke til midlertidig lagring; slet den præcise WAV-fil efter undersøgelsen.
Indtil den isolerede afspilningsretur er verificeret, kan **stemmeforbindelsen
ikke bruges sikkert**. Skriptet afviser
almindelig mikrofon og standard-/headset-output for at mindske risikoen for
at optage dig eller skabe ekko. Start ikke botten i en virkelig kanal, før
rutevalget er kontrolleret.
