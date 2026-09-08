import unittest
from stud import WallFrame, floor_frame, wall_frame, wall_enclosure, gable_roof, gable_end_frame, door_unit, window_unit
from test_construction_assemblies import project, failures


class ConstructionIntegrationTests(unittest.TestCase):
    def test_finished_walls_roof_and_units_share_datums(self):
        p=project()
        for key,sec in [('ridge',(1.5,9.25)),('fascia',(.75,13.25)),('nailer',(1.5,3.5))]:
            p.stock(key,key,'#aaa',section=sec,lengths=(96,144,192,240))
        p.stock('unit','unit','#ccc',product=True,purchase_unit='unit')
        floor_frame(p,'f',width=144,depth=192,joist_stock='joist',panel_stock='sheet')
        walls=wall_frame(p,'w',width=144,depth=192,height=96,stud_stock='stud',header_stock='joist',spacer_stock='sheet',frame=WallFrame((0,0,8)),interior_finish=True,openings=[dict(id='entry',wall='front',start=50,width=38,bottom=0,height=82),dict(id='view',wall='west',start=48,width=36,bottom=40,height=36)])
        roof=gable_roof(p,'r',length=192,span=144,pitch=6,plate_depth=3.5,frame=WallFrame((144,0,104),90),rafter_stock='joist',ridge_stock='ridge',tie_stock='stud',system='ridge_board_ties',plate_ids=(walls.interfaces['caps']['east'][1],walls.interfaces['caps']['west'][1]),maximum_notch=2,minimum_remaining=5,notch_basis='Regression inputs',eave_overhang=12,rake_overhang=12,fascia_stock='fascia',soffit_stock='sheet',soffit_support_stock='nailer',soffit_wall_ids=(walls.interfaces['walls']['east'].part_ids,walls.interfaces['walls']['west'].part_ids))
        gable_end_frame(p,'g',roof=roof,stud_stock='stud',plate_ids=(walls.interfaces['caps']['front'][1],walls.interfaces['caps']['back'][1]))
        skin=wall_enclosure(p,'skin',walls=walls,sheathing_stock='sheet',siding_stock='sheet',trim_stock='trim',liner_stock='sheet',exterior_height=roof.interfaces['soffit_bottom']-8)
        door_unit(p,'entry',opening=walls.interfaces['openings']['entry']['opening'],product_stock='unit',frame_depth=5.125,inset=-1.125,obstacle_ids=walls.part_ids+skin.part_ids)
        window_unit(p,'view',opening=walls.interfaces['openings']['view']['opening'],product_stock='unit',frame_depth=5.125,inset=-1.125,obstacle_ids=walls.part_ids+skin.part_ids)
        self.assertFalse(failures(p),failures(p))
        panel=next(part for part in p.parts if part['id']==roof.roles['soffit.panel.0.0'])
        panel['origin'][2]-=.25
        self.assertTrue(any(f.get('rule_id')=='r.soffit.support.0.0' for f in failures(p)))
