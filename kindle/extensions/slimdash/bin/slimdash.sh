#!/bin/sh
# SlimDash pour Kindle 4 (sans tactile, firmware 4.1.x, jailbreaké).
# Affiche en plein écran l'image d'une vue SlimDash (type 0 : /<dashboard>.png) et la
# met à jour toutes les INTERVAL secondes. L'interface du Kindle est arrêtée pendant
# l'affichage (plein écran, pas d'économiseur d'écran) ; elle revient à l'arrêt.
#
# Arrêt : touche Accueil (les autres sont ignorées). À défaut : bouton marche maintenu 20 s (redémarrage).

DIR=/mnt/us/extensions/slimdash
TMP=/tmp/slimdash
LOG=$DIR/slimdash.log
PIDF=$TMP/slimdash.pid
mkdir -p $TMP

log() {
    echo "$(date '+%d/%m %H:%M:%S') $*" >> $LOG
}

# Réglages (fichier édité sous Windows : on retire les fins de ligne CR).
URL=""
NTP=""
INTERVAL=60
FULL_EVERY=10
sed 's/\r$//' $DIR/slimdash.conf > $TMP/conf 2>/dev/null && . $TMP/conf
[ "$INTERVAL" -ge 10 ] 2>/dev/null || INTERVAL=60
[ "$FULL_EVERY" -ge 1 ] 2>/dev/null || FULL_EVERY=10

# Une seule instance.
if [ -f $PIDF ] && kill -0 "$(cat $PIDF)" 2>/dev/null; then
    exit 0
fi
echo $$ > $PIDF

# Journal limité à ~100 Ko.
if [ -f $LOG ] && [ "$(wc -c < $LOG)" -gt 100000 ]; then
    tail -n 200 $LOG > $TMP/log && mv $TMP/log $LOG
fi
log "démarrage : $URL toutes les $INTERVAL s"

if [ -z "$URL" ]; then
    eips -c
    eips 2 10 "SlimDash : adresse absente."
    eips 2 12 "Renseignez URL dans slimdash.conf"
    rm -f $PIDF
    exit 1
fi

# Plus d'économiseur d'écran, interface arrêtée (libère l'écran).
lipc-set-prop com.lab126.powerd preventScreenSaver 1
/etc/init.d/framework stop >/dev/null 2>&1
sleep 2
lipc-set-prop com.lab126.powerd preventScreenSaver 1
lipc-set-prop com.lab126.wifid enable 1 2>/dev/null
eips -c
eips 2 18 "SlimDash : connexion..."

# Arrêt par la touche Accueil (code 102) : lecture directe des événements clavier
# (/dev/input/event*). Le Kindle 4 n'a ni waitforkey ni od : les octets sont lus avec dd.
# Événement Linux 32 bits = 16 octets : temps (8), type (2), code (2), valeur (4).
STOPKEY=102
ONE=$(printf '\001')
STOPCH=$(printf "\\$(printf %o $STOPKEY)")
byte() {        # octet n° $2 du fichier $1 (vide pour 0 ou 10)
    dd if="$1" bs=1 skip="$2" count=1 2>/dev/null
}
code() {        # valeur décimale d'un octet (pour le journal), sans od
    c=$(byte "$1" "$2")
    [ -z "$c" ] && { echo 0; return; }
    i=1
    while [ $i -lt 256 ]; do
        [ "$c" = "$(printf "\\$(printf %o $i)")" ] && { echo $i; return; }
        i=$((i + 1))
    done
    echo "?"
}
WATCH=""
for dev in /dev/input/event*; do
    [ -e "$dev" ] || continue
    (
        f=$TMP/key.${dev##*/}
        while [ -f $PIDF ]; do
            rm -f $f
            # Une lecture rend tous les événements en attente (10 au plus).
            dd if=$dev of=$f bs=160 count=1 2>/dev/null
            [ -f $PIDF ] || break
            n=$(wc -c < $f 2>/dev/null)
            [ -n "$n" ] || n=16
            o=0
            while [ $((o + 16)) -le "$n" ]; do
                # type 1 (touche) et valeur 1 (appui)
                if [ "$(byte $f $((o + 8)))" = "$ONE" ] && [ "$(byte $f $((o + 12)))" = "$ONE" ]; then
                    if [ "$(byte $f $((o + 10)))" = "$STOPCH" ] && [ -z "$(byte $f $((o + 11)))" ]; then
                        log "touche Accueil : arrêt"
                        rm -f $PIDF
                    else
                        log "touche $(code $f $((o + 10))) ($dev) ignorée"
                    fi
                fi
                o=$((o + 16))
            done
        done
    ) &
    WATCH="$WATCH $!"
done

# Attente du Wi-Fi (2 min au plus).
i=0
while [ $i -lt 24 ] && [ -f $PIDF ]; do
    st=$(lipc-get-prop com.lab126.wifid cmState 2>/dev/null)
    [ "$st" = "CONNECTED" ] && break
    sleep 5
    i=$((i + 1))
done
log "Wi-Fi : ${st:-inconnu}"

# Mise à l'heure (l'interface arrêtée ne le fait plus) sur le serveur NTP réglé dans
# slimdash.conf (NTP=...) : ntpd de busybox, sinon ntpdate.
settime() {
    [ -n "$NTP" ] || return 0
    before=$(date +%s)
    if ntpd -q -n -p "$NTP" >/dev/null 2>&1 || ntpdate -u "$NTP" >/dev/null 2>&1; then
        log "heure réglée sur $NTP (écart $(( $(date +%s) - before )) s)"
        hwclock -w 2>/dev/null
    else
        log "mise à l'heure impossible sur $NTP (ntpd et ntpdate absents ou serveur injoignable)"
    fi
}
settime
lastset=$(date +%s)

n=0
fails=0
last=""
while [ -f $PIDF ]; do
    rm -f $TMP/new.png
    if wget -q -O $TMP/new.png "$URL" 2>/dev/null && [ -s $TMP/new.png ]; then
        sum=$(md5sum $TMP/new.png | cut -d' ' -f1)
        if [ "$sum" != "$last" ] || [ $fails -ge 3 ]; then
            n=$((n + 1))
            if [ $n -ge $FULL_EVERY ] || [ $fails -ge 3 ]; then
                eips -c             # rafraîchissement complet : efface les traces
                n=0
            fi
            eips -g $TMP/new.png
            last=$sum
        fi
        fails=0
    else
        fails=$((fails + 1))
        log "échec du téléchargement ($fails)"
        if [ $fails -eq 3 ]; then
            eips 1 38 "SlimDash injoignable - nouvel essai...   "
            lipc-set-prop com.lab126.wifid enable 0 2>/dev/null
            sleep 3
            lipc-set-prop com.lab126.wifid enable 1 2>/dev/null
        fi
    fi
    lipc-set-prop com.lab126.powerd preventScreenSaver 1 2>/dev/null
    # Attente calée sur l'horloge : prochain multiple de INTERVAL (pile à la minute pour 60),
    # + 2 s pour que l'heure du serveur ait bien changé. Tranches de 5 s au plus : la touche
    # d'arrêt agit vite.
    now=$(date +%s 2>/dev/null)
    if [ $((now - lastset)) -gt 86400 ] 2>/dev/null; then     # remise à l'heure chaque jour
        settime
        lastset=$(date +%s)
        now=$lastset
    fi
    if [ -n "$now" ] && [ "$now" -gt 1000000000 ] 2>/dev/null; then
        next=$(( (now / INTERVAL + 1) * INTERVAL + 2 ))
        while [ "$now" -lt "$next" ] && [ -f $PIDF ]; do
            s=$((next - now))
            [ $s -gt 5 ] && s=5
            sleep $s
            now=$(date +%s)
        done
    else
        t=0
        while [ $t -lt $INTERVAL ] && [ -f $PIDF ]; do
            sleep 5
            t=$((t + 5))
        done
    fi
done

# Arrêt : retour à l'interface normale du Kindle.
log "arrêt"
[ -n "$WATCH" ] && kill $WATCH 2>/dev/null
killall dd 2>/dev/null
lipc-set-prop com.lab126.powerd preventScreenSaver 0 2>/dev/null
eips -c
eips 2 18 "SlimDash arrete. Retour au Kindle..."
/etc/init.d/framework start >/dev/null 2>&1
rm -f $PIDF
