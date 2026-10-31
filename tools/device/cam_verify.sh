cd /tmp
rm -f verify.raw verify.png
timeout 120 /usr/local/bin/tablet-cam /tmp/verify.raw 2>&1 | tail -n 5
ls -l /tmp/verify.raw /tmp/verify.png 2>/dev/null
