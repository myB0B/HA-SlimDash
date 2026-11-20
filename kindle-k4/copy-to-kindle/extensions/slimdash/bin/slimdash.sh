#!/bin/sh
# SlimDash for Kindle 4 (non-touch, firmware 4.1.x, jailbroken).
# Shows the image of a SlimDash view full screen (type 0: /<dashboard>.png) and refreshes it
# every INTERVAL seconds. The Kindle interface is stopped while displaying
# (full screen, no screensaver); it comes back when SlimDash stops.
#
# Stop: Home key (other keys are ignored). Otherwise: hold the power button for 20 s (restart).

DIR=/mnt/us/extensions/slimdash
TMP=/tmp/slimdash
LOG=$DIR/slimdash.log
PIDF=$TMP/slimdash.pid
mkdir -p $TMP

log() {
    echo "$(date '+%d/%m %H:%M:%S') $*" >> $LOG
}

# Settings (file edited on Windows: strip the CR line endings).
URL=""
NTP=""
INTERVAL=60
FULL_EVERY=10
sed 's/\r$//' $DIR/slimdash.conf > $TMP/conf 2>/dev/null && . $TMP/conf
[ "$INTERVAL" -ge 10 ] 2>/dev/null || INTERVAL=60
[ "$FULL_EVERY" -ge 1 ] 2>/dev/null || FULL_EVERY=10

# Single instance.
if [ -f $PIDF ] && kill -0 "$(cat $PIDF)" 2>/dev/null; then
    exit 0
fi
echo $$ > $PIDF

# Log limited to ~100 KB.
if [ -f $LOG ] && [ "$(wc -c < $LOG)" -gt 100000 ]; then
    tail -n 200 $LOG > $TMP/log && mv $TMP/log $LOG
fi
log "start: $URL every $INTERVAL s"

if [ -z "$URL" ]; then
    eips -c
    eips 2 10 "SlimDash: address missing."
    eips 2 12 "Set URL in slimdash.conf"
    rm -f $PIDF
    exit 1
fi

# No more screensaver, interface stopped (frees the screen).
lipc-set-prop com.lab126.powerd preventScreenSaver 1
/etc/init.d/framework stop >/dev/null 2>&1
sleep 2
lipc-set-prop com.lab126.powerd preventScreenSaver 1
lipc-set-prop com.lab126.wifid enable 1 2>/dev/null
eips -c
eips 2 18 "SlimDash: connecting..."

# Stop with the Home key (code 102): direct reading of the keyboard events
# (/dev/input/event*). The Kindle 4 has neither waitforkey nor od: bytes are read with dd.
# 32-bit Linux event = 16 bytes: time (8), type (2), code (2), value (4).
STOPKEY=102
ONE=$(printf '\001')
STOPCH=$(printf "\\$(printf %o $STOPKEY)")
byte() {        # byte number $2 of file $1 (empty for 0 or 10)
    dd if="$1" bs=1 skip="$2" count=1 2>/dev/null
}
code() {        # decimal value of a byte (for the log), without od
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
            # One read returns all the pending events (10 at most).
            dd if=$dev of=$f bs=160 count=1 2>/dev/null
            [ -f $PIDF ] || break
            n=$(wc -c < $f 2>/dev/null)
            [ -n "$n" ] || n=16
            o=0
            while [ $((o + 16)) -le "$n" ]; do
                # type 1 (key) and value 1 (press)
                if [ "$(byte $f $((o + 8)))" = "$ONE" ] && [ "$(byte $f $((o + 12)))" = "$ONE" ]; then
                    if [ "$(byte $f $((o + 10)))" = "$STOPCH" ] && [ -z "$(byte $f $((o + 11)))" ]; then
                        log "Home key: stop"
                        rm -f $PIDF
                    else
                        log "key $(code $f $((o + 10))) ($dev) ignored"
                    fi
                fi
                o=$((o + 16))
            done
        done
    ) &
    WATCH="$WATCH $!"
done

# Wait for Wi-Fi (2 min at most).
i=0
while [ $i -lt 24 ] && [ -f $PIDF ]; do
    st=$(lipc-get-prop com.lab126.wifid cmState 2>/dev/null)
    [ "$st" = "CONNECTED" ] && break
    sleep 5
    i=$((i + 1))
done
log "Wi-Fi: ${st:-unknown}"

# Set the clock (the stopped interface no longer does it) from the NTP server set in
# slimdash.conf (NTP=...): busybox ntpd, otherwise ntpdate.
settime() {
    [ -n "$NTP" ] || return 0
    before=$(date +%s)
    if ntpd -q -n -p "$NTP" >/dev/null 2>&1 || ntpdate -u "$NTP" >/dev/null 2>&1; then
        log "clock set from $NTP (offset $(( $(date +%s) - before )) s)"
        hwclock -w 2>/dev/null
    else
        log "cannot set the clock from $NTP (no ntpd or ntpdate, or server unreachable)"
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
                eips -c             # full refresh: removes ghosting
                n=0
            fi
            eips -g $TMP/new.png
            last=$sum
        fi
        fails=0
    else
        fails=$((fails + 1))
        log "download failed ($fails)"
        if [ $fails -eq 3 ]; then
            eips 1 38 "SlimDash unreachable - retrying...   "
            lipc-set-prop com.lab126.wifid enable 0 2>/dev/null
            sleep 3
            lipc-set-prop com.lab126.wifid enable 1 2>/dev/null
        fi
    fi
    lipc-set-prop com.lab126.powerd preventScreenSaver 1 2>/dev/null
    # Wait aligned on the clock: next multiple of INTERVAL (exactly on the minute for 60),
    # + 2 s so that the server time has really changed. Slices of 5 s at most: the stop key
    # reacts quickly.
    now=$(date +%s 2>/dev/null)
    if [ $((now - lastset)) -gt 86400 ] 2>/dev/null; then     # set the clock again every day
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

# Stop: back to the normal Kindle interface.
log "stop"
[ -n "$WATCH" ] && kill $WATCH 2>/dev/null
killall dd 2>/dev/null
lipc-set-prop com.lab126.powerd preventScreenSaver 0 2>/dev/null
eips -c
eips 2 18 "SlimDash stopped. Back to Kindle..."
/etc/init.d/framework start >/dev/null 2>&1
rm -f $PIDF
