"""Reconcile authored fabrication and purchase records without loading CAD."""
from decimal import Decimal, InvalidOperation


def audit_fabrication(manifest):
    findings=[]
    def issue(category,target,message):findings.append(dict(category=category,target=target,message=message))
    objects={obj['id']:obj for obj in manifest['objects']}
    covered=set();cut_parts=set();sheet_parts=set();quantities={}
    for demand in manifest['demands']:
        key=demand['id'];ids=set(demand['object_ids']);quantity=None
        for pid in ids-set(objects):issue('unresolved_material',key,f'Material demand references missing part {pid}.')
        if demand.get('quantity') is not None:
            try:
                value=Decimal(str(demand['quantity']))
                if not value.is_finite() or value<0:raise InvalidOperation
                quantity=value
                quantities[demand['product_id']]=quantities.get(demand['product_id'],Decimal(0))+value
            except (InvalidOperation,ValueError):issue('invalid_material_quantity',key,'Material quantity must be finite and nonnegative.')
        represented=set()
        for cut in demand.get('cuts_mm') or []:
            pid=cut.get('object_id');obj=objects.get(pid)
            if not obj or pid not in ids:
                issue('unresolved_cut',key,'Every cut must reference an included physical part.');continue
            if pid in cut_parts:issue('duplicate_cut',pid,'The same physical member appears in more than one purchase cut.')
            cut_parts.add(pid);represented.add(pid)
            expected=(obj.get('blank') or {}).get('cut_length_mm')
            try:matches=expected is not None and abs(float(expected)-float(cut['length_mm']))<=.01
            except (ValueError,TypeError,KeyError):matches=False
            if not matches:issue('stale_cut_length',pid,'The purchase cut length differs from the physical part blank, or its blank cut length is missing.')
            blank=(obj.get('blank') or {}).get('size_mm',[])
            section=demand.get('specification',{}).get('section_mm',[])
            compatible=False
            if len(blank)==3 and len(section)==2 and expected is not None:
                for axis in range(3):
                    transverse=sorted(value for i,value in enumerate(blank) if i!=axis)
                    if abs(blank[axis]-expected)<=.01 and all(abs(a-b)<=.01 for a,b in zip(transverse,sorted(section))):compatible=True
            if not compatible:issue('incompatible_stock_section',pid,'The purchased stock section does not match the part blank in its longitudinal stock frame.')
        for sheet in demand.get('sheets') or []:
            for panel in sheet.get('panels',[]):
                pid=panel.get('object_id')
                if pid not in ids or pid not in objects:issue('unresolved_sheet_cut',key,'Every sheet cut must reference an included physical panel.')
                if pid in sheet_parts:issue('duplicate_sheet_cut',pid,'The physical panel is assigned to more than one sheet cut.')
                sheet_parts.add(pid);represented.add(pid)
                obj=objects.get(pid);spec=demand.get('specification',{})
                if obj:
                    blank=obj.get('blank') or {};axes=blank.get('panel_axes',[0,1]);sizes=blank.get('size_mm',[])
                    normal=next((axis for axis in (0,1,2) if axis not in axes),None)
                    if len(sizes)!=3 or normal is None or abs(sizes[normal]-spec.get('thickness_mm',-1))>.01:
                        issue('incompatible_sheet_thickness',pid,'The purchased sheet thickness differs from the physical panel blank.')
                stock=spec.get('sheet_mm',[])
                if len(stock)!=2 or len(sheet.get('size_mm',[]))!=2 or any(abs(a-b)>.01 for a,b in zip(sorted(stock),sorted(sheet['size_mm']))):
                    issue('incompatible_sheet_stock',sheet['id'],'The cutting layout uses a different sheet size from the purchased material.')
        if demand.get('cuts_mm') is not None or demand.get('sheets') is not None:
            for pid in ids-represented:issue('missing_purchase_cut',pid,'The demand includes this part but has no matching board or sheet cut.')
        elif demand.get('quantity') is not None:
            represented=ids
            physical=[pid for pid in ids & set(objects) if objects[pid].get('material')==demand['product_id']]
            if physical and demand.get('unit','each')=='each' and quantity is not None and quantity<len(physical):
                issue('missing_part_quantity',key,f'{len(physical)} physical items require at least that many units of this material.')
        for pid in represented & set(objects):
            if objects[pid].get('material')==demand['product_id']:covered.add(pid)
    for pid in set(objects)-covered:
        issue('missing_part_material',pid,'No matching material demand purchases this physical part.')
    hardware={}
    for connection in manifest['connections']:
        item=connection.get('hardware')
        if not item:continue
        try:
            value=Decimal(str(item['count']))
            if not value.is_finite() or value<0:raise InvalidOperation
            hardware[item['product_id']]=hardware.get(item['product_id'],Decimal(0))+value
        except (InvalidOperation,KeyError,ValueError):issue('invalid_hardware',connection['id'],'Connection hardware needs a product and finite nonnegative count.')
    for product,count in hardware.items():
        if quantities.get(product,Decimal(0))<count:
            issue('missing_hardware_quantity',product,f'Connections require {count} items; matching demands specify only {quantities.get(product,0)}.')
    for pid,obj in objects.items():
        for operation in (obj.get('blank') or {}).get('operations',[]):
            kind=operation.get('kind')
            if kind=='bore' and (not operation.get('diameter_mm') or len(operation.get('center_mm',[]))!=2):
                issue('missing_cut_information',pid,'A bore needs its diameter and two local face offsets.')
            if kind=='profile_cut' and len(operation.get('profile_mm',[]))<3:
                issue('missing_cut_information',pid,'A profile cut needs the closed outline coordinates in its declared blank face.')
    return findings
