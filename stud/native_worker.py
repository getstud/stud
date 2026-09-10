"""Fault-isolated operations on an existing native archive; never rerun source."""
import argparse
import math
import os
from pathlib import Path
import sys
import traceback

if __package__ in (None,''):sys.path.insert(0,str(Path(__file__).resolve().parents[1]))

from stud.contracts import StudError, read_json, write_json
from stud.units import requirement_units


def measurement(model,manifest,args):
    import cadquery as cq
    from OCP.BRepExtrema import BRepExtrema_DistShapeShape
    from stud.checks import measure_requirement, resolve_point
    tolerance=float(args['tolerance'])
    if not math.isfinite(tolerance) or tolerance<0:raise StudError('invalid_measurement','Measurement tolerance must be finite and nonnegative.')
    targets=[];picks=[]
    for target in args['targets']:
        if not isinstance(target,dict):targets.append(target);continue
        object_id=target.get('object_id');point=target.get('point')
        if object_id not in model.shapes:raise StudError('unresolved_reference','The picked part is missing.',references=[object_id])
        if not isinstance(point,list) or len(point)!=3 or not all(isinstance(n,(int,float)) and math.isfinite(n) for n in point):
            raise StudError('invalid_measurement','A picked point requires finite world coordinates in project units.')
        vertex=cq.Vertex.makeVertex(*point)
        query=BRepExtrema_DistShapeShape(vertex.wrapped,model.shapes[object_id]['world'].wrapped)
        query.Perform()
        if not query.IsDone() or query.NbSolution()<1:raise StudError('geometric_operation_failed','Native point projection failed.')
        maximum=float(target.get('max_snap',manifest['settings']['linear_tolerance']*2+tolerance))
        if not math.isfinite(maximum) or maximum<0:raise StudError('invalid_measurement','Pick tolerance must be finite and nonnegative.')
        if query.Value()>maximum:raise StudError('stale_target','The picked point is too far from this version of the native solid.',references=[object_id])
        native=query.PointOnShape2(1);resolved=[native.X(),native.Y(),native.Z()]
        targets.append(resolved);picks.append(dict(object_id=object_id,input_point=point,native_point=resolved,snap_distance=query.Value()))
    kind=args['kind']
    if kind in ('point_distance','length'):
        if len(targets)!=2:raise StudError('invalid_measurement','Point distance requires two references.')
        a,b=[resolve_point(model,target) for target in targets]
        value=math.dist(a,b);units=model.units;evidence=dict(start=a,end=b,operation='native reference distance')
    else:
        requirement=dict(kind=kind,targets=targets,threshold=0,tolerance=tolerance)
        value,_,evidence=measure_requirement(model,requirement);units=requirement_units(model.units,kind)
    return dict(project_id=manifest['project_id'],source_id=manifest['source_id'],build_id=manifest['build_id'],
        status='measured',kind=kind,value=value,units=units,tolerance=tolerance,evidence=evidence,picks=picks)


def run(request):
    try:
        from stud.evaluated import load_model
        build=request['build'];args=request['arguments']
        if request['kind']=='plans':
            from stud.plans import generate
            result=generate(build['artifact_path'],request['output'],checkpoint=args['checkpoint'],print_spec=args['print_spec'],
                views=args['views'],estimate=request['estimate'],diagnostic=args['diagnostic'],include_lists=args.get('include_lists',True),
                expected_build={**build,'export_checkpoint':args['checkpoint']},reproduced_from_build=request.get('reproduced_from_build'))
        else:
            model,manifest=load_model(build['artifact_path'],manifest_version=args.get('manifest_version'),expected=build)
            result=measurement(model,manifest,args)
        write_json(request['result_path'],result)
        return 0
    except Exception as error:
        traceback.print_exc()
        write_json(request['result_path'],dict(error=error.as_dict() if isinstance(error,StudError) else dict(category='native_operation_failed',message=str(error))))
        return 1


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--request',required=True,type=Path)
    status = run(read_json(parser.parse_args().request))
    if os.name == 'nt':
        # Results are durable before run returns. The pinned native stack crashes
        # during Windows interpreter teardown; preserve the actual worker status.
        sys.stdout.flush()
        sys.stderr.flush()
        os._exit(status)
    raise SystemExit(status)
