#!/usr/bin/env bash
# Dmail Zimbra overrides: keep our mail-delivery rules in place across
# zmconfigd rewrites and Zimbra upgrades.
#
#   sudo bash apply.sh            install files + include line (idempotent)
#   sudo bash apply.sh --check    verify everything, exit 1 on drift
#   sudo bash apply.sh --check --notify   same, and mail admin on drift
#
# apply never restarts services. After it changes something it prints the
# one restart needed. Run it again after every Zimbra upgrade.
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ZCONF=/opt/zimbra/conf
TEMPLATE="$ZCONF/amavisd.conf.in"
LIVE="$ZCONF/amavisd.conf"
OVR="$ZCONF/dmail-amavis-overrides.conf"
TPLDIR="$ZCONF/dmail-templates"
MARK='# DMAIL-OVERRIDE'
INCLUDE="include_config_files('$OVR');  $MARK"
NOTIFY_TO="${DMAIL_OVERRIDES_NOTIFY:-admin@corp.dejoiy.com}"

# Expected Zimbra settings (LDAP / localconfig, upgrade-safe by themselves;
# checked here so drift is noticed).
EXPECT_GCF=( "zimbraVirusBlockEncryptedArchive=FALSE" )
EXPECT_GS=( "zimbraMtaDelayWarningTime=4h" "zimbraMtaMaximalQueueLifetime=3d" "zimbraMtaBounceQueueLifetime=3d" )
EXPECT_LC=( "smtp_source=admin@corp.dejoiy.com" "smtp_destination=admin@corp.dejoiy.com" )

zsu() { su - zimbra -c "$1"; }

install_file() { # src dst -> echo "changed" if content differed
  local src="$1" dst="$2"
  if [ -f "$dst" ] && cmp -s "$src" "$dst"; then return 0; fi
  install -o zimbra -g zimbra -m 0644 "$src" "$dst"
  echo "changed"
}

do_apply() {
  [ "$(id -u)" = 0 ] || { echo "run as root" >&2; exit 2; }
  local changed=""
  install -d -o zimbra -g zimbra -m 0755 "$TPLDIR"
  changed+=$(install_file "$HERE/dmail-amavis-overrides.conf" "$OVR")
  changed+=$(install_file "$HERE/templates/sender-blocked.txt" "$TPLDIR/sender-blocked.txt")
  if ! grep -qF "$MARK" "$TEMPLATE"; then
    cp -p "$TEMPLATE" "$TEMPLATE.dmail-backup.$(date +%Y%m%d%H%M%S)"
    # insert before the final "1;" line of the template
    awk -v inc="$INCLUDE" '
      { lines[NR]=$0 } END {
        last=0; for (i=NR;i>0;i--) if (lines[i] ~ /^1;/) { last=i; break }
        if (!last) { print "no final 1; line" > "/dev/stderr"; exit 3 }
        for (i=1;i<=NR;i++) { if (i==last) print inc; print lines[i] }
      }' "$TEMPLATE" > "$TEMPLATE.dmail-new"
    chown --reference="$TEMPLATE" "$TEMPLATE.dmail-new"
    chmod --reference="$TEMPLATE" "$TEMPLATE.dmail-new"
    mv "$TEMPLATE.dmail-new" "$TEMPLATE"
    changed+="changed"
  fi
  if [ -n "$changed" ]; then
    echo "Overrides installed. Validate, then restart amavis:"
    echo "  sudo bash $HERE/apply.sh --check"
    echo "  su - zimbra -c 'zmamavisdctl restart'   # rewrites amavisd.conf from the template"
  else
    echo "Overrides already in place; nothing changed."
  fi
}

do_check() {
  local problems=()
  [ -f "$OVR" ] && cmp -s "$HERE/dmail-amavis-overrides.conf" "$OVR" || problems+=("$OVR missing or differs from repo")
  [ -f "$TPLDIR/sender-blocked.txt" ] && cmp -s "$HERE/templates/sender-blocked.txt" "$TPLDIR/sender-blocked.txt" || problems+=("bounce template missing or differs")
  grep -qF "$MARK" "$TEMPLATE" || problems+=("include line missing in amavisd.conf.in (Zimbra upgrade?)")
  grep -qF "$MARK" "$LIVE"     || problems+=("include line missing in live amavisd.conf (restart amavis)")
  # amavis must be able to load the full config (parses overrides + template)
  if ! zsu "/opt/zimbra/common/sbin/amavisd -X no_conf_file_writable_check -c $LIVE showkeys" >/dev/null 2>&1; then
    problems+=("amavisd cannot load $LIVE (config error)")
  fi
  local kv k v got
  for kv in "${EXPECT_GCF[@]}"; do k=${kv%%=*}; v=${kv#*=}
    got=$(zsu "zmprov -l gcf $k" | awk -F': ' 'NR==1{print $2}'); [ "$got" = "$v" ] || problems+=("global $k is '$got', expected '$v'"); done
  for kv in "${EXPECT_GS[@]}"; do k=${kv%%=*}; v=${kv#*=}
    got=$(zsu "zmprov -l gs \$(zmhostname) $k" | awk -F': ' '/: /{print $2; exit}'); [ "$got" = "$v" ] || problems+=("server $k is '$got', expected '$v'"); done
  for kv in "${EXPECT_LC[@]}"; do k=${kv%%=*}; v=${kv#*=}
    got=$(zsu "zmlocalconfig -m nokey $k"); [ "$got" = "$v" ] || problems+=("localconfig $k is '$got', expected '$v'"); done

  if [ ${#problems[@]} -eq 0 ]; then echo "OK: all Dmail Zimbra overrides in place."; return 0; fi
  printf 'DRIFT: %s\n' "${problems[@]}"
  if [ "${NOTIFY:-0}" = 1 ]; then
    { echo "From: Dmail server check <admin@corp.dejoiy.com>"
      echo "To: $NOTIFY_TO"
      echo "Subject: Dmail mail-delivery settings drifted on $(hostname)"
      echo; echo "Daily check found problems (bounce/quarantine rules may be off):"; echo
      printf -- '- %s\n' "${problems[@]}"; echo
      echo "Fix: sudo bash $HERE/apply.sh && su - zimbra -c 'zmamavisdctl restart'"
    } | /opt/zimbra/common/sbin/sendmail -f admin@corp.dejoiy.com "$NOTIFY_TO"
  fi
  return 1
}

case "${1:-}" in
  --check) [ "${2:-}" = --notify ] && NOTIFY=1; do_check ;;
  ""|--apply) do_apply ;;
  *) echo "usage: $0 [--check [--notify]]" >&2; exit 2 ;;
esac
