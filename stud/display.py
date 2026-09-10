"""Presentation adapters for the established viewer, without a second model engine.

CAD coordinates remain in the declared project units. The established viewer
uses inches for camera and GPU coordinates; labels use the project units.
"""
import csv
import io
import json
import math
from pathlib import Path
from urllib.parse import quote

from .contracts import StudError, digest, identifier, read_json
from .estimate import calculate, purchase_lines
from .units import convert


def displayed_manifest(session):
    with session.mutex:
        latest=session.job(session.state['latest_build']) if session.state['latest_build'] else None
        displayed=session.state['displayed_build']
        if session.state.get('view_mode')=='history' and displayed:
            job=session.job(displayed);path=Path(job['artifact_path'])
            manifest=read_json(path/'manifest.json') or read_json(path/'geometry.json') or read_json(path/'partial.json')
            if manifest:return manifest,job
        if latest and latest.get('artifact_path'):
            path=Path(latest['artifact_path'])
            current=read_json(path/'manifest.json') or read_json(path/'geometry.json') or read_json(path/'partial.json')
            if current and (current['objects'] or current['completion']['geometry']=='complete'):
                return current,latest
        if displayed:
            job=session.job(displayed);manifest=read_json(Path(job['artifact_path'])/'manifest.json')
            if manifest:return manifest,job
        raise StudError('build_pending','A model is being prepared; no current geometry is available yet.',retryable=True)


def inputs_for_model(session,manifest,job=None):
    """Use this model's design assumptions, even when a newer draft is running."""
    job=job or session.job(manifest['build_id'])
    active=session._request(session.state['active_request']) if session.state['active_request'] else None
    if session.state.get('view_mode')=='history' and session.state.get('view_checkpoint'):
        report=session.history.checkpoint_report(session.state['view_checkpoint'])
        if report and report['source_id']==manifest['source_id']:
            return session.records.inputs(session.state['view_checkpoint'],include_pending=False)
    if active and (job.get('request_id')==active['id'] or (active.get('change_kind')=='records' and active.get('latest_build')==job['id'])):
        return session.records.inputs(request=active)
    head=session.history.option(session.state['active_option'])['head']
    report=session.history.checkpoint_report(head)
    if not active and report and report['source_id']==manifest['source_id'] and (not job.get('checkpoint') or job['checkpoint']==head):
        return session.records.inputs(head,include_pending=True)
    checkpoint=job.get('checkpoint')
    if not checkpoint and job.get('request_id'):
        request=session._request(job['request_id']);checkpoint=request.get('checkpoint') or request['expected_head']
    return session.records.inputs(checkpoint or head,include_pending=False)


def _point(manifest, reference):
    if isinstance(reference,list):return reference
    named=manifest['references'].get(reference)
    if not named or named['kind']!='point':return None
    obj=next((p for p in manifest['objects'] if p['id']==named['object_id']),None)
    if not obj:return None
    point=named['value'];matrix=obj['placement']
    return [sum(matrix[row][i]*point[i] for i in range(3))+matrix[row][3] for row in range(3)]


def _rotation(matrix):
    # Same XYZ convention used by Three.Euler; only for the inspector labels.
    y=math.asin(max(-1,min(1,matrix[0][2])))
    if abs(matrix[0][2])<.9999999:x,z=math.atan2(-matrix[1][2],matrix[2][2]),math.atan2(-matrix[0][1],matrix[0][0])
    else:x,z=math.atan2(matrix[2][1],matrix[1][1]),0
    return [math.degrees(value) for value in (x,y,z)]


def model_for_viewer(session):
    manifest,job=displayed_manifest(session)
    return model_from_manifest(session,manifest,job)


def model_from_manifest(session,manifest,job,*,inputs=None,presentation=None,checkpoint=None):
    factor=convert(1,manifest['units'],'in')
    assemblies={a['id']:a['label'] for a in manifest['assemblies']}
    demands={d['product_id']:d for d in manifest['demands']}
    stocks={}
    for obj in manifest['objects']:
        material=obj.get('material') or 'unspecified'
        demand=demands.get(material,{})
        spec=demand.get('specification',{})
        stocks[material]=dict(name=material.replace('.',' ').title(),color=obj.get('color','#d8b982'),url='',
            section=[v*factor for v in spec['section']] if spec.get('section') else None,
            sheet=[v*factor for v in spec['sheet']] if spec.get('sheet') else None,
            sheet_thickness=spec.get('thickness',0)*factor if spec.get('thickness') else None)
    parts=[]
    for obj in manifest['objects']:
        asset=manifest['assets'][obj['shape_key']];bounds=asset['bounds']
        size=[(b-a)*factor for a,b in zip(bounds['min'],bounds['max'])]
        origin=[obj['placement'][i][3]*factor for i in range(3)]
        blank=obj.get('blank') or {}
        part=dict(id=obj['id'],name=obj['label'],mark=obj['mark'],assembly=assemblies.get(obj['parent'],obj['parent'] or 'Parts'),
            assembly_id=obj['parent'],stock=obj.get('material') or 'unspecified',size=size,origin=origin,
            rotation=_rotation(obj['placement']),status='modeled',note='',color=obj.get('color'),
            blank_size=[v*factor for v in blank['size']] if blank.get('size') else None,
            cut_length=blank.get('cut_length',0)*factor or None,
            cad=dict(build_id=manifest['build_id'],source_id=manifest['source_id'],shape_key=obj['shape_key'],
                     mesh_url=f'/api/v1/builds/{manifest["build_id"]}/{asset["mesh"]}',mesh_sha256=asset['mesh_sha256'],units=asset['units'],
                     placement=obj['placement'],local_bounds=bounds,operations=blank.get('operations',[]),provenance=obj.get('provenance')))
        parts.append(part)
    dimensions=[]
    for dimension in manifest['dimensions']:
        a,b=_point(manifest,dimension['start']),_point(manifest,dimension['end'])
        if a is not None and b is not None:
            dimensions.append(dict(id=dimension['id'],label=dimension['label'],start=[v*factor for v in a],end=[v*factor for v in b],inches=math.dist(a,b)*factor))
    inputs=inputs if inputs is not None else inputs_for_model(session,manifest,job)
    materials=[]
    try:purchases=purchase_lines(manifest['demands'],inputs)
    except StudError as error:purchases=[dict(product_id='unavailable',object_ids=[],quantity=None,purchase_unit='',basis=str(error),missing=[str(error)])]
    for purchase in purchases:
        label=purchase['product_id'].replace('.',' ').title()
        if purchase.get('specification',{}).get('stock_length'):label+=' / '+str(float(purchase['specification']['stock_length']))+' '+manifest['units']+' stock'
        materials.append(dict(stock=purchase['product_id'],name=label,parts=len(set(purchase['object_ids'])),
            purchase=f'{purchase["quantity"] if purchase["quantity"] is not None else "Unknown"} {purchase["purchase_unit"]}',basis=purchase['basis'],
            status='Incomplete' if purchase['missing'] else 'Specified purchases',url=''))
    version='geometry' if manifest.get('artifact_stage')=='geometry' else manifest.get('publication_sequence')
    revision=f'{manifest["build_id"]}:{version if version is not None else "final"}'
    checks=manifest.get('checks',{})
    findings=[]
    for finding in checks.get('findings',[]):
        status={'passed':'PASS','failed':'FAIL','unresolved':'UNVERIFIED','unsupported':'UNVERIFIED','execution_failed':'FAIL'}[finding['status']]
        targets=[manifest['references'].get(t,{}).get('object_id',t) for t in finding['targets']]
        message=finding.get('explanation') or finding['kind'].replace('_',' ').capitalize()
        if finding.get('measured') is not None:message+=f': measured {finding["measured"]:g} {finding["units"]}; expected {finding["expected"]:g}.'
        if finding.get('error'):message+=' '+finding['error']['message']
        findings.append(dict(status=status,rule=finding['requirement_id'],parts=targets,message=message,evidence=finding.get('evidence')))
    if not checks.get('coverage',{}).get('complete'):
        findings.append(dict(status='UNVERIFIED',rule='Coverage',parts=checks.get('coverage',{}).get('uncovered_objects',[]),message='Some geometric requirements have not been verified.'))
    latest=session.job(session.state['latest_build']) if session.state['latest_build'] and presentation is None else job
    return dict(schema_version=1,engine='cadquery',units='in',display_units=manifest['units'],name=manifest['name'],revision=revision,parts=parts,stocks=stocks,
        dimensions=dimensions,materials=materials,environment=[],
        validation_results=dict(findings=findings,coverage=checks.get('coverage',{})),
        cad=dict(project_id=manifest['project_id'],build_id=manifest['build_id'],source_id=manifest['source_id'],
                 checkpoint=checkpoint or (session.state.get('view_checkpoint') if session.state.get('view_mode')=='history' else job.get('checkpoint')),manifest_version=version,completion=manifest['completion'],
                 latest_build_id=latest['id'],latest_status=latest['status'],diagnostics=latest.get('diagnostics'),
                 reproduction=job.get('reproduction'),
                 presentation=presentation or ('history' if session.state.get('view_mode')=='history' else 'live')))


def current_estimate(session,manifest=None):
    manifest,job=displayed_manifest(session) if manifest is None else (manifest,None)
    if manifest['completion']['geometry']!='complete':
        raise StudError('incomplete_geometry','Partial geometry is not a complete material estimate.')
    inputs=inputs_for_model(session,manifest,job)
    return calculate(manifest['demands'],inputs,session.records.values('quotes'),project_id=manifest['project_id'],
                     demand_findings=manifest.get('fabrication_findings'),
                     source_id=manifest['source_id'],build_id=manifest['build_id'])


def prices_for_viewer(session):
    manifest,job=displayed_manifest(session)
    historical=session.state.get('view_mode')=='history'
    if historical:
        report=session.history.checkpoint_report(session.state['view_checkpoint']) or {}
        estimate=report.get('original_estimate') or {}
        if 'id' not in estimate:
            return dict(currency='USD',revision=manifest['build_id'],rows=[],subtotal=None,total=None,complete=False,
                priced_lines=0,unpriced_lines=0,categories={},price_kinds={},editable=False,
                context='No original estimate was saved for this checkpoint.')
    else:estimate=current_estimate(session,manifest)
    rows=[]
    for line in estimate['rows']:
        quote_record=line['quote'];quote_kind={'manual':'manual','sourced':'source','estimated':'estimate'}.get((quote_record or {}).get('kind'))
        q=dict(unit_price=quote_record['price'],source=quote_record['supplier'],observed_on=quote_record['quote_date'],
               url=quote_record.get('source',''),note=quote_record.get('note',''),quantity=line.get('quantity_override')) if quote_record else None
        rows.append(dict(key=line['line_id'],product_id=line['product_id'],specification=line['specification'],pack_size=line['pack_size'],
            purchase_unit=line['purchase_unit'],name=line['product_id'].replace('.',' ').title(),unit=line['purchase_unit'],
            model_quantity=line['quantity'],quantity=line['quantity'],total=line['line_total'],basis=line['basis'],
            quote=q,quote_kind=quote_kind,has_manual=quote_kind=='manual',sourced_quote=None,category='Materials'))
    return dict(currency=estimate['currency'],revision=f'{manifest["build_id"]}:final',estimate_id=estimate['id'],
        editable=not historical,context=f'Original saved estimate for checkpoint {session.state["view_checkpoint"][:12]}.' if historical else 'Current design and project quotes.',
        price_basis_id=estimate['price_basis_id'],build_id=manifest['build_id'],rows=rows,subtotal=estimate['known_subtotal'],
        total=estimate['total'],complete=estimate['status']=='complete',tax=estimate['tax'],contingency=estimate['contingency'],
        priced_lines=sum(row['total'] is not None for row in rows),unpriced_lines=sum(row['total'] is None for row in rows),
        categories={},price_kinds={kind:dict(lines=sum(row['quote_kind']==kind for row in rows)) for kind in ('manual','source','estimate')})


def save_viewer_prices(session,payload):
    estimate=prices_for_viewer(session)
    if payload.get('expected_estimate') and payload['expected_estimate']!=estimate['estimate_id']:
        raise StudError('stale_revision','The estimate changed before this price was saved.',expected=payload['expected_estimate'],current=estimate['estimate_id'])
    row=next((row for row in estimate['rows'] if row['key']==payload.get('key')),None)
    if not row:raise StudError('unresolved_reference','The priced material no longer exists.')
    quote_record=dict(product_id=row['product_id'],specification=row['specification'],purchase_unit=row['purchase_unit'],pack_size=row['pack_size'])
    if payload.get('action')=='clear_manual':quote_record['action']='clear_manual'
    else:
        quote_record.update(price=payload['unit_price'],currency=estimate['currency'],supplier=payload['source'],
                            source=payload.get('url',''),quote_date=payload['observed_on'],kind={'source':'sourced','estimate':'estimated'}.get(payload.get('kind'),'manual'),
                            note=payload.get('note',''))
    overrides={row['key']:payload['quantity']} if payload.get('quantity') is not None else None
    session.save_prices(key=payload.get('client_key') or identifier('price'),quotes=[quote_record],overrides=overrides,expected_build=estimate['build_id'])
    return prices_for_viewer(session)


def displayed_prompts(session):
    with session.mutex:
        try:manifest,job=displayed_manifest(session)
        except StudError:manifest=None
        checkpoint=session.state.get('view_checkpoint') if session.state.get('view_mode')=='history' else None
        return session.records.prompts(manifest=manifest,checkpoint=checkpoint)


def prompts_for_viewer(session):
    return [{**prompt,'kind':'part' if prompt.get('object_id') else 'area','part_id':prompt.get('object_id'),
             'prompt_revision':prompt['revision'],
             'revision':f'{prompt["build_id"]}:{prompt["manifest_version"] if prompt.get("manifest_version") is not None else "final"}',
             'anchor':prompt.get('region'),'part_snapshot':prompt.get('original_target')}
            for prompt in displayed_prompts(session)]


def save_viewer_prompt(session,payload):
    action=payload.get('action','add');key=payload.get('client_key') or payload.get('id')
    if action=='add':
        if not payload.get('build_id') or not payload.get('source_id'):
            raise StudError('stale_target','Capture the displayed source and build before saving a prompt.')
        session.save_prompt(key=key,prompt_id=payload['id'],text=payload['text'],build_id=payload['build_id'],source_id=payload['source_id'],
            object_id=payload.get('part_id'),region=payload.get('anchor'),camera=payload.get('camera'),screenshot=payload.get('image'),
            manifest_version=payload.get('manifest_version'))
    else:
        if action=='resolve':action='resolve' if payload.get('resolved') else 'reopen'
        session.update_prompt(key=key,prompt_id=payload['id'],expected_revision=payload['expected_revision'],action=action,text=payload.get('text'))
    return dict(comments=prompts_for_viewer(session))


def csv_for_viewer(session,path):
    manifest,job=displayed_manifest(session)
    if manifest['completion']['geometry']!='complete':raise StudError('incomplete_geometry','Complete exports require complete geometry.')
    stream=io.StringIO();writer=csv.writer(stream)
    checkpoint=job.get('checkpoint') or ''
    if path=='/api/parts.csv':
        writer.writerow(['project_id','source_id','build_id','checkpoint','part_id','mark','label','units','blank'])
        for obj in manifest['objects']:writer.writerow([manifest['project_id'],manifest['source_id'],manifest['build_id'],checkpoint,obj['id'],obj['mark'],obj['label'],manifest['units'],(obj.get('blank') or {}).get('size')])
    else:
        estimate=current_estimate(session,manifest)
        writer.writerow(['source_id','build_id','checkpoint','estimate_id','price_basis_id','product','quantity','unit','unit_price','amount','currency'])
        for row in estimate['rows']:writer.writerow([manifest['source_id'],manifest['build_id'],checkpoint,estimate['id'],estimate['price_basis_id'],row['product_id'],row['quantity'],row['purchase_unit'],row['unit_price'],row['line_total'],estimate['currency']])
    return stream.getvalue()
