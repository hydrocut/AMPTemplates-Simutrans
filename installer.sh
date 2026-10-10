#!/bin/bash
# installer.sh - pose par le template AMP TeamKit (Simutrans), reecrit a chaque Update.
#
# 1. telecharge Simutrans (donnees du jeu : textes, scripts, IA, config)
# 2. compile le SERVEUR SANS AFFICHAGE depuis les sources officielles
#    (le binaire Linux publie est un client SDL2 : en serveur, il bloque sur
#    la fenetre d'accueil et ne repond a aucun joueur)
# 3. telecharge le pakset choisi dans AMP
#
# Ne touche jamais aux parties (save/, server*.sve) ni a simuconf.tab.
set -e
PAK="$1"

# Version de Simutrans. Pour passer a la suivante, changer les DEUX lignes :
# le numero de revision est celui qu'affiche le binaire officiel au demarrage
# ("Simutrans version 125.0.1 from Oct  5 2026 r12334"). Les clients le
# comparent a celui du serveur dans la liste des serveurs.
VERSION=125-0-1
REVISION=12334

SF=https://downloads.sourceforge.net/project/simutrans
case "$PAK" in
  pak)    PAK_URL="$SF/pak64/125-0/simupak64-125-0.zip" ;;
  pak128) PAK_URL="$SF/pak128/pak128%20for%20ST%20125.0%20up%20%282.10.3%29/simupak128-2-1023-for-125-0up.zip" ;;
  *) echo "ERREUR : pakset inconnu '$PAK' (attendu : pak ou pak128)"; exit 1 ;;
esac

cd "$(dirname "$0")"
mkdir -p simutrans

if [ "$(cat simutrans/.teamkit-version 2>/dev/null)" != "$VERSION-r$REVISION" ] || [ ! -x simutrans/simutrans-server ]; then
  echo "Telechargement de Simutrans $VERSION..."
  curl -fsSL -o simutrans-linux.zip "$SF/simutrans/$VERSION/simulinux-x64-$VERSION.zip"
  unzip -q -o simutrans-linux.zip
  rm -f simutrans-linux.zip

  echo "Telechargement des sources de Simutrans $VERSION..."
  curl -fsSL -o simutrans-src.zip "$SF/simutrans/$VERSION/simutrans-src-$VERSION.zip"
  rm -rf compilation
  mkdir compilation
  unzip -q simutrans-src.zip -d compilation
  rm -f simutrans-src.zip

  # BACKEND posix = le "Simutrans Server" du README officiel : aucun affichage.
  # MSG_LEVEL 3 compile les lignes __ChatLog__ (arrivees, departs, chat) qui
  # font vivre la liste des joueurs dans AMP.
  cat > compilation/config.default <<CFG
BACKEND := posix
OSTYPE := linux
MSG_LEVEL := 3
OPTIMISE := 1
MULTI_THREAD := 1
USE_ZSTD := 1
USE_UPNP := 0
USE_FREETYPE := 0
USE_FONTCONFIG := 0
WITH_REVISION := $REVISION
CFG
  echo "Compilation du serveur sans affichage (1 a 2 minutes)..."
  if ! ( cd compilation && make -j2 > ../compilation.log 2>&1 ); then
    echo "ERREUR de compilation, fin du journal :"
    tail -20 compilation.log
    exit 1
  fi
  cp compilation/build/default/sim simutrans/simutrans-server
  chmod +x simutrans/simutrans-server
  rm -rf compilation compilation.log
  echo "$VERSION-r$REVISION" > simutrans/.teamkit-version
fi

if [ "$(cat "simutrans/.teamkit-$PAK-source" 2>/dev/null)" != "$PAK_URL" ] || [ ! -f "simutrans/$PAK/ground.Outside.pak" ]; then
  echo "Telechargement du pakset $PAK..."
  curl -fsSL -o pakset.zip "$PAK_URL"
  rm -rf "simutrans/$PAK"
  unzip -q -o pakset.zip
  rm -f pakset.zip
  echo "$PAK_URL" > "simutrans/.teamkit-$PAK-source"
fi

mkdir -p simutrans/save
echo "Simutrans $VERSION (r$REVISION) pret, pakset $PAK."
