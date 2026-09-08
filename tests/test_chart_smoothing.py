"""The display transform preserves source arrays and uses x-distance windows."""
# test-tier: every-time
import json
from pathlib import Path
import subprocess


def test_runtime_ids_are_injective_css_safe_and_repeatable():
    source=Path(__file__).resolve().parents[1]/'public/chart-panels.js'
    values=['Control · before/after [α]', 'a b', 'a/b', 'a_b', '', '💡', '\\', '"', 'a:b']
    script="""
const fs=require('fs'),vm=require('vm');const sandbox={window:{}};
vm.runInNewContext(fs.readFileSync(process.argv[1],'utf8'),sandbox);
const values=JSON.parse(fs.readFileSync(0,'utf8'));
process.stdout.write(JSON.stringify(values.map(sandbox.window.scientificRuntimeTraceId)));
"""
    def encode():
        return json.loads(subprocess.run(['node','-e',script,str(source)],input=json.dumps(values),text=True,capture_output=True,check=True).stdout)
    ids=encode()
    import re
    assert ids==encode() and len(set(ids))==len(values)
    assert all(re.fullmatch(r'trace(?:_[0-9a-f]{4})*',key) for key in ids)


def test_centered_windows_match_brute_force_and_raw_keeps_order():
    source=Path(__file__).resolve().parents[1]/'public/chart-panels.js'
    cases=[{'x':[3,0,1,1],'y':[9,0,3,6],'radius':r} for r in (0,0.5,1,4)]
    script="""
const fs=require('fs'),vm=require('vm');const sandbox={window:{}};
vm.runInNewContext(fs.readFileSync(process.argv[1],'utf8'),sandbox);
const cases=JSON.parse(fs.readFileSync(0,'utf8'));
process.stdout.write(JSON.stringify(cases.map(c=>sandbox.window.scientificCenteredMeanByX(c.x,c.y,c.radius))));
"""
    result=subprocess.run(['node','-e',script,str(source)],input=json.dumps(cases),text=True,capture_output=True,check=True)
    for case,actual in zip(cases,json.loads(result.stdout)):
        if not case['radius']:
            assert actual=={'x':case['x'],'y':case['y']}
            continue
        ordered=sorted(zip(case['x'],case['y']),key=lambda p:p[0])
        expected=[]
        for x,_ in ordered:
            neighbors=[y for px,y in ordered if abs(px-x)<=case['radius']]
            expected.append(sum(neighbors)/len(neighbors))
        assert actual=={'x':[x for x,_ in ordered],'y':expected}
