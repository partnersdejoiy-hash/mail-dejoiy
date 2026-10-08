"""Restore Log4j 1 API compatibility using Apache's Log4j 2 bridge."""
from pathlib import Path
import hashlib, urllib.request, os
version='2.17.1'  # Match this pinned Zimbra build's log4j-api and log4j-core.
name=f'log4j-1.2-api-{version}.jar'
url=f'https://repo.maven.apache.org/maven2/org/apache/logging/log4j/log4j-1.2-api/{version}/{name}'
data=urllib.request.urlopen(url,timeout=30).read()
expected=urllib.request.urlopen(url+'.sha1',timeout=30).read().decode().strip()
assert hashlib.sha1(data).hexdigest()==expected, 'Apache artifact checksum mismatch'
for directory in ['/opt/zimbra/lib/jars','/opt/zimbra/jetty_base/common/lib']:
 path=Path(directory)/name
 path.write_bytes(data);os.chmod(path,0o444)
print(name, 'SHA256', hashlib.sha256(data).hexdigest())
