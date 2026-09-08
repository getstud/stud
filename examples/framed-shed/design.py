"""Worked example: coordinated gable shed geometry, not an approved building plan.
Read README.md before adapting. Site, loads and products remain provisional.
"""
from stud import Project, WallFrame, floor_frame, wall_frame, gable_roof, gable_end_frame, wall_enclosure, door_unit, window_unit
# Architectural choices for this example; change them for the next design.
SIDING_LAYOUT = 'centered'  # 'start' supports an optional first-sheet cut offset.
SIDING_OFFSET = 0
RIDGE_TERMINATION = 'wall'
BIRD_BOX_PAST_TRIM = 4
EAVE_FASCIA_OVERLAP = .375*(1+.5**2)**.5  # Vertical projection of the rake soffit thickness.
FASCIA_ASSEMBLY = '04 / Fascia'  # None keeps fascia with the roof assembly.
project=Project('Worked example | 12 × 16 framed shed')
project.stock('door_kickboard','Door kickboard trim — rip 1×10 blank','#e1dacb',section=(.75,9.25),lengths=(96,120),category='Exterior trim')
project.stock('opening_trim','4 in exterior casing — rip 1×6 blank','#e1dacb',section=(.75,5.5),lengths=(96,120,144),category='Exterior trim')
for key,sec,color in [('stud',(1.5,3.5),'#d8b781'),('joist',(1.5,7.25),'#bb965f'),('beam',(3.5,7.25),'#896c45'),('ridge',(1.5,9.25),'#c9a773'),('fascia',(.75,9.25),'#e1dacb'),('rake_fascia',(.75,9.25),'#e1dacb'),('nailer',(1.5,3.5),'#d1b682'),('trim',(.75,3.5),'#e1dacb')]:
    project.stock(key,{'nailer':'2×4 soffit framing — on edge','fascia':'1×10 eave fascia blank — rip to tail plus soffit overlap','rake_fascia':'1×10 rake fascia blank — rip to rafter plus soffit'}.get(key,key),color,section=sec,lengths=(96,120,144,192,240))
for key,color in [('subfloor','#b99466'),('sheathing','#c4ad82'),('siding','#39555a'),('liner','#e5daca'),('soffit','#e1dacb'),('bird_box_closure','#e1dacb'),('sill_packer','#b99466')]:
    project.stock(key,{'soffit':'⅜ in soffit panels','bird_box_closure':'¾ in bird-box closure panels','sill_packer':'½ in sill installation packers'}.get(key,key),color,sheet=(48,96),sheet_thickness={'soffit':.375,'bird_box_closure':.75,'sill_packer':.5}.get(key))
for key,color in [('pad','#8d8f88'),('door','#b96f48'),('window','#dde0d9')]:
    project.stock(key,key,color,product=True,purchase_unit='unit')
project.validation={'version':1,'automatic':['solid_collision','stock_fit'],'rules':[],'unverified':[
    dict(rule='fixture.site',message='Integration geometry only. Footings, soil, member capacity, connection schedules and local approvals are not designed.') ]}
for i,x in enumerate((0,140.5)):
    for j,y in enumerate((0,90,180)):
        project.box(f'pad.{i}.{j}','01 / Support envelopes','pad',(12,12,12),(x-4.25,y,0))
    project.box(f'beam.{i}','01 / Beams','beam',(3.5,192,7.25),(x,0,12))
    for j in range(3):
        project.validation['rules'].append(dict(id=f'beam.pad.{i}.{j}',kind='minimum_contact',parts=[f'beam.{i}',f'pad.{i}.{j}'],normal=[0,0,-1],minimum_area=42))
project.notes.append('No furnishings. This fixture exercises building assemblies. Product selection, fastening and weather details remain unresolved. Gable cladding and roof-edge trim are modeled. It is unpriced; no $10,000 budget claim is made.')
floor=floor_frame(project,'floor',width=144,depth=192,joist_stock='joist',frame=WallFrame((0,0,19.25)),support_ids=['beam.0','beam.1'],blocking_rows=(48,96),panel_stock='subfloor',assembly='02 / Floor framing')

walls=wall_frame(project,'walls',width=144,depth=192,height=96,stud_stock='stud',header_stock='joist',spacer_stock='sheathing',frame=WallFrame((0,0,floor.interfaces['top_elevation'])),support_ids=[pid for role,pid in floor.roles.items() if role.startswith('panel.')],interior_finish=True,assembly='03 / Wall framing',openings=[dict(id='entry',wall='front',start=50,width=38,bottom=0,height=82),dict(id='view',wall='west',start=48,width=36,bottom=40,height=36)])
roof=gable_roof(project,'roof',length=192,span=144,pitch=6,plate_depth=3.5,frame=WallFrame((144,0,123.25),90),rafter_stock='joist',ridge_stock='ridge',tie_stock='stud',system='ridge_board_ties',plate_ids=(walls.interfaces['caps']['east'][1],walls.interfaces['caps']['west'][1]),maximum_notch=2,minimum_remaining=5,notch_basis='Geometry regression fixture only; not approved sizing',eave_overhang=12,rake_overhang=12,fascia_stock='fascia',rake_fascia_stock='rake_fascia',corner_trim_clearance={'projection':1.25,'side_run':2.25},ridge_termination=RIDGE_TERMINATION,eave_fascia_overlap=EAVE_FASCIA_OVERLAP,bird_box_return=3+BIRD_BOX_PAST_TRIM,fascia_assembly=FASCIA_ASSEMBLY,soffit_stock='soffit',bird_box_stock='bird_box_closure',soffit_support_stock='nailer',soffit_wall_ids=(walls.interfaces['walls']['east'].part_ids,walls.interfaces['walls']['west'].part_ids),assembly='04 / Roof and eave soffits')
gable=gable_end_frame(project,'gable',roof=roof,stud_stock='stud',plate_ids=(walls.interfaces['caps']['front'][1],walls.interfaces['caps']['back'][1]),assembly='04 / Gable end framing')
skin=wall_enclosure(project,'skin',walls=walls,sheathing_stock='sheathing',siding_stock='siding',trim_stock='trim',liner_stock='liner',roof=roof,siding_layout=SIDING_LAYOUT,siding_offset=SIDING_OFFSET,exterior_bottom=-8,opening_trim_stock='opening_trim',opening_trim_width=4,opening_trim_overlap=.5,door_kickboard_stock='door_kickboard',assembly='05 / Wall enclosure')
door=door_unit(project,'entry.unit',opening=walls.interfaces['openings']['entry']['opening'],product_stock='door',frame_depth=5.125,inset=-1.125,obstacle_ids=walls.part_ids+skin.part_ids,sill_support_stock='sill_packer',sill_support_ids=[pid for role,pid in floor.roles.items() if role.startswith('panel.')],assembly='06 / Door unit')
window=window_unit(project,'view.unit',opening=walls.interfaces['openings']['view']['opening'],product_stock='window',frame_depth=5.125,inset=-1.125,operation='casement',obstacle_ids=walls.part_ids+skin.part_ids,sill_support_stock='sill_packer',sill_support_ids=[walls.interfaces['openings']['view']['opening'].roles['sill']],assembly='06 / Window unit')

# Finish regression inputs: architectural charcoal asphalt, closed ridge.
from stud import asphalt_roof
project.stock('roof_deck','5/8 in roof decking','#b39570',sheet=(48,96),sheet_thickness=.625,category='Roof')
for key,name,color,yield_area,unit in [
    ('roof_membrane','Roof membrane allowance','#44454a',400,'roll'),
    ('roof_shingle','Charcoal architectural asphalt shingles','#35383c',32.8,'bundle'),
    ('roof_metal','Drip edge allowance','#aaaeb0',10,'10 ft length'),
    ('roof_starter','Starter strip allowance','#303236',120,'120 ft bundle'),
    ('roof_cap','Ridge cap allowance','#414448',20,'20 ft bundle')]:
    project.stock(key,name,color,**{('coverage_linear_ft' if key in ('roof_metal','roof_starter','roof_cap') else 'coverage_sq_ft'):yield_area},purchase_unit=unit,waste_factor=.1,category='Roof')
finish=asphalt_roof(project,'roof_finish',roof=roof,deck_stock='roof_deck',membrane_stock='roof_membrane',shingle_stock='roof_shingle',flashing_stock='roof_metal',starter_stock='roof_starter',cap_stock='roof_cap',assembly='07 / Asphalt roof finish')
