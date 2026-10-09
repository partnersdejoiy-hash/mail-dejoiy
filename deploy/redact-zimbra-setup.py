from pathlib import Path
p = Path('/opt/zimbra/libexec/zmsetup.pl')
s = p.read_text()
needle = 'sub detail {\n  my $msg = shift;'
assert needle in s
s = s.replace(needle, needle + r'''
  # Dmail deployment: suppress generated and supplied secrets in setup logs.
  foreach my $key (keys %config) {
    if ($key =~ /PASS|PASSWORD|PW$/i && defined $config{$key} && length($config{$key}) > 3) {
      my $secret = $config{$key};
      $msg =~ s/\Q$secret\E/[REDACTED]/g;
    }
  }
  $msg =~ s/((?:password|passwd|authToken)\s*(?:to|=|:)\s*)[^\s]+/${1}[REDACTED]/ig;
''')
p.write_text(s)
