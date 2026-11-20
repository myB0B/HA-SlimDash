#!/bin/sh
# Started by KUAL: detaches slimdash.sh (KUAL stops together with the Kindle interface).
S=/mnt/us/extensions/slimdash/bin/slimdash.sh
echo "$(date '+%d/%m %H:%M:%S') start.sh" >> /mnt/us/extensions/slimdash/slimdash.log
if command -v nohup >/dev/null 2>&1; then
    nohup /bin/sh $S </dev/null >/dev/null 2>&1 &
else
    /bin/sh $S </dev/null >/dev/null 2>&1 &
fi
