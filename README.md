# Skynet til TeamSpeak 6

Lille tekstbot til en selvhostet TeamSpeak 6-server. Den lytter på **én kanalchat** og reagerer på beskeder, der starter med `*` (`* hej skynet` eller `*hej skynet`; mellemrum er valgfrit). De ældre `!skynet spørgsmål` og `/skynet spørgsmål` virker stadig. Den svarer med OpenAI `gpt-6-luna`, reasoning `low`.

Status: Koden er testet lokalt med simulerede chat-events. **Der er endnu ikke testet mod Dammes TS6 beta12.1 eller en rigtig OpenAI-nøgle.** Den konkrete kanaladfærd, query-rettigheder og SSH-login skal afprøves på serveren. TeamSpeaks support har bekræftet, at query-klienten skal være i samme kanal som brugeren for at se kanalchat.

## Hvad botten behøver

- Python 3.12 og `paramiko` (probe-imaget bruger digest-pinnet Alpine og hash-låste wheels fra `requirements.lock`; `requirements.txt` er kun til lokal udvikling).
- En dedikeret SSH ServerQuery-identitet med adgang til at vælge virtual server, finde eget klient-ID, registrere kanalchat-events og senere sende kanalbeskeder. Koden flytter kun query-klienten, hvis `whoami` viser en anden kanal; giv ikke flytterettigheder, hvis standardkanalen allerede er den valgte. Præcise TS6 beta12.1-permissionnavne skal verificeres på den kørende server.
- En OpenAI API-nøgle med credits. Den bruges kun til spørgsmål, der starter med Skynet-kommandoen.
- Serverens SSH-hostnøglefingeraftryk til pinning.

Botten har ingen adminfunktioner, håndterer ikke stemme og får ikke Docker-adgang.

## Lokal test uden credentials

```bash
python3 -m venv .venv
. .venv/bin/activate
pip install -r requirements.txt
python -m unittest discover -s tests -v
```

Testene bruger hverken TS6 eller OpenAI. De beviser derfor kun den lokale logik.

## Deployment til Damme

Se `LOCAL_DEPLOYMENT.md` for aktuel primary-status. `compose.probe.yml` er TS-only. Den permanente service er defineret i `compose.yml` og bruger den lokale `.env` til OpenAI-nøglen.

Dammes administrator styrer denne del. Lav først backup af den eksisterende Compose-fil og registrér den aktuelle `teamspeak6` image/tag. Planlæg et kort afbrud til genoprettelse af **kun primary**. `teamspeak6-2` skal ikke ændres.

1. Fjern primary-servicens host-publiceringer `10022:10022` og `10080:10080`. De interne containerporte fungerer stadig på Compose-netværket. Bekræft, at SSH-query ikke længere er tilgængelig på hostens offentlige adresser.
2. Aktivér først SSH-query på `teamspeak6`, når primarys 10022/10080-hostbindinger er fjernet og verificeret. Bind `TSSERVER_QUERY_SSH_IP` til primarys faste IP på det dedikerede interne query-netværk; ellers kan andre containere på standardnetværket nå query. Hold HTTP-query deaktiveret. `TSSERVER_QUERY_SSH_ALLOW_GUEST=0` er ikke understøttet på beta12.1; brug ikke en beta13-indstilling som sikkerhedsgaranti.
3. Opret en separat query-identitet/-gruppe til Skynet med de nødvendige chat-rettigheder. Brug ikke `serveradmin` til den kørende bot. Hvis den nødvendige begrænsning ikke kan etableres, stop deploymenten her.
4. Query-password ligger i den lokale UID-10001-ejede secret-fil med mode `0400`. OpenAI-nøglen kan sættes i projektets lokale `.env` (`OPENAI_API_KEY=...`); filen er mode `0600` og ignoreret af Git/Docker-build-context. Indsæt eller send aldrig nøglen i Discord.
5. Pin TS6 SSH-hostnøglen: find den faktiske offentlige nøgle på TS6-host/container, verificér den uafhængigt, og beregn OpenSSH `SHA256:`-fingeraftrykket. Et ubekræftet `ssh-keyscan`-resultat alene er ikke en identitetskontrol.
6. Tilføj Skynet på et dedikeret **internt query-netværk**, der kun deles med `teamspeak6`, ikke på standardnetværket med databasen. Ingen `ports:`, Docker-socket eller særlige privilegier. Brug kun konfigurationsfelter, der passer til den eksisterende Compose-fil.
7. Den første probe bruger `compose.probe.yml` og den faktiske kanal `6` (`Who's a good little monkey?`) på primary, ikke eksempel-ID'et `42`. Den flytter kun sin egen query-klient til kanal 6 ved behov, fordi TeamSpeak-staff bekræfter, at chat-events kun ses i samme kanal; begræns og verificér denne rettighed først, ellers stop. Kør `docker compose -p skynet-probe -f compose.probe.yml run --rm --no-deps probe` med verificeret SSH-fingerprint og kun query-secret. Den kontakter ikke OpenAI, sender ingen chatbeskeder og venter op til 60 sekunder på en almindelig chatbesked i kanalen. Den logger kun, om eventen kom frem. Kør **ikke** den permanente bot eller `!skynet hej` før proben er bestået, og AI-fasen er særskilt godkendt.

Den permanente service er defineret i `compose.yml`, ikke i den TS-only-probe. Den bruger det interne query-netværk plus en separat bridge til OpenAI-egress; den har ingen publicerede porte eller Docker-socket. Start først servicen, når `.env` indeholder en API-nøgle.

`TS_HOST_KEY_SHA256` er påkrævet. Botten afviser forbindelsen, hvis SSH-hostnøglen ændres. `TS_CHANNEL_ID` og eventuelt `TS_SERVER_ID` skal være de faktiske ID'er fra primary-serveren.

## Driftsadfærd

- Kanalbeskeder, der starter med `*` (med eller uden mellemrum efter stjernen), behandles. De ældre `!skynet`- og `/skynet`-kommandoer virker stadig.
- Maks. 1.200 tegn pr. spørgsmål, 15 sekunders pause pr. afsender og højst tre korte svarbeskeder.
- Botten svarer ikke på egne beskeder og genopretter SSH-forbindelsen ved fejl.
- Der gemmes ingen samtalehistorik. OpenAI-kaldet bruger `store: false`.
- Spørgsmål sendes til OpenAI; kanalens øvrige chat sendes ikke. Programmet logger ikke selve spørgsmålene.
- OpenAI API-fejl vises som en kort fejlbesked i chatten. Ingen API-nøgler vises.

## Kilder og versionsforbehold

- [Officiel TS6 serverkonfiguration](https://github.com/teamspeak/teamspeak6-server/blob/main/CONFIG.md)
- [TS6 beta13 udgivelsesnote om ny gæsteadgang](https://github.com/teamspeak/teamspeak6-server/releases/tag/v6.0.0-beta13)
- [TeamSpeak community: query-klienten skal være i samme kanal](https://community.teamspeak.com/t/server-query-how-to-receive-textchannel-event-notifications/62346)
- [OpenAI Responses API tekstgenerering](https://developers.openai.com/api/docs/guides/text)
- [OpenAI GPT-6 Luna](https://developers.openai.com/api/docs/models/gpt-6-luna)
