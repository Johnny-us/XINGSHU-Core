"""从已接受实现复用机械快照，不调用 StatefulRelay 的业务状态机。"""
import copy,hashlib,json,os,re,stat
from pathlib import Path
MAX_BYTES=65536
class Rejected(Exception):pass
def strict_json(raw):
    def pairs(items):
        out = {}
        for key, value in items:
            if key in out:
                raise Rejected('DUPLICATE_JSON_KEY')
            out[key] = value
        return out
    try:
        return json.loads(raw, object_pairs_hook=pairs,
                          parse_constant=lambda _: (_ for _ in ()).throw(Rejected('NONFINITE_JSON')))
    except Rejected:
        raise
    except (ValueError, UnicodeError, RecursionError):
        raise Rejected('INVALID_JSON')


def encode(value):
    return json.dumps(value,sort_keys=True,separators=(',',':'),ensure_ascii=False,allow_nan=False).encode()
def digest(value):return hashlib.sha256(encode(value)).hexdigest()
from xingshu_collaboration.binding import CandidateError
def identity(value):
    return type(value) is str and re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_-]{0,79}',value) is not None

class SnapshotStore:
    """仅候选路径、追加封印快照；partial/tamper 不自动修复或重试。"""
    def __init__(self,root,allowed_candidate_root,*,protected_roots=()):
        self.root=Path(root);self.allowed=Path(allowed_candidate_root)
        if (not self.root.is_absolute() or '..' in self.root.parts or not self.allowed.is_absolute()
            or '..' in self.allowed.parts or self.root==self.allowed
            or not self.root.is_relative_to(self.allowed)):
            raise CandidateError('CANDIDATE_STORE_PATH_REJECTED')
        for protected in protected_roots:
            protected=Path(protected)
            if not protected.is_absolute() or '..' in protected.parts:
                raise CandidateError('PROTECTED_ROOT_INVALID')
            if (self.root==protected or self.root.is_relative_to(protected)
                    or protected.is_relative_to(self.root)):
                raise CandidateError('CANDIDATE_STORE_PATH_REJECTED')
        for p in [self.root]+list(self.root.parents):
            if p.is_symlink():raise CandidateError('CANDIDATE_STORE_SYMLINK_REJECTED')
        self.root.mkdir(mode=0o700,parents=True,exist_ok=True)
    def records(self):
        if list(self.root.glob('*.pending')):raise CandidateError('PARTIAL_CHECKPOINT_OWNER_REQUIRED')
        if any(not p.name.startswith('snapshot-') or p.suffix!='.json' for p in self.root.iterdir()):
            raise CandidateError('CHECKPOINT_UNKNOWN_OBJECT')
        records=sorted(self.root.glob('snapshot-*.json'));previous='0'*64;last=None
        for i,p in enumerate(records,1):
            st=p.lstat()
            if p.name!='snapshot-'+str(i).zfill(6)+'.json' or not stat.S_ISREG(st.st_mode) or st.st_nlink!=1 or st.st_size>MAX_BYTES:
                raise CandidateError('CHECKPOINT_IDENTITY_INVALID')
            try:row=strict_json(p.read_bytes())
            except Rejected:raise CandidateError('CHECKPOINT_JSON_INVALID')
            if type(row) is not dict or set(row)!={'schema_version','index','previous','state','digest'}:raise CandidateError('CHECKPOINT_SCHEMA_INVALID')
            unsigned={k:v for k,v in row.items() if k!='digest'}
            if row['schema_version']!='stateful-checkpoint-candidate-0.1' or row['index']!=i or row['previous']!=previous or row['digest']!=digest(unsigned):raise CandidateError('CHECKPOINT_CHAIN_INVALID')
            previous=row['digest'];last=row
        return records,last
    def load(self):
        _,last=self.records();return copy.deepcopy(last['state']) if last else None
    def save(self,doc):
        records,last=self.records()
        if last and last['state']==doc:return records[-1]
        row={'schema_version':'stateful-checkpoint-candidate-0.1','index':len(records)+1,'previous':last['digest'] if last else '0'*64,'state':copy.deepcopy(doc)}
        row['digest']=digest(row);b=encode(row)
        if len(b)>MAX_BYTES:raise CandidateError('CHECKPOINT_SIZE_BOUND')
        p=self.root/('snapshot-'+str(len(records)+1).zfill(6)+'.pending');final=p.with_suffix('.json')
        fd=os.open(p,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600)
        with os.fdopen(fd,'wb') as f:f.write(b);f.flush();os.fsync(f.fileno())
        if final.exists():raise CandidateError('CHECKPOINT_RACE_OWNER_REQUIRED')
        os.rename(p,final)
        return final
