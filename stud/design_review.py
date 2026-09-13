"""Review recorded design intent separately from measured geometry."""


def design_review(manifest):
    findings=[]
    registries={name:{item['id'] for item in manifest.get(name,[])}
                for name in ('objects','requirements','connections')}
    for expectation in manifest.get('expectations',[]):
        for field,registry in [('parts','objects'),('requirements','requirements'),('connections','connections')]:
            for target in expectation[field]:
                if target not in registries[registry]:
                    findings.append(dict(category='missing_'+field, target=expectation['id'],
                        parts=expectation['parts'],message=f'Expected {field}: {target} is missing.'))
    for connection in manifest.get('connections',[]):
        for target in connection['parts']:
            if target not in registries['objects']:
                findings.append(dict(category='missing_connection_part',target=connection['id'],parts=[target],
                                     message=f'Connection references missing part {target}.'))
        for message in connection.get('unresolved',[]):
            findings.append(dict(category='geometry_detail' if connection.get('geometry_unresolved') else 'connection_detail',
                                 target=connection['id'],parts=connection['parts'],message=message))
    for demand in manifest.get('demands',[]):
        for message in demand.get('unresolved',[]):
            findings.append(dict(category='material_selection',target=demand['id'],parts=demand['object_ids'],message=message))
    for finding in manifest.get('fabrication_findings',[]):
        findings.append(dict(finding,parts=[finding['target']] if finding['target'] in registries['objects'] else []))
    missing_geometry=any(f['category'] in ('missing_parts','missing_requirements','missing_connection_part','geometry_detail') for f in findings)
    geometry='verified' if manifest.get('checks',{}).get('all_passed') and not missing_geometry else 'not_verified'
    return dict(geometry=geometry,details='unresolved' if findings else 'no_recorded_gaps',findings=findings,
                summary=('Geometry verified.' if geometry=='verified' else 'Geometry not fully verified.')+
                (' Design details remain unresolved.' if findings else ' No recorded design-detail gaps; structural approval is not established.'))
