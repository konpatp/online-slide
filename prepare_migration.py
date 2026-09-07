"""Prepare a separate revision-bound authoring generation; never overwrite live state.

Publication must recheck the returned baseline digest before switching the
service. The old release and state file remain the rollback generation.
"""
import argparse,copy,hashlib,json
from pathlib import Path
from urllib.request import urlopen
from slidekit import ContractError,load_catalog,validate_state_snapshot,catalog_revision
from server import atomic_write_json

FIELDS=('schema','revision','order','hidden','overlays','objects','tables')
def persistent(state):return {key:copy.deepcopy(state.get(key,{})) for key in FIELDS}
def digest(state):return hashlib.sha256(json.dumps(persistent(state),sort_keys=True,separators=(',',':')).encode()).hexdigest()

def prepare(baseline,current,candidate,catalog):
    if digest(baseline)!=digest(current):raise ContractError('live authoring changed since the migration baseline')
    if baseline.get('sourceRevision')!=current.get('sourceRevision'):raise ContractError('live source changed since the migration baseline')
    old=set(current['order'])
    if not old<=set(catalog):raise ContractError('migration removed an existing slide')
    if [sid for sid in candidate['order'] if sid in old]!=current['order']:raise ContractError('migration changed existing human order')
    if set(candidate['hidden'])&old!=set(current['hidden']):raise ContractError('migration changed existing human visibility')
    for field in ('overlays','objects','tables'):
        for key,value in current.get(field,{}).items():
            if candidate.get(field,{}).get(key)!=value:raise ContractError('migration changed retained human '+field+': '+key)
    proposed=validate_state_snapshot(persistent(candidate),persistent(current),catalog)
    return proposed,{'schema':'online-slide/state-generation@1','baselineDigest':digest(current),
        'baselineRevision':current['revision'],'preparedDigest':digest(proposed),
        'sourceRevision':catalog_revision(catalog),'retainedSlides':current['order'],
        'slides':len(catalog),'oldStateUntouched':True,'activationRequiresFreshBaseline':True}

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    for key in ('baseline','candidate','slides','output','receipt'):parser.add_argument('--'+key,type=Path,required=True)
    parser.add_argument('--live-url',required=True);args=parser.parse_args()
    with urlopen(args.live_url.rstrip('/')+'/api/deck-state',timeout=15) as response:current=json.load(response)
    proposed,receipt=prepare(json.loads(args.baseline.read_text()),current,json.loads(args.candidate.read_text()),load_catalog(args.slides))
    if args.output.exists():
        if digest(json.loads(args.output.read_text()))!=digest(proposed):raise ContractError('refusing to replace an existing authoring generation')
    else:atomic_write_json(args.output,proposed)
    atomic_write_json(args.receipt,receipt)
    print(json.dumps(receipt,indent=2))
if __name__=='__main__':main()
