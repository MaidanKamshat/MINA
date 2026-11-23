"""MINA v2.15 local conversation archive and explicit-pinned memory.

Plain-text SQLite stored only on this machine, not encrypted. Never stores audio,
API keys, coordinates from traces, or raw map HTML; only text messages when
explicitly opted in. Retrieval is opt-in on user request; no hidden prompt injection.
"""
from __future__ import annotations
from datetime import datetime, timezone
from contextlib import contextmanager
from pathlib import Path
import json, os, re, sqlite3

BASE = Path.home() / '.mina'
DB = BASE / 'conversation_memory_v215.sqlite3'
SETTINGS = BASE / 'conversation_memory_consent_v215.json'
VERSION = '2.15.0'

class MemoryErrorLocal(ValueError):
    pass

def _secure_dir(path: Path):
    path.mkdir(parents=True, exist_ok=True, mode=0o700)
    if os.name == 'posix':
        try: path.chmod(0o700)
        except OSError: pass

def _connect(path: Path = DB):
    _secure_dir(path.parent)
    conn = sqlite3.connect(path, timeout=5)
    try:
        if os.name == 'posix': path.chmod(0o600)
        conn.execute('PRAGMA busy_timeout=3000')
        conn.execute('''CREATE TABLE IF NOT EXISTS turns (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id TEXT NOT NULL,
            created_utc TEXT NOT NULL,
            role TEXT NOT NULL CHECK (role IN ('user','assistant')),
            content TEXT NOT NULL)''')
        conn.execute('''CREATE TABLE IF NOT EXISTS pinned_facts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            created_utc TEXT NOT NULL,
            content TEXT NOT NULL)''')
        conn.commit()
    except Exception:
        conn.close()
        raise
    return conn

@contextmanager
def _using(path: Path = DB):
    connection=_connect(path)
    try:
        with connection:
            yield connection
    finally:
        connection.close()


def load_opt_in(path: Path = SETTINGS):
    if not path.exists(): return False
    try:
        d = json.loads(path.read_text(encoding='utf-8'))
        if d.get('version') != 1 or type(d.get('enabled')) is not bool: raise ValueError()
        return d['enabled']
    except (OSError, ValueError, TypeError) as exc:
        raise MemoryErrorLocal('Invalid local memory preference file.') from exc

def set_opt_in(enabled: bool, path: Path = SETTINGS):
    if type(enabled) is not bool: raise MemoryErrorLocal('Expected true or false.')
    _secure_dir(path.parent)
    from tempfile import NamedTemporaryFile
    with NamedTemporaryFile('w', encoding='utf-8', dir=path.parent, prefix='.memory-', delete=False) as f:
        tmp = Path(f.name)
        try:
            os.chmod(tmp, 0o600)
            json.dump({'version':1,'enabled':enabled}, f)
            f.flush(); os.fsync(f.fileno())
        except BaseException:
            tmp.unlink(missing_ok=True)
            raise
    os.replace(tmp, path)

def append_exchange(session_id: str, user: str, assistant: str, *, path: Path = DB):
    if not session_id or not user.strip() or not assistant.strip():
        raise MemoryErrorLocal('Invalid conversation turn.')
    if max(len(user),len(assistant)) > 30000:
        raise MemoryErrorLocal('Message too large for local archive.')
    with _using(path) as c:
        now = datetime.now(timezone.utc).isoformat()
        c.executemany('INSERT INTO turns (session_id,created_utc,role,content) VALUES (?,?,?,?)',
            [(session_id,now,'user',user.strip()),(session_id,now,'assistant',assistant.strip())])

def recent_turns(*, limit=50, path: Path = DB):
    if not path.exists(): return []
    with _using(path) as c:
        rows=c.execute('SELECT session_id,created_utc,role,content FROM turns ORDER BY id DESC LIMIT ?',
                       (min(max(int(limit),1),200),)).fetchall()
    return list(reversed([{'session':r[0],'time':r[1],'role':r[2],'text':r[3]} for r in rows]))

def search_turns(query: str, *, limit=6, path: Path = DB):
    """Literal case-insensitive substring lookup; not semantic similarity."""
    q=query.strip()
    if not q or len(q)>200: return []
    if not path.exists(): return []
    with _using(path) as c:
        rows=c.execute('SELECT created_utc,role,content FROM turns WHERE instr(lower(content),lower(?)) > 0 ORDER BY id DESC LIMIT ?',
                     (q,min(max(int(limit),1),20))).fetchall()
    return [{'time':t,'role':r,'text':txt[:500]} for t,r,txt in rows]

def pin_fact(fact: str, *, path: Path = DB):
    fact = fact.strip()
    if len(fact)<3 or len(fact)>500: raise MemoryErrorLocal('Memory fact must contain 3–500 characters.')
    with _using(path) as c:
        c.execute('INSERT INTO pinned_facts (created_utc,content) VALUES (?,?)',
                  (datetime.now(timezone.utc).isoformat(),fact))

def facts(*, path: Path = DB):
    if not path.exists(): return []
    with _using(path) as c:
        rows=c.execute('SELECT id,content FROM pinned_facts ORDER BY id DESC LIMIT 100').fetchall()
    return [{'id':r[0],'text':r[1]} for r in rows]

def remove_fact(id: int, *, path: Path = DB):
    if not path.exists(): return False
    with _using(path) as c:
        r=c.execute('DELETE FROM pinned_facts WHERE id=?',(int(id),))
    return r.rowcount>0

def erase_history(*, path: Path = DB):
    if not path.exists(): return
    with _using(path) as c: c.execute('DELETE FROM turns')
    # SQLite may keep freed pages: VACUUM to reduce recoverable old content.
    with _using(path) as c: c.execute('VACUUM')

def erase_all(*, path: Path = DB):
    if not path.exists(): return
    with _using(path) as c:
        c.execute('DELETE FROM turns'); c.execute('DELETE FROM pinned_facts')
    with _using(path) as c: c.execute('VACUUM')

def memory_request(text: str):
    """Only explicit recall or pin commands, not every possible question."""
    s=text.strip()
    m=re.match(r'^(?:mina[,.! ]+)?remember that (.{3,500})[.!]?$',s,re.I)
    if m: return ('pin',m.group(1).strip().rstrip('.'))
    m=re.match(r'^(?:mina[,.! ]+)?(?:what (?:did (?:i|we) (?:say|tell you) about|do you remember about)|search (?:my |our )?(?:conversation|chat) (?:for|about))\s+(.+?)[?!.]?$',s,re.I)
    if m: return ('search',m.group(1).strip())
    return None
