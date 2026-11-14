"""Passkeys for Dejoiy Mail: a second step after the password, done with the phone's or computer's own
lock (fingerprint, face, PIN). This is WebAuthn; the device holds a private key that never leaves it,
and this server keeps only the public half.

How it fits sign-in:
  1. the password is checked by the mail server as always;
  2. when the mailbox has a passkey, no session is made yet: the browser is sent a challenge;
  3. the device signs the challenge after the person unlocks it; the signature is checked here.
Lost the device? One of ten one-time recovery codes (shown once, when the first passkey is added)
works instead, and a company admin can remove a person's passkeys.

Stands alone (standard library only). Signatures are checked here for the two kinds every phone and
computer offers: ES256 (ECDSA P-256) and RS256. Checking a signature uses public values only.
    keys = Passkeys(store)                      # store: get(email) -> dict, put(email, dict)
    options, state = keys.register_options(email, name, rp_id)
    keys.register(email, state, credential, origin, label)   -> {'codes': [...]} on the first one
    options, state = keys.login_options(email, rp_id)        -> (None, None) when the step is not needed
    keys.login(email, state, assertion, origin)  /  keys.use_code(email, code)
"""
import base64, hashlib, hmac, json, secrets, struct, time

MAX_KEYS = 10
CODES = 10


class PasskeyError(ValueError):
    """Safe to show to the person signing in or setting up."""


def b64(raw): return base64.urlsafe_b64encode(raw).rstrip(b'=').decode()
def unb64(text):
    if not isinstance(text, str) or len(text) > 20000: raise PasskeyError('That passkey answer could not be read. Try again.')
    try: return base64.urlsafe_b64decode(text + '=' * (-len(text) % 4))
    except (ValueError, TypeError): raise PasskeyError('That passkey answer could not be read. Try again.')


# ---- CBOR: just enough to read what an authenticator sends (ints, bytes, text, lists, maps) ----
def cbor(data, at=0):
    """Reads one CBOR item. Returns (value, next position)."""
    try:
        first = data[at]; major, info = first >> 5, first & 31; at += 1
        if info < 24: n = info
        elif info in (24, 25, 26, 27):
            size = 1 << (info - 24); n = int.from_bytes(data[at:at + size], 'big'); at += size
            if len(data) < at: raise IndexError
        else: raise PasskeyError('That passkey could not be read.')
        if major == 0: return n, at
        if major == 1: return -1 - n, at
        if major in (2, 3):
            if n > len(data) - at: raise IndexError
            raw = bytes(data[at:at + n]); return (raw if major == 2 else raw.decode()), at + n
        if major == 4:
            out = []
            for _ in range(min(n, 64)): item, at = cbor(data, at); out.append(item)
            return out, at
        if major == 5:
            out = {}
            for _ in range(min(n, 64)):
                key, at = cbor(data, at); value, at = cbor(data, at)
                if isinstance(key, (int, str)): out[key] = value
            return out, at
    except (IndexError, UnicodeDecodeError, RecursionError): pass
    raise PasskeyError('That passkey could not be read.')


# ---- ES256: ECDSA over P-256 with SHA-256 (verification only: public values, no secrets) ----
P = 0xFFFFFFFF00000001000000000000000000000000FFFFFFFFFFFFFFFFFFFFFFFF
N = 0xFFFFFFFF00000000FFFFFFFFFFFFFFFFBCE6FAADA7179E84F3B9CAC2FC632551
B = 0x5AC635D8AA3A93E7B3EBBD55769886BC651D06B0CC53B0F63BCE3C3E27D2604B
G = (0x6B17D1F2E12C4247F8BCE6E563A440F277037D812DEB33A0F4A13945D898C296, 0x4FE342E2FE1A7F9B8EE7EB4A7C0F9E162BCE33576B315ECECBB6406837BF51F5)

def _add(a, b):
    if a is None: return b
    if b is None: return a
    if a[0] == b[0]:
        if (a[1] + b[1]) % P == 0: return None
        slope = (3 * a[0] * a[0] - 3) * pow(2 * a[1], -1, P) % P
    else: slope = (b[1] - a[1]) * pow(b[0] - a[0], -1, P) % P
    x = (slope * slope - a[0] - b[0]) % P
    return x, (slope * (a[0] - x) - a[1]) % P

def _mul(k, point):
    out = None
    while k:
        if k & 1: out = _add(out, point)
        point = _add(point, point); k >>= 1
    return out

def on_curve(x, y): return 0 < x < P and 0 < y < P and (y * y - (x * x * x - 3 * x + B)) % P == 0

def der_pair(sig):
    """The two numbers of an ECDSA signature in DER form (SEQUENCE of two INTEGERs)."""
    try:
        if sig[0] != 0x30: raise ValueError
        at = 2 + (sig[1] & 0x7f if sig[1] & 0x80 else 0); out = []
        for _ in range(2):
            if sig[at] != 0x02: raise ValueError
            size = sig[at + 1]; out.append(int.from_bytes(sig[at + 2:at + 2 + size], 'big')); at += 2 + size
        if at != len(sig): raise ValueError
        return out
    except (IndexError, ValueError): raise PasskeyError('That passkey answer is not valid.')

def verify_es256(x, y, message, sig):
    r, s = der_pair(sig)
    if not (0 < r < N and 0 < s < N) or not on_curve(x, y): return False
    z = int.from_bytes(hashlib.sha256(message).digest(), 'big'); w = pow(s, -1, N)
    point = _add(_mul(z * w % N, G), _mul(r * w % N, (x, y)))
    return point is not None and point[0] % N == r

# ---- RS256: RSA PKCS#1 v1.5 with SHA-256 (Windows Hello often uses this) ----
SHA256_PREFIX = bytes.fromhex('3031300d060960864801650304020105000420')
def verify_rs256(n, e, message, sig):
    size = (n.bit_length() + 7) // 8
    if size < 256 or len(sig) != size or e < 3: return False
    opened = pow(int.from_bytes(sig, 'big'), e, n).to_bytes(size, 'big')
    wanted = b'\x00\x01' + b'\xff' * (size - 3 - len(SHA256_PREFIX) - 32) + b'\x00' + SHA256_PREFIX + hashlib.sha256(message).digest()
    return hmac.compare_digest(opened, wanted)

def public_key(cose):
    """The parts of a COSE public key we can check signatures with, as a JSON-safe dict."""
    if not isinstance(cose, dict): raise PasskeyError('That passkey could not be read.')
    if cose.get(1) == 2 and cose.get(3) == -7 and cose.get(-1) == 1 and isinstance(cose.get(-2), bytes) and isinstance(cose.get(-3), bytes):
        x, y = int.from_bytes(cose[-2], 'big'), int.from_bytes(cose[-3], 'big')
        if not on_curve(x, y): raise PasskeyError('That passkey could not be read.')
        return {'alg': 'ES256', 'x': hex(x), 'y': hex(y)}
    if cose.get(1) == 3 and cose.get(3) == -257 and isinstance(cose.get(-1), bytes) and isinstance(cose.get(-2), bytes):
        return {'alg': 'RS256', 'n': hex(int.from_bytes(cose[-1], 'big')), 'e': hex(int.from_bytes(cose[-2], 'big'))}
    raise PasskeyError('This device makes a kind of passkey Dejoiy Mail cannot check yet. Try another device.')

def signed_by(key, message, sig):
    if key.get('alg') == 'ES256': return verify_es256(int(key['x'], 16), int(key['y'], 16), message, sig)
    if key.get('alg') == 'RS256': return verify_rs256(int(key['n'], 16), int(key['e'], 16), message, sig)
    return False


# ---- the two WebAuthn checks ----
def client_data(raw, kind, challenge, origin):
    try: data = json.loads(raw)
    except ValueError: data = None
    if not isinstance(data, dict) or data.get('type') != kind: raise PasskeyError('That passkey answer is not valid.')
    if not hmac.compare_digest(str(data.get('challenge', '')), challenge): raise PasskeyError('That took too long. Start again.')
    if data.get('origin') != origin: raise PasskeyError('That passkey belongs to another site.')

def auth_data(raw, rp_id):
    """Checks the part the authenticator signs. Returns (sign count, rest after the fixed header, has-new-key flag)."""
    if len(raw) < 37 or not hmac.compare_digest(raw[:32], hashlib.sha256(rp_id.encode()).digest()): raise PasskeyError('That passkey belongs to another site.')
    flags = raw[32]
    if not flags & 1 or not flags & 4: raise PasskeyError('Unlock your device (fingerprint, face or PIN) to use the passkey.')
    return struct.unpack('>I', raw[33:37])[0], raw[37:], bool(flags & 64)

def hash_code(code): return hashlib.sha256(('dejoiy-passkey-code:' + ''.join(c for c in str(code).lower() if c.isalnum())).encode()).hexdigest()


class Passkeys:
    def __init__(self, store, now=time.time): self.store, self.now = store, now

    def data(self, email):
        saved = self.store.get(email.lower()); saved = saved if isinstance(saved, dict) else {}
        return {'keys': [k for k in saved.get('keys', []) if isinstance(k, dict)], 'codes': [c for c in saved.get('codes', []) if isinstance(c, str)]}
    def save(self, email, data): self.store.put(email.lower(), data)

    def view(self, email):
        """What the settings page shows: never the keys themselves."""
        d = self.data(email)
        return {'passkeys': [{'id': k['id'][:16], 'name': k['name'], 'created': k['created'], 'used': k.get('used'), 'site': k['rp']} for k in d['keys']], 'codesLeft': len(d['codes']), 'on': bool(d['keys'])}

    # -- adding one (the person is already signed in) --
    def register_options(self, email, name, rp_id, shown=''):
        """email: the key the passkeys are kept under (an account id is fine); shown: the address the device lists it as."""
        d = self.data(email)
        if len(d['keys']) >= MAX_KEYS: raise PasskeyError(f'You can keep {MAX_KEYS} passkeys. Remove one first.')
        challenge = b64(secrets.token_bytes(32))
        options = {'challenge': challenge, 'rp': {'id': rp_id, 'name': 'Dejoiy Mail'},
                   'user': {'id': b64(hashlib.sha256(email.lower().encode()).digest()), 'name': shown or email.lower(), 'displayName': name or shown or email},
                   'pubKeyCredParams': [{'type': 'public-key', 'alg': -7}, {'type': 'public-key', 'alg': -257}], 'timeout': 120000, 'attestation': 'none',
                   'authenticatorSelection': {'residentKey': 'preferred', 'userVerification': 'required'},
                   'excludeCredentials': [{'type': 'public-key', 'id': k['id']} for k in d['keys'] if k['rp'] == rp_id]}
        return options, {'challenge': challenge, 'rp': rp_id, 'until': self.now() + 300}

    def register(self, email, state, credential, origin, label=''):
        if not isinstance(state, dict) or state.get('until', 0) < self.now(): raise PasskeyError('That took too long. Start again.')
        response = credential.get('response') if isinstance(credential, dict) else None
        if not isinstance(response, dict): raise PasskeyError('That passkey answer could not be read. Try again.')
        client_data(unb64(response.get('clientDataJSON')), 'webauthn.create', state['challenge'], origin)
        attestation, _ = cbor(unb64(response.get('attestationObject')))
        raw = attestation.get('authData') if isinstance(attestation, dict) else None
        if not isinstance(raw, bytes): raise PasskeyError('That passkey could not be read.')
        count, rest, has_key = auth_data(raw, state['rp'])
        if not has_key or len(rest) < 18: raise PasskeyError('That passkey could not be read.')
        size = struct.unpack('>H', rest[16:18])[0]; cred_id = rest[18:18 + size]
        if not 16 <= size <= 1023 or len(cred_id) != size: raise PasskeyError('That passkey could not be read.')
        key = public_key(cbor(rest[18 + size:])[0])
        d = self.data(email); ident = b64(cred_id)
        if any(k['id'] == ident for k in d['keys']): raise PasskeyError('This passkey is already added.')
        if len(d['keys']) >= MAX_KEYS: raise PasskeyError(f'You can keep {MAX_KEYS} passkeys. Remove one first.')
        name = ''.join(c for c in str(label or '') if c.isprintable()).strip()[:40] or 'Passkey ' + str(len(d['keys']) + 1)
        d['keys'].append({'id': ident, 'key': key, 'count': count, 'name': name, 'created': int(self.now()), 'rp': state['rp']})
        codes = None
        if not d['codes']:   # the first passkey comes with the way back in
            codes = self.new_codes(); d['codes'] = [hash_code(c) for c in codes]
        self.save(email, d)
        return {**self.view(email), **({'codes': codes} if codes else {})}

    @staticmethod
    def new_codes(): return ['-'.join(secrets.token_hex(2) for _ in range(3)) for _ in range(CODES)]

    def fresh_codes(self, email):
        d = self.data(email)
        if not d['keys']: raise PasskeyError('Add a passkey first.')
        codes = self.new_codes(); d['codes'] = [hash_code(c) for c in codes]; self.save(email, d)
        return {**self.view(email), 'codes': codes}

    def remove(self, email, short_id):
        d = self.data(email); keep = [k for k in d['keys'] if k['id'][:16] != str(short_id)]
        if len(keep) == len(d['keys']): raise PasskeyError('That passkey is no longer there.')
        d['keys'] = keep
        if not keep: d['codes'] = []   # no passkey left: the second step is off, and old codes with it
        self.save(email, d); return self.view(email)

    def reset(self, email):
        """An admin's way to let someone back in: removes every passkey and code of that mailbox."""
        had = bool(self.data(email)['keys']); self.save(email, {'keys': [], 'codes': []}); return had

    # -- signing in --
    def needed(self, email): return bool(self.data(email)['keys'])

    def login_options(self, email, rp_id):
        """(options, state) for the second step, or (None, None) when this mailbox has no passkey.
        On a site where none of the person's passkeys was made, options carries no credentials: a recovery code is the way in."""
        d = self.data(email)
        if not d['keys']: return None, None
        challenge = b64(secrets.token_bytes(32)); here = [k for k in d['keys'] if k['rp'] == rp_id]
        options = {'challenge': challenge, 'rpId': rp_id, 'timeout': 120000, 'userVerification': 'required',
                   'allowCredentials': [{'type': 'public-key', 'id': k['id']} for k in here]}
        return options, {'challenge': challenge, 'rp': rp_id, 'until': self.now() + 300, 'tries': 0}

    def login(self, email, state, assertion, origin):
        if not isinstance(state, dict) or state.get('until', 0) < self.now(): raise PasskeyError('That took too long. Sign in again.')
        response = assertion.get('response') if isinstance(assertion, dict) else None
        if not isinstance(response, dict): raise PasskeyError('That passkey answer could not be read. Try again.')
        d = self.data(email); key = next((k for k in d['keys'] if k['id'] == assertion.get('id') and k['rp'] == state['rp']), None)
        if key is None: raise PasskeyError('That passkey is not one of yours for this mailbox.')
        client_raw = unb64(response.get('clientDataJSON')); auth_raw = unb64(response.get('authenticatorData'))
        client_data(client_raw, 'webauthn.get', state['challenge'], origin)
        count, _, _ = auth_data(auth_raw, state['rp'])
        if not signed_by(key['key'], auth_raw + hashlib.sha256(client_raw).digest(), unb64(response.get('signature'))): raise PasskeyError('That passkey did not match. Try again.')
        if (count or key['count']) and count <= key['count']: raise PasskeyError('This passkey looks copied, so it was refused. Use a recovery code and remove it.')
        key['count'] = count; key['used'] = int(self.now()); self.save(email, d)
        return True

    def use_code(self, email, code):
        """A one-time recovery code: works once, then it is gone."""
        d = self.data(email); wanted = hash_code(code)
        match = next((c for c in d['codes'] if hmac.compare_digest(c, wanted)), None)
        if match is None: raise PasskeyError('That recovery code is not right, or was already used.')
        d['codes'].remove(match); self.save(email, d)
        return len(d['codes'])
