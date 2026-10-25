#!/bin/sh
set -eu

if [ "$(id -u)" -ne 0 ]; then
    printf 'Run this installer as root.\n' >&2
    exit 1
fi

cron_file=/etc/cron.d/bub-sf6-sync
runuser_bin=$(command -v runuser || true)
flock_bin=$(command -v flock || true)
sha256_bin=$(command -v sha256sum || true)
cut_bin=$(command -v cut || true)
systemctl_bin=$(command -v systemctl || true)
install_bin=$(command -v install || true)
mv_bin=$(command -v mv || true)
python_bin=/var/lib/bub/.venv/bin/python
sync_script=/var/lib/bub/scripts/sync_sf6_google_sheet.py
target=/var/lib/bub/FAT\ -\ SF6\ Frame\ Data.ods

for required in "$runuser_bin" "$flock_bin" "$sha256_bin" "$cut_bin" "$systemctl_bin" "$install_bin" "$mv_bin"; do
    if [ -z "$required" ] || [ ! -x "$required" ]; then
        printf 'Required executable is unavailable: %s\n' "$required" >&2
        exit 1
    fi
done
if ! id alwaly >/dev/null 2>&1; then
    printf 'Runtime user alwaly does not exist.\n' >&2
    exit 1
fi
if [ ! -x "$python_bin" ]; then
    printf 'Runtime Python is unavailable: %s\n' "$python_bin" >&2
    exit 1
fi
if [ ! -f "$sync_script" ] || [ ! -f "$target" ]; then
    printf 'SF6 sync input is missing: %s or %s\n' "$sync_script" "$target" >&2
    exit 1
fi

temporary_cron=$(mktemp /etc/cron.d/.bub-sf6-sync.XXXXXX)
trap 'rm -f "$temporary_cron" "$temporary_cron.ready"' EXIT HUP INT TERM
cat > "$temporary_cron" <<CRON
SHELL=/bin/sh
PATH=/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin
MAILTO=
CRON_TZ=UTC
15 4 * * * root $flock_bin -n /var/lib/bub/sf6-sync.lock /bin/sh -c 'target="/var/lib/bub/FAT - SF6 Frame Data.ods"; before=\$($sha256_bin "\$target" | $cut_bin -d " " -f 1); $runuser_bin -u alwaly -- $python_bin $sync_script --target "\$target" >>/var/lib/bub/sf6_sync.log 2>&1; status=\$?; if [ "\$status" -ne 0 ]; then exit "\$status"; fi; after=\$($sha256_bin "\$target" | $cut_bin -d " " -f 1); if [ "\$before" = "\$after" ]; then printf "\%s no workbook change; Bub restart skipped\\n" "\$(/bin/date -u +\%FT\%TZ)" >>/var/lib/bub/sf6_sync.log; exit 0; fi; $systemctl_bin restart bub >>/var/lib/bub/sf6_sync.log 2>&1'
CRON
$install_bin -o root -g root -m 0644 "$temporary_cron" "$temporary_cron.ready"
$mv_bin -f "$temporary_cron.ready" "$cron_file"
rm -f "$temporary_cron"
trap - EXIT HUP INT TERM
printf 'Installed %s\n' "$cron_file"
