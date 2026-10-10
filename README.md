# AMPTemplates-Simutrans — Simutrans dedicated server for AMP

**AMP Generic Module** template for a headless **Simutrans** server on Linux
(the free and open-source transport simulation game — Steam app 434520,
<https://www.simutrans.com>). Written for TeamKit, October 2026. CubeCoders
ships no Simutrans template.

> **Résumé en français** — Template AMP pour un serveur Simutrans 125.0.1 sans
> écran. Le binaire Linux officiel est un client graphique : en serveur, il reste
> bloqué sur sa fenêtre d'accueil. Le template **compile donc le vrai serveur sans
> affichage** à partir des sources officielles pendant l'Update (≈ 1 minute), puis
> télécharge le pakset (pak64 ou pak128). La partie est sauvegardée à chaque arrêt
> et reprise au démarrage. Le serveur ne sait pas créer une carte à la taille
> voulue : sans partie, il génère une carte de 64 × 64 ; pour une vraie carte, on la
> crée dans son jeu et on dépose le `.sve` dans `save/`. Les joueurs apparaissent
> dans AMP (arrivées, départs). Un seul port : **13353 TCP**. Voir `FAISABILITE.md`.

## Why the server is compiled

Simutrans publishes Linux binaries for the **SDL2 client** only
(`simulinux-x64-125-0-1.zip`). Its own README lists a separate back-end,
*"Simutrans Server: Server back-end with no graphical interface"* — the
`posix` back-end — but nobody publishes it pre-built for Linux.

Tested in a throw-away `cubecoders/ampbase:debian` container (10 Oct. 2026):

| Binary | Result |
|---|---|
| official SDL2 client + `SDL_VIDEODRIVER=dummy -server 13353` | starts, then blocks in the welcome banner (`modal_dialogue(new banner_t(), …)` in `simmain.cc`, compiled only when `COLOUR_DEPTH != 0`). A client gets `Server did not respond!` |
| `posix` build from `simutrans-src-125-0-1.zip` | works. 65 s to compile with 2 CPUs, 20–27 MB of RAM, the official 125.0.1 client joins it |

So `installer.sh` (run by **Update**) downloads the official data zip, the
official source zip, compiles with this `config.default` and copies the result
as `simutrans/simutrans-server`:

```
BACKEND := posix        # no display at all
MSG_LEVEL := 3          # compiles the __ChatLog__ lines AMP reads (join/leave/chat)
WITH_REVISION := 12334  # the revision printed by the official 125.0.1 binary
OPTIMISE := 1, MULTI_THREAD := 1, USE_ZSTD := 1, USE_UPNP := 0, USE_FREETYPE := 0
```

`WITH_REVISION` matters: clients compare their revision with the server's in
the server list (`gui/server_frame.cc`), and `config.template` says the
revision is *"required for networkgames"*. The value `12334` comes from the
first log line of the official binary:
`Simutrans version 125.0.1 from Oct  5 2026 r12334 hash 0x40bbb12`.

The compiler and `-dev` libraries are installed in the container by
`Meta.ExtraContainerPackages`, hence `ContainerPolicy=Required`.

## Downloads (all checked with `curl -IL`, 10 Oct. 2026)

| File | Size | URL |
|---|---|---|
| game data | 11.2 MB | `https://downloads.sourceforge.net/project/simutrans/simutrans/125-0-1/simulinux-x64-125-0-1.zip` |
| sources | 6.9 MB | `…/simutrans/125-0-1/simutrans-src-125-0-1.zip` |
| pak64 125.0 | 5.2 MB | `…/pak64/125-0/simupak64-125-0.zip` |
| pak128 2.10.3 for 125.0+ | 97.6 MB | `…/pak128/pak128 for ST 125.0 up (2.10.3)/simupak128-2-1023-for-125-0up.zip` |

Versions are pinned in `installer.sh` (`VERSION`, `REVISION`, the two pakset
URLs). Moving to Simutrans 125.1 = edit those lines, then **Update**: the
script sees the version marker change and recompiles.

## How a game is chosen at start (`lancer.sh`)

AMP starts `lancer.sh`, which picks the game and then `exec`s the server, so
the server itself receives AMP's stop signal.

1. A **"Partie de départ"** (savegame name in `simutrans/save/`) that is new or
   was modified since last time → loaded with `-load`. The server's previous
   game is moved to `save/archive-<date>-…sve`, never deleted.
2. `server13353-restore.sve` newer than `server13353-network.sve` → renamed.
   Simutrans writes `-restore.sve` when stopped with
   `server_save_game_on_quit = 1`, but only ever reloads `-network.sve`
   (`simmain.cc`, "recover last server game").
3. `server13353-network.sve` exists → Simutrans resumes it by itself.
4. Nothing at all → a starter map is generated **outside server mode** and
   saved, then loaded by the server. Reason, seen twice in tests: a headless
   server that builds its own map stays paused (`karte_t` starts with
   `step_mode = PAUSE_FLAG`; only the GUI banner unpauses it), and the first
   client to join triggers `wanted to do_command(NWC_SYNC) in the past` and
   `Lost synchronisation with server`. A server started from a savegame does
   not have this problem.

The starter map is **64 × 64** with one town: that size is hard-coded in
`simmain.cc` (`sets.set_size(64,64)`) and there is no command-line option or
`simuconf.tab` key for it. **Map size therefore cannot be set from AMP** — a
real map is made in the game client (same version, same pakset), saved, and
uploaded to `save/`.

Changing the pakset archives the current game too: a pak64 save cannot run on
pak128.

## Settings exposed in AMP

Written by AMP to `simutrans/simuconf.tab`, which Simutrans reads **last**,
after `config/simuconf.tab` and the pakset's own file (`simmain.cc`). Every
key below is read by `settings_t::parse_simuconf()` in
`src/simutrans/dataobj/settings.cc` (125.0.1 source):

| AMP field | Key | Default |
|---|---|---|
| Nom du serveur | `server_name` | `FR TeamKit - Simutrans` |
| Description | `server_comments` | TeamKit line |
| Lien d'information | `server_infurl` | `https://teamkit.fr` |
| Fichier du message d'accueil | `server_motd_filename` | `motd.txt` (file created by the template) |
| Annoncer publiquement | `server_announce` | `0` |
| Adresse publique annoncée | `server_dns` | empty — must be the public IP for the announce to be useful |
| Intervalle d'annonce | `server_announce_interval` | `900` (Simutrans default, clamped 60–86400) |
| Sauvegarder à l'arrêt | `server_save_game_on_quit` | `1` |
| Pause sans joueur | `pause_server_no_clients` | `0` (see below) |
| Mot de passe d'administration | `server_admin_pw` | empty |

Plus three command-line settings: **Pakset** (`pak` / `pak128`, passed as
`-objects`), **Langue** (`-lang`, files `text/<code>.tab` of the official zip)
and **Partie de départ** (see above).

What does **not** exist, so is not offered:

* **a join password** — Simutrans has none (`nwc_join_t` carries only a
  nickname). Each player protects their *company* with a password in game.
  `server_admin_pw` is only for `nettool`, the command-line admin tool
  (`SRVC_LOGIN_ADMIN` in `network_cmd_ingame.cc`).
* **monthly autosave** — disabled in network mode
  (`if( !env_t::networkmode && env_t::autosave>0 …` in `simworld.cc`). Saves
  happen when a player joins (`server13353-network.sve`), when AMP stops the
  server (`-restore.sve`), and with pause mode when the last player leaves.
  AMP's own backups include `*.sve` (`SmartExcludeExemptions`).

### `pause_server_no_clients` is off by default — why

With pause on, the world stops and is saved when the last player leaves —
nice. But Simutrans logs a departure from `karte_t::step()`, which does not
run while paused: the **last** player's `disconnect` line only appears when
the next player arrives. AMP would keep showing that player online, and
TeamKit's inactivity detection relies on AMP's player count. Seen in the
test: after the last client left with pause on, only
`socket_list_t::remove_client` was logged, no `__ChatLog__ disconnect`.

## Players in AMP

`-debug 3` + `MSG_LEVEL 3` make the server log, on its error stream (the
launcher merges it with `2>&1`):

```
Message: simu_main():	Running world, pause=0, fast forward=0 ...
Message: __ChatLog__:	connect,2,127.0.0.1,KevinTest
Message: __ChatLog__:	disconnect,2,127.0.0.1,KevinTest
```

(real lines; the separator after `:` is a tab). `Console.AppReadyRegex`,
`UserJoinRegex` and `UserLeaveRegex` read them. `UserChatRegex` follows the
same `__ChatLog__` CSV format (`chat,client,ip,nick,company#,company,message`)
and ignores the server's own relay lines (`Server#0`); a player chat line could
not be produced in the test (no keyboard on the test client), so that one is
built from the code. `ThrowawayMessageRegex` drops the per-step network chatter
(`NWC_STEP` packets, ~30 lines a second while someone plays).

Stop: `App.ExitMethod=OS_CLOSE`. The posix back-end catches SIGTERM
(`simsys_posix.cc`), saves and exits — 0.2 s in the test. There is no
writable console.

## Check before pushing

```
python verifier.py
```

Must print `Tout est bon.` It checks: valid JSON, `@IncludeJson` targets, port
refs, the full `Console.*`/`Limits.*` block, every exposed key present in the
shipped `simuconf.tab` with the same default, the config regex round trip
(value with spaces, empty value, `=` and comma in a value), every `{{Setting}}`
used on a command line exists, paksets offered = paksets `installer.sh` knows,
the scripts embedded in `simutransupdates.json` are byte-identical to
`installer.sh` / `lancer.sh` (+ `bash -n`), and the console regexes against the
real log lines above (including lines they must **not** match).

`installer.sh` and `lancer.sh` are the readable sources; they are embedded in
`simutransupdates.json` as `CreateFile` stages (AMP clones the repository into
ADS, not into the instance).

## Install the repository in AMP

ADS → Configuration → Instance Deployment → **Configuration Repositories** →
add `hydrocut/AMPTemplates-Simutrans:main`, save, **Fetch Latest**. The
application appears as "Simutrans (TeamKit)". Create the instance, **Update**
(downloads + compile, ~2 minutes), **Start**.

Players need **Simutrans 125.0.1 and the same pakset**, then *Join game* →
`ip:13353`.

## Sources

* Simutrans source code 125.0.1 (`simutrans-src-125-0-1.zip`, SourceForge) —
  `simmain.cc` (command line, game recovery, banner), `dataobj/settings.cc`
  (simuconf keys), `dataobj/environment.cc` (defaults), `world/simworld.cc`
  (save on quit, pause, announce), `network/network_cmd_ingame.cc`
  (`__ChatLog__` lines), `sys/simsys_posix.cc` (SIGTERM), `utils/csv.cc`.
* Simutrans `README.md` (back-ends) and `config.template` (build options).
* `simutrans/config/simuconf.tab` of the official zip (commented server keys).
* Steam store API for app 434520 (name "Simutrans", free).

Simutrans is free software by the Simutrans team (Artistic License). This
repository contains only the template; the game is downloaded from
SourceForge at Update time.
