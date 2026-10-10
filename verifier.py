# -*- coding: utf-8 -*-
"""
Contrôle du template avant de le pousser (même rôle que ceux de DDNet et Mumble).

    python verifier.py

1. tous les JSON se parsent ;
2. le .kvp ne référence que des fichiers présents, et il est complet (bloc Console/Limits) ;
3. le port déclaré est celui que le .kvp et les réglages attendent ;
4. chaque réglage exposé dans AMP existe dans le simuconf.tab livré, et la regex
   du metaconfig relit chaque ligne (valeur à espaces, valeur vide, aller-retour) ;
5. chaque {{Réglage}} utilisé en ligne de commande existe, et chaque réglage
   sans ParamFieldName sert bien quelque part ;
6. les pakset proposés sont ceux que installer.sh sait télécharger ;
7. les scripts embarqués dans simutransupdates.json sont identiques à installer.sh
   et lancer.sh du dépôt, et leur syntaxe bash est valide ;
8. les regex de console reconnaissent les VRAIES lignes du serveur, relevées le
   10 oct. 2026 sur Simutrans 125.0.1 compilé en posix (conteneur d'essai,
   client SDL2 officiel « KevinTest » connecté en réseau local).
"""
import io
import json
import os
import re
import shutil
import subprocess
import sys

try:
    sys.stdout.reconfigure(encoding='utf-8')  # accents lisibles dans la console Windows
except Exception:
    pass

ICI = os.path.dirname(os.path.abspath(__file__))
NOM = 'simutrans'
soucis = []


def lire(nom):
    with io.open(os.path.join(ICI, nom), encoding='utf-8', newline='') as f:
        return f.read()


def py(motif):
    # AMP est en C# : (?<nom>...) ; Python veut (?P<nom>...)
    return re.compile(motif.replace('(?<', '(?P<'))


def ok(etiquette, texte):
    print('ok   %-24s %s' % (etiquette, texte))


# ── 1. JSON ──────────────────────────────────────────────────────────────────
data = {}
for nom in ('manifest.json', NOM + 'config.json', NOM + 'metaconfig.json',
            NOM + 'ports.json', NOM + 'updates.json'):
    try:
        data[nom] = json.loads(lire(nom))
        ok(nom, 'JSON valide')
    except Exception as e:
        soucis.append('%s : JSON invalide (%s)' % (nom, e))
if soucis:
    print('\n'.join('NON  ' + s for s in soucis))
    sys.exit(1)

config = data[NOM + 'config.json']
etapes = data[NOM + 'updates.json']
meta = data[NOM + 'metaconfig.json'][0]

# ── 2. kvp ───────────────────────────────────────────────────────────────────
kvp = lire(NOM + '.kvp')
cles = dict(l.split('=', 1) for l in kvp.splitlines() if '=' in l)
for ref in re.findall(r'@IncludeJson\[([^\]]+)\]', kvp):
    if os.path.isfile(os.path.join(ICI, ref)):
        ok('@IncludeJson', ref)
    else:
        soucis.append('@IncludeJson[%s] : fichier absent' % ref)
for cle in ('Meta.ConfigManifest', 'Meta.MetaConfigManifest'):
    if not os.path.isfile(os.path.join(ICI, cles.get(cle, '').strip())):
        soucis.append('%s pointe sur un fichier absent' % cle)

ATTENDUES = ['App.SupportsUniversalSleep', 'App.WakeupMode', 'App.ApplicationReadyMode',
             'Console.FilterMatchRegex', 'Console.FilterMatchReplacement',
             'Console.ThrowawayMessageRegex', 'Console.AppReadyRegex', 'Console.UserJoinRegex',
             'Console.UserLeaveRegex', 'Console.UserChatRegex', 'Console.UpdateAvailableRegex',
             'Console.PreConnectRegex', 'Console.ConnectIPRegex', 'Console.MetricsRegex',
             'Console.HideFromConsoleRegex', 'Console.SuppressLogAtStart', 'Console.UserActions',
             'Limits.SleepMode', 'Limits.SleepOnStart', 'Limits.SleepDelayMinutes',
             'Limits.DozeDelay', 'Limits.AutoRetryCount', 'Limits.SleepStartThresholdSeconds']
absentes = [c for c in ATTENDUES if c not in cles]
if absentes:
    soucis.append('clés absentes du .kvp : ' + ', '.join(absentes))
else:
    ok('kvp complet', 'les %d clés Console/Limits sont là' % len(ATTENDUES))
if cles.get('App.ApplicationReadyMode') == 'RegexMatch' and not cles.get('Console.AppReadyRegex'):
    soucis.append('ApplicationReadyMode=RegexMatch mais AppReadyRegex est vide')
if cles.get('App.ExitMethod') != 'OS_CLOSE':
    soucis.append('App.ExitMethod doit être OS_CLOSE : le serveur sauvegarde sur SIGTERM et n\'a pas de console en écriture')

# ── 3. ports ────────────────────────────────────────────────────────────────
refs = {p['Ref'] for p in data[NOM + 'ports.json']}
if cles.get('App.PrimaryApplicationPortRef') not in refs:
    soucis.append('PrimaryApplicationPortRef ne correspond à aucun port')
else:
    ok('port principal', cles['App.PrimaryApplicationPortRef'])
for p in data[NOM + 'ports.json']:
    if p['Protocol'] != 'TCP':
        soucis.append('Simutrans n\'utilise que TCP (SOCK_STREAM dans network.cc) : port %s en %s' % (p['Ref'], p['Protocol']))
for c in config:
    if c['FieldName'].startswith('$') and c['FieldName'][1:] not in refs:
        soucis.append('réglage %s : aucun port ne porte ce Ref' % c['FieldName'])

# ── 4. simuconf.tab livré ↔ réglages ─────────────────────────────────────────
tab = [e for e in etapes if e['UpdateSource'] == 'CreateFile' and e['UpdateSourceArgs'].endswith('simuconf.tab')]
if len(tab) != 1:
    soucis.append('il faut exactement une étape CreateFile pour simuconf.tab')
    tab = [{'UpdateSourceData': ''}]
elif tab[0].get('OverwriteExistingFiles') is not False:
    soucis.append('simuconf.tab ne doit jamais être écrasé par un Update')
if not meta['ConfigFile'].endswith('simuconf.tab'):
    soucis.append('le metaconfig ne pointe pas sur simuconf.tab')
motif = py(meta['ConfigFormatRegex'])
lues = {}
for ligne in tab[0]['UpdateSourceData'].split('\n'):
    if not ligne.strip() or ligne.startswith('#'):
        continue
    if ligne.startswith('-') or ligne.startswith(' '):
        soucis.append('ligne piège pour Simutrans (tiret = fin de lecture, espace = commentaire) : %r' % ligne)
    m = motif.match(ligne)
    if not m:
        soucis.append('la regex ne relit pas : %r' % ligne)
    else:
        lues[m.group('key')] = m.group('value')
exposes = [c['ParamFieldName'] for c in config if c.get('ParamFieldName')]
manquants = [p for p in exposes if p not in lues]
if manquants:
    soucis.append('réglages absents du simuconf.tab livré : ' + ', '.join(manquants))
else:
    ok('correspondance', '%d réglages, tous dans simuconf.tab' % len(exposes))
for c in config:
    p = c.get('ParamFieldName')
    if p and str(c.get('DefaultValue', '')) != lues.get(p):
        soucis.append('%s : défaut AMP %r, fichier livré %r' % (p, c.get('DefaultValue'), lues.get(p)))
# aller-retour : ce qu'AMP écrit avec ConfigFormat doit se relire à l'identique
for k, v in (('server_name', 'FR TeamKit - Simutrans'), ('server_dns', ''),
             ('server_comments', 'a = b, avec virgule'), ('server_announce', '1')):
    ecrit = meta['ConfigFormat'].replace('{0}', k).replace('{1}', v)
    m = motif.match(ecrit)
    if not m or m.group('key') != k or m.group('value') != v:
        soucis.append('aller-retour raté pour %r' % ecrit)
    else:
        ok('relecture', '%-24s -> %r' % (k, v))
vus = {}
for c in config:
    vus[c['FieldName']] = vus.get(c['FieldName'], 0) + 1
doubles = [f for f, n in vus.items() if n > 1]
if doubles:
    soucis.append('réglages en double : ' + ', '.join(doubles))

# ── 5. {{Réglages}} en ligne de commande ─────────────────────────────────────
champs = {c['FieldName'] for c in config}
utilises = set(re.findall(r'\{\{([A-Za-z]\w*)\}\}', cles.get('App.CommandLineArgs', '')))
for e in etapes:
    utilises |= set(re.findall(r'\{\{([A-Za-z]\w*)\}\}', e.get('UpdateSourceArgs', '')))
for u in sorted(utilises):
    if u not in champs:
        soucis.append('{{%s}} utilisé mais aucun réglage ne porte ce nom' % u)
for c in config:
    if not c.get('ParamFieldName') and not c['FieldName'].startswith('$') and c['FieldName'] not in utilises:
        soucis.append('réglage %s : ni écrit dans simuconf.tab, ni passé en ligne de commande' % c['FieldName'])
ok('ligne de commande', ', '.join(sorted(utilises)))

# ── 6. paksets proposés = paksets que installer.sh télécharge ────────────────
installer = lire('installer.sh')
pakset = next(c for c in config if c['FieldName'] == 'Pakset')
for valeur in pakset['EnumValues']:
    if not re.search(r'^\s*%s\)\s+PAK_URL=' % re.escape(valeur), installer, re.M):
        soucis.append('pakset %s proposé dans AMP mais inconnu de installer.sh' % valeur)
ok('paksets', ', '.join(pakset['EnumValues']))

# ── 7. scripts embarqués = scripts du dépôt ──────────────────────────────────
for fichier, cible in (('installer.sh', 'installer.sh'), ('lancer.sh', 'simutrans/lancer.sh')):
    e = [x for x in etapes if x['UpdateSource'] == 'CreateFile' and x['UpdateSourceArgs'].endswith(cible)]
    if len(e) != 1:
        soucis.append('aucune étape CreateFile pour %s' % cible)
        continue
    if e[0]['UpdateSourceData'] != lire(fichier).replace('\r\n', '\n'):
        soucis.append('%s du dépôt et sa copie dans %supdates.json diffèrent' % (fichier, NOM))
    elif e[0].get('OverwriteExistingFiles') is not True:
        soucis.append('%s doit être réécrit à chaque Update' % cible)
    else:
        ok('script embarqué', fichier)
    if '{{' in e[0]['UpdateSourceData']:
        soucis.append('%s contient {{ : AMP pourrait le remplacer' % fichier)
bash = shutil.which('bash')
if bash:
    for fichier in ('installer.sh', 'lancer.sh'):
        r = subprocess.run([bash, '-n', os.path.join(ICI, fichier)], capture_output=True, text=True)
        if r.returncode:
            soucis.append('syntaxe bash de %s : %s' % (fichier, r.stderr.strip()))
        else:
            ok('bash -n', fichier)
else:
    print('--   bash -n                  bash introuvable, syntaxe des scripts non vérifiée')

# ── 8. regex de console sur les vraies lignes ────────────────────────────────
# Lignes copiées telles quelles des journaux du 10 oct. 2026 (le séparateur
# après « : » est une tabulation, c'est le format de log_t::message).
VRAIES = {
    'pret':       'Message: simu_main():\tRunning world, pause=0, fast forward=0 ... ',
    'arrivee':    'Message: __ChatLog__:\tconnect,2,127.0.0.1,KevinTest',
    'depart':     'Message: __ChatLog__:\tdisconnect,2,127.0.0.1,KevinTest',
    'chat_serv1': 'Message: __ChatLog__:\tchat,0,0.0.0.0,Server#0,15,,KevinTest',
    'chat_serv2': 'Message: __ChatLog__:\tchat,0,0.0.0.0,Server#0,15,,',
    'bruit1':     'Message: network_command_t::rdwr:\twrite packet_id=NWC_STEP, client_id=0',
    'bruit2':     'Message: packet_t::send:\tsent 18 bytes to socket[5]; id=16, size=18',
    'bruit3':     'Message: karte_t::reset_timer():\tcalled, mode=$4',
    'join_pkt':   'Message: network_command_t::rdwr:\twrite packet_id=NWC_JOIN, client_id=0',
    'sauvegarde': "Message: karte_t::save:\tSaving game to 'server13353-network.sve', version=0.125.6, ticks=238341",
    'teamkit':    'TeamKit : demarrage de Simutrans -singleuser -server 13353 -objects pak -lang fr -debug 3',
}
# Une ligne de chat d'un JOUEUR n'a pas pu être produite (le client d'essai
# n'avait pas de clavier). Elle est construite ici d'après le code qui écrit
# les lignes ci-dessus (nwc_chat_t::execute, champs : chat, id client, ip,
# pseudo, n° de compagnie, nom de compagnie, message ; CSV_t met entre
# guillemets un champ qui contient une virgule).
CONSTRUITE = 'Message: __ChatLog__:\tchat,2,127.0.0.1,KevinTest,0,"Transports Kevin, Fils",salut, ca roule ?'

ESSAIS = [
    ('Console.AppReadyRegex', VRAIES['pret'], {}),
    ('Console.UserJoinRegex', VRAIES['arrivee'], {'userid': '2', 'username': 'KevinTest'}),
    ('Console.UserLeaveRegex', VRAIES['depart'], {'userid': '2', 'username': 'KevinTest'}),
    ('Console.UserChatRegex', CONSTRUITE, {'username': 'KevinTest', 'message': 'salut, ca roule ?'}),
]
for cle, ligne, attendu in ESSAIS:
    m = py(cles.get(cle, '^$')).search(ligne)
    if not m or any(m.group(k) != v for k, v in attendu.items()):
        soucis.append('%s ne reconnaît pas : %r' % (cle, ligne))
    else:
        ok(cle.split('.')[1], attendu or 'prêt')
NEGATIFS = [
    ('Console.UserChatRegex', VRAIES['chat_serv1'], 'le serveur qui relaie un message n\'est pas un joueur'),
    ('Console.UserChatRegex', VRAIES['chat_serv2'], 'idem, message vide'),
    ('Console.UserJoinRegex', VRAIES['depart'], 'un départ n\'est pas une arrivée'),
    ('Console.UserLeaveRegex', VRAIES['arrivee'], 'une arrivée n\'est pas un départ'),
    ('Console.AppReadyRegex', VRAIES['teamkit'], 'la ligne du script n\'est pas le serveur prêt'),
]
for cle, ligne, pourquoi in NEGATIFS:
    if py(cles[cle]).search(ligne):
        soucis.append('%s attrape à tort %r (%s)' % (cle, ligne, pourquoi))
jeter = py(cles['Console.ThrowawayMessageRegex'])
for k in ('bruit1', 'bruit2', 'bruit3'):
    if not jeter.search(VRAIES[k]):
        soucis.append('ThrowawayMessageRegex laisse passer le bruit %r' % VRAIES[k])
for k in ('pret', 'arrivee', 'depart', 'join_pkt', 'sauvegarde', 'teamkit'):
    if jeter.search(VRAIES[k]):
        soucis.append('ThrowawayMessageRegex jetterait une ligne utile : %r' % VRAIES[k])
ok('ThrowawayMessageRegex', 'jette 3 lignes de bruit, garde 6 lignes utiles')

# ── verdict ──────────────────────────────────────────────────────────────────
print()
if soucis:
    print('%d problème(s) :' % len(soucis))
    print('\n'.join('  NON  ' + s for s in soucis))
    sys.exit(1)
print('Tout est bon.')
