#!/bin/bash
# lancer.sh - pose par le template AMP TeamKit (Simutrans), reecrit a chaque Update.
#
# AMP lance ce script. Il choisit la partie a charger, puis cede la place au
# serveur (exec) : c'est donc le serveur lui-meme qui recoit le signal d'arret
# d'AMP, et il sauvegarde la partie avant de s'eteindre.
#
# Ordre de choix de la partie :
#   1. une "partie de depart" nouvelle ou modifiee dans save/  -> on la charge
#      (l'ancienne partie du serveur est rangee dans save/archive-...)
#   2. la sauvegarde faite a l'arret, si elle est la plus recente
#   3. la derniere sauvegarde du serveur (Simutrans la reprend tout seul)
#   4. rien du tout : Simutrans genere une carte de depart (64 x 64)
PORT="$1"; PAK="$2"; LANGUE="$3"; PARTIE="${4%.sve}"
cd "$(dirname "$0")" || exit 1
NET="server${PORT}-network.sve"; RES="server${PORT}-restore.sve"; HASH="server${PORT}-pwdhash.sve"
MARQ=".teamkit-partie"; HORO=$(date +%Y%m%d-%H%M%S)
mkdir -p save
[ -x ./simutrans-server ] || { echo "TeamKit : ERREUR simutrans-server absent, lance Update dans AMP."; exit 1; }
[ -f "$PAK/ground.Outside.pak" ] || { echo "TeamKit : ERREUR pakset $PAK absent, lance Update dans AMP."; exit 1; }

archiver() {
  for f in "$NET" "$RES"; do [ -f "$f" ] && mv -f "$f" "save/archive-$HORO-$1-$f"; done
  rm -f "$HASH"
}

ANCIEN=$(cat "$MARQ" 2>/dev/null)
ANCIEN_PAK=${ANCIEN%%|*}
CHARGER=""
if [ -n "$ANCIEN_PAK" ] && [ "$ANCIEN_PAK" != "$PAK" ]; then
  echo "TeamKit : pakset change ($ANCIEN_PAK -> $PAK), l'ancienne partie est rangee dans save/."
  archiver "$ANCIEN_PAK"; ANCIEN=""
fi
if [ -n "$PARTIE" ]; then
  if [ -f "save/$PARTIE.sve" ]; then
    SIG="$PAK|$PARTIE|$(stat -c %Y "save/$PARTIE.sve")"
    if [ "$SIG" != "$ANCIEN" ]; then
      echo "TeamKit : nouvelle partie de depart save/$PARTIE.sve, l'ancienne est rangee dans save/."
      archiver "avant-$PARTIE"; CHARGER="$PARTIE"; ANCIEN="$SIG"
    fi
  else
    echo "TeamKit : ATTENTION save/$PARTIE.sve introuvable, on continue la partie en cours."
  fi
fi

if [ -z "$CHARGER" ]; then
  if [ -f "$RES" ] && { [ ! -f "$NET" ] || [ "$RES" -nt "$NET" ]; }; then
    mv -f "$RES" "$NET"; echo "TeamKit : reprise de la sauvegarde faite a l'arret."
  fi
  if [ ! -f "$NET" ]; then
    P=${ANCIEN#*|}; P=${P%%|*}
    if [ -n "$P" ] && [ -f "save/$P.sve" ]; then
      CHARGER="$P"; echo "TeamKit : aucune sauvegarde du serveur, on repart de save/$P.sve."
    else
      # Un serveur sans affichage qui cree lui-meme sa carte reste en pause et
      # perd la synchronisation au premier joueur (vu en test). On genere donc
      # la carte HORS mode serveur, on l'enregistre, et le serveur la charge.
      echo "TeamKit : aucune partie, creation d'une carte de depart par Simutrans (64 x 64)..."
      rm -f "autosave-$PAK.sve"
      ./simutrans-server -singleuser -objects "$PAK" -lang "$LANGUE" -debug 3 >/dev/null 2>.teamkit-generation.log &
      G=$!
      for i in $(seq 1 300); do
        grep -q "Running world" .teamkit-generation.log && break
        kill -0 $G 2>/dev/null || break
        sleep 1
      done
      kill -TERM $G 2>/dev/null; wait $G 2>/dev/null
      if [ -f "autosave-$PAK.sve" ]; then
        mv -f "autosave-$PAK.sve" "$NET"; rm -f "$HASH"
      else
        echo "TeamKit : ERREUR la carte de depart n'a pas pu etre creee :"; tail -5 .teamkit-generation.log; exit 1
      fi
    fi
  fi
fi
if [ -n "$ANCIEN" ]; then echo "$ANCIEN" > "$MARQ"; else echo "$PAK||" > "$MARQ"; fi

if grep -q "^server_announce = 1" simuconf.tab 2>/dev/null && grep -q "^server_dns = *$" simuconf.tab; then
  echo "TeamKit : ATTENTION annonce publique activee mais 'Adresse publique annoncee' est vide."
fi

ARGS=(-singleuser -server "$PORT" -objects "$PAK" -lang "$LANGUE" -debug 3)
[ -n "$CHARGER" ] && ARGS+=(-load "$CHARGER")
echo "TeamKit : demarrage de Simutrans ${ARGS[*]}"
exec ./simutrans-server "${ARGS[@]}" 2>&1
