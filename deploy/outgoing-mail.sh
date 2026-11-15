#!/usr/bin/env bash
# Which mail leaves through Dejoiy's own Amazon SES. Run as root on the mail server.
#
#   bash outgoing-mail.sh --status   what happens today (changes nothing)
#   bash outgoing-mail.sh --switch   SES only for Dejoiy's domains and the ones a super admin promoted;
#                                    every other domain sends straight from this server (asks first)
#   bash outgoing-mail.sh --undo     back to SES for every domain
#   bash outgoing-mail.sh            (cron, every 2 minutes) refresh the list after a promote/demote
#
# The app writes the list (LIST): "*.dejoiy.com" = that domain and all its subdomains, else one domain per line.
# The SES user name and password stay where they already are (the mail system's SASL table, keyed by the
# SES host), so nothing secret is asked for or written here.
set -uo pipefail
LIST=${SES_DOMAINS_FILE:-/var/lib/dmail/ses-domains.txt}
STATE=/etc/dmail/ses-relay            # saved at --switch: the SES next hop and Zimbra's old relay setting
MAP=/opt/zimbra/conf/dmail_ses_senders
zsu() { su - zimbra -c "$1"; }
die() { echo "$*" >&2; exit 1; }
[ "$(id -u)" = 0 ] || die "Run as root."
[ -x /opt/zimbra/bin/zmprov ] || die "Zimbra not found on this machine."

# the Zimbra attribute behind a Postfix setting, when this Zimbra version manages that setting (else empty)
attr_for() { awk -v k="$1" '$1=="POSTCONF" && $2==k {for(i=3;i<=NF;i++) if($i ~ /^zimbra/) {print $i; exit}}' /opt/zimbra/conf/zmconfigd.cf 2>/dev/null; }

build_map() {   # writes MAP from LIST; prints "changed" when it did
  local relay=$1 tmp all line d
  tmp=$(mktemp); all=$(zsu "zmprov -l gad" 2>/dev/null | tr 'A-Z' 'a-z')
  if [ -f "$LIST" ]; then
    while IFS= read -r line; do
      line=$(echo "$line" | tr 'A-Z' 'a-z' | tr -d ' \r')
      case "$line" in
        \*.*) d=${line#*.}; [[ "$d" =~ ^[a-z0-9.-]+$ ]] || continue
              echo "@$d $relay" >> "$tmp"
              echo "$all" | grep -E "\.${d//./\\.}$" | sed "s/^/@/; s/$/ $relay/" >> "$tmp" ;;
        *)    [[ "$line" =~ ^[a-z0-9]([a-z0-9.-]*[a-z0-9])?\.[a-z]{2,}$ ]] && echo "@$line $relay" >> "$tmp" ;;
      esac
    done < "$LIST"
  else
    echo "@dejoiy.com $relay" >> "$tmp"
  fi
  sort -u "$tmp" -o "$tmp"
  if [ -f "$MAP" ] && cmp -s "$tmp" "$MAP"; then rm -f "$tmp"; return 0; fi
  install -o zimbra -g zimbra -m 0644 "$tmp" "$MAP"; rm -f "$tmp"
  zsu "postmap lmdb:$MAP" && echo changed
}

status() {
  echo "Global relay (all mail):   '$(zsu 'postconf -h relayhost')'"
  echo "Per-sender relay table:    '$(zsu 'postconf -h sender_dependent_relayhost_maps')'"
  [ -f "$MAP" ] && { echo "Domains through SES:"; sed 's/^/  /' "$MAP"; }
  [ -f "$STATE" ] && echo "Switched on $(stat -c %y "$STATE" | cut -d. -f1)." || echo "Not switched: every domain goes through SES."
}

case "${1:-}" in
  --status) status ;;

  --switch)
    relay=$(zsu "postconf -h relayhost")
    [ -f "$STATE" ] && [ -z "$relay" ] && { echo "Already switched."; status; exit 0; }
    [ -n "$relay" ] || die "No global relay is set, so nothing goes through SES today. Nothing to switch."
    old_attr=$(zsu "zmprov gcf zimbraMtaRelayHost" | awk -F': ' 'NR==1{print $2}')
    echo "Today every domain leaves through: $relay"
    echo "== Can this server deliver to Gmail and Outlook itself (port 25 out)?"
    ok=1
    for mx in gmail-smtp-in.l.google.com outlook-com.olc.protection.outlook.com; do
      greet=$(timeout 10 bash -c "exec 3<>/dev/tcp/$mx/25 && head -c 3 <&3" 2>/dev/null || true)
      [ "$greet" = 220 ] && echo "  $mx: yes" || { echo "  $mx: NO"; ok=0; }
    done
    [ "$ok" = 1 ] || die "Port 25 out is blocked here, so mail would pile up. Ask the hosting company to open it, then run this again. Nothing changed."
    ip=$(curl -fsS4 --max-time 5 https://api.ipify.org || hostname -I | awk '{print $1}')
    ptr=$(getent hosts "$ip" | awk '{print $2}')
    echo "  Reverse DNS of $ip: ${ptr:-none}"
    [ -n "$ptr" ] || echo "  WARNING: set reverse DNS (PTR) of $ip to $(zsu 'zmhostname') at the hosting company, or Gmail will mark this server's mail as spam."
    echo
    echo "After this, only these keep SES:"; [ -f "$LIST" ] && sed 's/^/  /' "$LIST" || echo "  *.dejoiy.com"
    echo "Every other company's mail goes straight from $ip (or through its Swiss Mail add-on / own service when set)."
    read -r -p "Switch now? Type yes: " answer; [ "$answer" = yes ] || die "Nothing changed."
    install -d -m 0700 /etc/dmail
    printf 'RELAY=%s\nOLD_ATTR=%s\n' "$relay" "$old_attr" > "$STATE"; chmod 600 "$STATE"
    build_map "$relay" >/dev/null || die "Could not build $MAP. Nothing else changed."
    [ "$(zsu "postmap -q '@dejoiy.com' lmdb:$MAP")" = "$relay" ] || die "The table does not answer for dejoiy.com. Nothing else changed."
    a=$(attr_for sender_dependent_relayhost_maps)
    if [ -n "$a" ]; then zsu "zmprov mcf $a lmdb:$MAP"; else zsu "postconf -e sender_dependent_relayhost_maps=lmdb:$MAP"; fi
    zsu "zmprov mcf zimbraMtaRelayHost ''"; zsu "zmprov ms \$(zmhostname) zimbraMtaRelayHost ''"
    [ -z "$a" ] && zsu "postconf -e relayhost="
    zsu "zmmtactl reload" >/dev/null
    for i in $(seq 1 30); do [ -z "$(zsu 'postconf -h relayhost')" ] && break; sleep 3; done
    status
    [ -z "$(zsu 'postconf -h relayhost')" ] || echo "The global relay is still set; wait a minute and run --status. Undo: bash $0 --undo"
    [ -n "$a" ] || echo "Note: this Zimbra keeps the per-sender table in main.cf only; run this script again after a Zimbra upgrade."
    echo "Done. Send a test from a dejoiy.com mailbox and from another company's mailbox to Gmail, then open 'Show original'."
    ;;

  --undo)
    [ -f "$STATE" ] || die "Not switched; nothing to undo."
    # shellcheck disable=SC1090
    . "$STATE"
    a=$(attr_for sender_dependent_relayhost_maps)
    zsu "zmprov mcf zimbraMtaRelayHost '${OLD_ATTR:-$RELAY}'"
    if [ -n "$a" ]; then zsu "zmprov mcf $a ''"; else zsu "postconf -e sender_dependent_relayhost_maps= relayhost=$RELAY"; fi
    zsu "zmmtactl reload" >/dev/null
    mv "$STATE" "$STATE.undone.$(date +%s)"
    status ;;

  "")
    [ -f "$STATE" ] || exit 0   # not switched yet: SES still carries everything
    # shellcheck disable=SC1090
    . "$STATE"
    [ "$(build_map "$RELAY")" = changed ] && echo "$(date -Is) SES list updated: $(wc -l < "$MAP") domains"
    exit 0 ;;

  *) die "Use --status, --switch, --undo or no argument." ;;
esac
