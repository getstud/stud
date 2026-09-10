"""Benchmark-only equivalence with both original native archives available.

Production history and cache identity remain byte-exact. This comparison can
additionally prove that distinct OCCT serializations represent the same solid.
It never rounds a cache key, relaxes an authored dimension or accepts a changed
measured value. Only native bounding padding and contact-distance roundoff have
explicit numeric allowances.
"""
from copy import deepcopy
import io
import math
from pathlib import Path

import cadquery as cq
from OCP.BRepAlgoAPI import BRepAlgoAPI_Cut
from OCP.Precision import Precision
from OCP.TopAbs import TopAbs_COMPOUND
from OCP.TopTools import TopTools_ListOfShape
from OCP.TopoDS import TopoDS_Iterator

from stud.contracts import confined, digest, read_json
from stud.source import evaluated_identity


def require(condition,message):
    if not condition:raise AssertionError(message)


def _empty_difference(left,right):
    arguments=TopTools_ListOfShape();arguments.Append(left.wrapped)
    tools=TopTools_ListOfShape();tools.Append(right.wrapped)
    operation=BRepAlgoAPI_Cut()
    operation.SetArguments(arguments);operation.SetTools(tools)
    operation.SetNonDestructive(True);operation.SetRunParallel(False)
    # Deliberately retain native kernel precision; no added fuzzy tolerance.
    operation.Build()
    require(operation.IsDone(),'Native difference did not finish')
    result=operation.Shape()
    require(not result.IsNull(),'Native difference returned a null shape')
    return result.ShapeType()==TopAbs_COMPOUND and not TopoDS_Iterator(result).More()


def equivalent_solids(left,right):
    require(left.Solids() and right.Solids() and left.isValid() and right.isValid(),'Invalid native solid')
    for topology in ('Solids','Shells','Faces','Wires','Edges','Vertices'):
        if len(getattr(left,topology)())!=len(getattr(right,topology)()):return False
    return _empty_difference(left,right) and _empty_difference(right,left)


def compare_native_evidence(left_directory,right_directory):
    directories=[Path(left_directory),Path(right_directory)]
    manifests=[read_json(directory/'manifest.json') for directory in directories]
    left,right=manifests
    for key in ('source_id','runtime','settings'):
        a,b=deepcopy(left[key]),deepcopy(right[key])
        if key=='settings':a.pop('full_checks',None);b.pop('full_checks',None)
        require(a==b,f'Different {key}')
    for key in ('name','units','references','requirements','demands','dimensions','drawings','steps','connections','notes','fabrication_findings','completion'):
        require(left.get(key)==right.get(key),f'Different {key}')
    assemblies=lambda manifest:sorted(({k:v for k,v in assembly.items() if k!='provenance'} for assembly in manifest['assemblies']),key=lambda a:a['id'])
    require(assemblies(left)==assemblies(right),'Different assemblies')
    native=[]
    for directory,manifest in zip(directories,manifests):
        values={}
        for key,asset in manifest['assets'].items():
            body=confined(directory,asset['native']).read_bytes()
            require(digest(body)==asset['native_sha256'],'Corrupt native asset')
            require(asset['units']==manifest['units'],'Mixed native asset units')
            values[key]=(asset['native_sha256'],body)
        native.append(values)
    objects=[{obj['id']:obj for obj in manifest['objects']} for manifest in manifests]
    require(len(objects[0])==len(left['objects']) and len(objects[1])==len(right['objects']),'Duplicate object IDs')
    require(objects[0].keys()==objects[1].keys(),'Different object IDs')
    proven=set();bound_roundoff=0
    for object_id,a in objects[0].items():
        b=objects[1][object_id]
        authored=lambda obj:{k:v for k,v in obj.items() if k not in ('provenance','shape_key','shape_digest','bounds')}
        require(authored(a)==authored(b),f'Different object metadata: {object_id}')
        assets=[values[obj['shape_key']] for values,obj in zip(native,(a,b))]
        require(all(checksum==obj['shape_digest'] for (checksum,_),obj in zip(assets,(a,b))),'Object/native digest mismatch')
        pair=(assets[0][0],assets[1][0])
        if pair[0]!=pair[1] and pair not in proven:
            shapes=[cq.Shape.importBrep(io.BytesIO(body)) for _,body in assets]
            require(equivalent_solids(*shapes),f'Different native solid: {object_id}')
            proven.add(pair)
        coordinate_scale=max(1,*(abs(v) for obj in (a,b) for values in obj['bounds'].values() for v in values))
        for side in ('min','max'):
            require(len(a['bounds'][side])==len(b['bounds'][side])==3,'Invalid bounds')
            for x,y in zip(a['bounds'][side],b['bounds'][side]):
                # OCCT may add one native Confusion() of box padding depending
                # on its representation; allow only that plus arithmetic ULPs.
                allowance=Precision.Confusion_s()+8*math.ulp(coordinate_scale)
                require(math.isfinite(x) and math.isfinite(y) and abs(x-y)<=allowance,f'Different bounds: {object_id}')
                bound_roundoff+=x!=y
    a,b=deepcopy(left['checks']),deepcopy(right['checks'])
    metadata=lambda checks:{k:v for k,v in checks.items() if k not in ('findings','elapsed_seconds','timings')}
    require(metadata(a)==metadata(b),'Different check coverage or result')
    require(len(a['findings'])==len(b['findings']),'Different finding count')
    contact_roundoff=0
    for first,second in zip(a['findings'],b['findings']):
        # Measured areas, thresholds and statuses remain exact. This allowance
        # applies only to the supplementary native face-separation distance.
        if first.get('kind') in ('contact','support') and second.get('kind')==first.get('kind'):
            one,two=first.get('evidence') or {},second.get('evidence') or {}
            if 'distance' in one and 'distance' in two and one['distance']!=two['distance']:
                x,y=one['distance'],two['distance']
                require(math.isfinite(x) and math.isfinite(y) and abs(x-y)<=1e-12,'Different contact separation')
                one['distance']=two['distance'];contact_roundoff+=1
        require(first==second,f'Different finding: {first.get("requirement_id")}')
    return dict(equivalent=True,byte_identity_matches=evaluated_identity(left)==evaluated_identity(right),
                native_difference_pairs=len(proven),bound_roundoff_coordinates=bound_roundoff,
                contact_distance_roundoff=contact_roundoff)
